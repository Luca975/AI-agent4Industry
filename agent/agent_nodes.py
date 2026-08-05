from langchain_core.messages import SystemMessage,HumanMessage,AIMessage
from langchain_anthropic import ChatAnthropic
from langgraph.types import interrupt
from langgraph.runtime import Runtime

from agent_state import AgentState
from agent_context import AgentContext
from agent_tools import tools

MAX_REPLAN = 3
MAX_NO_PLAN = 3

llm = ChatAnthropic(model="claude-sonnet-4-6", temperature=0).bind_tools(tools)


SYSTEM_PROMPT = """You are a planning agent for an industrial robotic system based on PlanSys2.
Your job is to translate a user task into a valid PDDL problem, load it into PlanSys2,
and verify that it is solvable.

You interact with PlanSys2 through tools. Follow this procedure:

1. Call observe_scene to see the objects and the transit graph.
2. Call get_domain to read the PDDL domain (types, predicates, actions).
3. Write a PDDL problem consistent with the domain, the observed scene and the user task.
4. Call set_problem with the full PDDL problem (a single string) to store it.
5. Call send_problem to load it into PlanSys2.
6. Call get_plan to verify that a plan exists.

The world has two kinds of location:
- areas: work stations where pieces are picked and placed (e.g. workspace, conveyor).
- waypoints: transit points the arm moves through between stations (e.g. home, wp1, wp2).
The arm picks and places ONLY on areas; it travels through waypoints, never operating there.

observe_scene returns two sections.

SECTION 1 - "Objects in the scene". One line per object or location:
  "name (type[, color])" optionally followed by "-> location".
- The type in parentheses is authoritative. Declare each object in :objects with exactly
  that type: (area), (waypoint), (robot), (piece).
- "-> <location>": the object is there. Emit (at <name> <location>).
- "-> held by the arm": the piece is in the gripper. Emit (holding <robot> <name>) and do
  NOT emit any (at <name> ...) fact for it.
- no "->": the object/location is not itself located anywhere. Areas and waypoints have no
  "->" (they are locations, not things in a location); emit no (at ...) fact for them.
- color is only to help you identify which piece the task refers to. Never put it in the
  PDDL: the domain has no color predicate.
- humans: a line with type (human) marks a person detected in the cell. Humans are
  obstacles, never manipulated. Do NOT declare them in :objects and do NOT emit any fact
  for them. Their effect is already encoded for you: the arcs they block simply lack their
  (clean_path ...) line in Section 2, and you must omit the (clean ...) line for the node
  they occupy (see below). Skip every (human) line when writing objects and (at ...) facts.

SECTION 2 - "Graph facts". Lines of (connected ...) and (clean_path ...) already written
for you. COPY THEM VERBATIM into :init. Do NOT invent, add, drop or reorder arcs, and do
not derive them yourself: this section is the authoritative topology.
- (connected a b): the arm can travel directly from a to b.
- (clean_path a b): that segment is currently free of humans. An arc that has a
  (connected a b) line but NO (clean_path a b) line is blocked by a human: leave it so,
  the planner must route around it.

Facts you must add yourself, from Section 1:
- (available <robot>) for every robot.
- (clean <location>) for every location where NO human is reported. If a (human) line
  reports a human "-> <location>", that location is NOT clean: omit its (clean ...). The
  arm and the pieces do NOT affect cleanliness: a location holding only the arm or only
  pieces is still clean.
- (free <location>) for every location EXCEPT the one where the arm is. The set of
  locations is every node named in the Graph facts. (free) means no other arm occupies it;
  with a single arm every node is free except the arm's own.

Rules for :objects:
- every location named in the Graph facts MUST be declared, with the type observe_scene
  gave it. A fact referencing an undeclared object makes the planner fail.
- do not declare some_place, humans, or any location that is not a graph node.

Example (FORMAT ONLY - adapt to the real scene and task):

(define (problem test) (:domain gazebo_world)
(:objects 
    arm_1 - robot
    workspace_1 conveyor - area
    circle_2 - piece
    wp1 wp2 home - waypoint
)

(:init
    (available arm_1)
    (at circle_2 workspace_1)
    (at arm_1 home)

    (clean home)
    (clean workspace_1)
    (clean conveyor)
    (clean wp1)
    (clean wp2)

    (free workspace_1)
    (free conveyor)
    (free wp1)
    (free wp2)

    (connected home wp1)      (connected wp1 home)
    (connected home wp2)      (connected wp2 home)
    (connected workspace_1 wp1) (connected wp1 workspace_1)
    (connected wp1 conveyor)  (connected conveyor wp1)
    (connected workspace_1 wp2) (connected wp2 workspace_1)
    (connected wp2 conveyor)  (connected conveyor wp2)

    (clean_path home wp1)      (clean_path wp1 home)
    (clean_path home wp2)      (clean_path wp2 home)
    (clean_path workspace_1 wp1) (clean_path wp1 workspace_1)
    (clean_path wp1 conveyor)  (clean_path conveyor wp1)
    (clean_path workspace_1 wp2) (clean_path wp2 workspace_1)
    (clean_path wp2 conveyor)  (clean_path conveyor wp2) 

)

(:goal (and
    (at circle_2 conveyor)
))
)


In the example: home has no (free) because the arm is there; every node has (clean) because
no human is present; a blocked arc would keep its (connected) line but lose its (clean_path).

If a step returns an error, read it, fix the problem, and retry the relevant steps.
If a message tells you a previous plan was blocked and you must replan, start again from
observe_scene: the scene has changed and the fresh observation reflects it. Build a new
problem from the new Graph facts, do not reuse the previous one.
When a plan is found, STOP calling tools and briefly report success. Do not call any tool
once the problem is solved.
"""



