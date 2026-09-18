import os
from langchain_core.messages import SystemMessage,HumanMessage,AIMessage
#from langchain_anthropic import ChatAnthropic #USE THIS FOR CLAUDE API CALLING
from langchain_openai import ChatOpenAI
from langgraph.types import interrupt
from langgraph.runtime import Runtime

from agent_state import AgentState
from agent_context import AgentContext
from agent_tools import tools

MAX_REPLAN = 3
MAX_NO_PLAN = 3
MAX_INCOMPLETE = 2

#llm = ChatAnthropic(model="claude-sonnet-4-6", temperature=0).bind_tools(tools)

llm = ChatOpenAI(
    base_url=os.environ.get("VLLM_BASE_URL", "http://192.168.100.162:8001/v1"),
    model=os.environ.get("VLLM_MODEL", "Qwen2.5-3B-Instruct"),
    api_key="EMPTY",
    temperature=0,
    extra_body={"stop": ["</tool_call>"]}
).bind_tools(tools)

SYSTEM_PROMPT = """You are an agent for an industrial robotic cell based on PlanSys2. You act ONLY through
the available tools. Each tool's description tells you what it does; do not re-derive it.

=== STEP 0: CLASSIFY THE TASK (decide BEFORE doing anything) ===
Every user message is one of two kinds:

- QUERY: a question about the current state (what is present, where, how many, which
  color, how locations connect, what the robot can do). To answer a QUERY:
    1. Call the tool that holds the answer (scene facts -> observe_scene; robot actions
       or domain -> get_domain; call BOTH only if the question needs both).
    2. Read the tool result, then REPLY IN PLAIN TEXT and STOP.
    Do NOT write PDDL. Do NOT call set_problem, send_problem or get_plan for a QUERY.

    Example A (scene question):
      User: "How many pieces are in the scene and where are they?"
      -> call observe_scene
      -> reply: "There are 2 pieces: cube_1 on workspace_1 and cube_3 held by the arm."  STOP.

    Example B (domain question):
      User: "What actions can the robot perform?"
      -> call get_domain
      -> reply: "The robot can move, pick and place."  STOP.

- MANIPULATION: a task that requires moving/picking/placing pieces. Follow the FLOW below.

=== GLOBAL RULES (both kinds) ===
- Call ONE tool per turn. Wait for its result before the next call. Never emit several
  tool calls in one message.
- When the task is done (QUERY answered, or plan found), STOP calling tools and briefly
  report. Do not call any tool once done.

=== MANIPULATION FLOW ===
1. observe_scene  -> objects + transit graph.
2. get_domain     -> types, predicates, actions.
3. Write a PDDL problem for the domain, scene and task.
4. set_problem    -> store the full PDDL problem (one string).
5. send_problem   -> load it into PlanSys2.
6. get_plan       -> verify a plan exists.
If a step errors, read it, fix the problem, retry.

=== REPLANNING (MANIPULATION only) ===
If you receive a message saying the previous plan was BLOCKED and you must replan:
- Do NOT reuse or edit the old problem, and do NOT retry the same plan.
- RESTART the flow from observe_scene: the scene has changed, so read it fresh.
- Build a completely NEW PDDL problem from the new Graph facts, then set/send/get_plan again.

Two kinds of location:
- areas: stations where pieces are picked/placed (e.g. workspace, conveyor).
- waypoints: transit points the arm moves through (e.g. home, wp1, wp2).
The arm picks/places ONLY on areas; it travels through waypoints, never operating there.

observe_scene returns two sections.

SECTION 1 - "Objects in the scene", one line per object/location:
  "name (type[, color])" optionally "-> location".
- The type in parentheses is authoritative. Declare each object in :objects with that
  exact type: (area), (waypoint), (robot), (piece).
- "-> <location>": emit (at <name> <location>).
- "-> held by the arm": emit (holding <robot> <name>); emit NO (at <name> ...) for it.
- no "->": it is a location, not a thing in a location; emit no (at ...) for it.
- color: only to identify the piece. NEVER put color in the PDDL.
- (human) lines: obstacles. Do NOT declare them and emit NO fact for them. Skip them.

SECTION 2 - "Graph facts": lines of (connected ...) and (clean_path ...).
COPY THEM VERBATIM into :init. Do NOT invent, add, drop or reorder arcs. This section is
the authoritative topology.
- (connected a b): the arm can travel directly a -> b.
- (clean_path a b): that segment is human-free. A (connected a b) line with NO matching
  (clean_path a b) is blocked by a human: leave it so; the planner routes around it.

Facts YOU add, from Section 1:
- (available <robot>) for every robot.
- (clean <location>) for every location with NO human on it. If a (human) is "-> <loc>",
  omit (clean <loc>). Arm and pieces do NOT affect cleanliness.
- (free <location>) for every location EXCEPT the one where the arm is.

:objects rules:
- Declare EVERY item listed in SECTION 1 (objects) AND every node in the Graph facts,
  each with the exact type observe_scene gave it.
- This INCLUDES every piece. A piece you must move (e.g. cube_1) MUST appear in :objects
  as "cube_1 - piece". Forgetting a piece makes the problem INVALID.
- Any fact naming an undeclared object makes the planner reject the problem.
- Do not declare humans or anything that is not in Section 1 or the Graph facts.

FORMAT EXAMPLE (adapt to the REAL scene and task - do not copy these values):

(define (problem test) (:domain gazebo_world)
(:objects
    arm_1 - robot
    workspace_1 conveyor - area
    circle_2 - piece          ; every piece MUST be declared here
    wp1 wp2 home - waypoint
)
(:init
    (available arm_1)
    (at circle_2 workspace_1)
    (at arm_1 home)

    (clean home) (clean workspace_1) (clean conveyor) (clean wp1) (clean wp2)

    (free workspace_1) (free conveyor) (free wp1) (free wp2)

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

Here home has no (free) because the arm is there; every node has (clean) because no human
is present; a blocked arc would keep (connected) but lose (clean_path).
"""



def idle_node(state: AgentState)-> AgentState:
    """Prompt the user and start the next task"""

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
        "no_plan_count": 0,
        "load_status": None,
        "incomplete_flow_count": 0
    }

def llm_node(state:AgentState)->AgentState:
    messages = [SystemMessage(content=SYSTEM_PROMPT)]+state["messages"]
    response = llm.invoke(messages)
    return {"messages":[response]}


def emergency_node(state: AgentState) -> AgentState:
    user_input = interrupt(
        "EMERGENCY: Replanning attempts expired! Check the area for safety reason and press space to restart")

    return {
        "messages": [HumanMessage(content=user_input)],
        "phase": "idle",
        "cur_problem": None,
        "cur_plan": None,
        "replan_count": 0,
        "no_plan_count": 0,
        "load_status": None,
        "incomplete_flow_count": 0
    }


def running_node(state: AgentState, runtime:Runtime[AgentContext])->AgentState:
    """Execute the current plan and translate its outcome into the next phase.
    
    The replan-vs-emergency decision is made as follow:
        -move blocked by any obstacle -> replan up to MAX_REPLAN, then emergency
        -pick/place blocked -> emergency
        -any other failure -> fault (system error, not a safety event)"""
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
                "cur_problem" : None,
                "load_status": None
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

def recover_node(state: AgentState) -> AgentState:
    """The LLM sets the problem (cur_problem) but produces no plan and stops
    calling tools. Nudge it back with a specific message, up to MAX_INCOMPLETE times, then degrade to fault"""

    count = state.get("incomplete_flow_count",0)+1

    if count > MAX_INCOMPLETE:
        return {
            "messages": [AIMessage(content=("Flow left incomplete repeatedly without a plan."))],
            "phase":"fault",
            "incomplete_flow_count":count,
            "cur_problem":None,
            "cur_plan":None,
            "load_status": None
        }

    if state.get("load_status") == "failed":
        # PlanSys2 rejected the problem
        nudge = (
            "The problem you defined was REJECTED by the system (see the error above). "
            "Do NOT retry the same problem unchanged. Re-read the scene with observe_scene, "
            "fix the PDDL (every object AND every piece declared in :objects, parentheses "
            "balanced), then call set_problem, send_problem and get_plan again."
        )
    else:
        # Problem stored but the flow was never carried through
        nudge = (
            "You defined a problem but did NOT complete the flow: no plan was verified. "
            "Call send_problem to load it, then get_plan to verify a plan exists. "
            "One tool call per turn."
        )

    return {
        "messages": [HumanMessage(content=nudge)],
        "phase": "idle",
        "incomplete_flow_count": count
    }        