def idle_node(state: AgentState)-> AgentState:
    phase = state.get("phase", "idle")
    if phase == "complete":
        prompt = "Task complete. What would you like to do next?"
    elif phase == "fault":
        prompt = "The task failed due to a system error. What would you like to do next?"
    else:
        prompt = "What would you like to do?"

    user_input = interrupt(prompt)

    return {
        "messages": [HumanMessage(content=user_input)],
        "phase": "idle",
        "cur_problem": None,
        "cur_plan": None,
        "replan_count": 0,
        "no_plan_count": 0
    }

def llm_node(state:AgentState)->AgentState:
    messages = [SystemMessage(content=SYSTEM_PROMPT)]+state["messages"]
    response = llm.invoke(messages)
    return {"messages":[response]}


def emergency_node(state: AgentState) -> AgentState:
    user_input = interrupt(
        "EMERGENCY: a persistent obstacle stopped the operation. "
        "Resolve the situation, then tell me how to proceed.")

    return {
        "messages": [HumanMessage(content=user_input)],
        "phase": "idle",
        "cur_problem": None,
        "cur_plan": None,
        "replan_count": 0,
        "no_plan_count": 0
    }


def running_node(state: AgentState, runtime:Runtime[AgentContext])->AgentState:
    
    plan = state.get("cur_plan")
    if not plan:
        return{
            "messages":[AIMessage(content="No plan to execute.")],
            "phase":"fault"
        }
    
    success, action, message = runtime.context.executor_client.execute_plan(plan)

    if success:
        return {
            "messages":[AIMessage(content="Plan executed successfully.")],
            "phase":"complete"
        }

    obstacle = message.startswith("Obstacle")

    if action == "move" and obstacle:

        count = state.get("replan_count",0) +1
        if count <= MAX_REPLAN:
            return {
                "messages":[HumanMessage(content=(
                    f"The plan was blocked: {message}. "
                    f"Re-observe the scene and build a new plan "
                    f"(replan attempt {count}/{MAX_REPLAN})."))],
                "phase": "replan",
                "replan_count": count,
                "cur_plan" : None,
                "cur_problem" : None
            }
        return {
            "messages": [AIMessage(content=(
            f"Move still blocked after {MAX_REPLAN} replans ({message}). "
            f"Human intervention required."))],
            "phase": "emergency"
        }

    if action in ("pick", "place") and obstacle:
        return {
            "messages": [AIMessage(content=(
                f"{action} blocked: a human occupies the station ({message}). "
                f"Human intervention required."))],
            "phase": "emergency"
        }

    return {
        "messages": [AIMessage(content=f"Plan execution failed: {message}.")],
        "phase": "fault"
    }


# def safe_pos_node(state:AgentState, runtime:Runtime[AgentContext])->AgentState:
    
#     success,info = runtime.context.home_pos_client.go_home()
#     if success:
#         msg = "Execution failed. Arm moved back to the home position"
#     else:
#         msg = f"Execution failed. Arm cannot move back to home: {info}"

#     return{
#         "messages":[AIMessage(content=msg)],
#         "phase":"failed"
#     }