from langchain_core.messages import SystemMessage,HumanMessage,AIMessage
from langchain_anthropic import ChatAnthropic
from langgraph.types import interrupt
from langgraph.runtime import Runtime

from agent_state import AgentState
from agent_context import AgentContext
from agent_tools import tools

llm = ChatAnthropic(model="claude-sonnet-4-6", temperature=0).bind_tools(tools)


SYSTEM_PROMPT = """You are a planning agent for an industrial robotic system based on PlanSys2.
Your job is to translate a user task into a valid PDDL problem, load it into PlanSys2,
and verify that it is solvable.
 
You interact with PlanSys2 through tools. Follow this procedure:
 
1. Call observe_scene to see which objects are in the environment, their type, their
   location, whether a piece is held by the arm, and (for pieces) their color.
2. Call get_domain to read the PDDL domain (types, predicates, actions).
3. Write a PDDL problem that satisfies the user's task, consistent with the domain and the
   observed scene.
4. Call set_problem with the full PDDL problem (a single string) to store it.
5. Call send_problem to load it into PlanSys2.
6. Call get_plan to verify that a plan exists.
 
Reading observe_scene. Each object is reported on one line as
"name (type[, color]) -> location". Interpret it when building the :init section:
- "-> <area>": the object is in that area. Emit (at <name> <area>).
- "-> held by the arm": the piece is in the gripper, it is NOT in any area. Emit
  (holding <robot> <name>) and do NOT emit any (at <name> ...) fact for that piece.
- no "->" at all: the object is outside every area. Do not emit an (at ...) fact for it.
- color, when present, only helps you identify which piece the task refers to. It is
  descriptive: never put it in the PDDL. The domain has no color predicate, and emitting
  one would make the planner fail on an undeclared symbol.
 
Declare every area named by observe_scene as an object of type area, including some_place
(the arm's location when it is outside every real area). A predicate that references an
undeclared object makes the planner fail, so an area that appears in an (at ...) fact must
also appear in :objects.
 
observe_scene reports the (at ...) and (holding ...) facts, but not the predicates the
actions require to fire. Add those yourself:
- (clean <area>) ONLY for areas where observe_scene reports neither a human nor a robot
  present. An area occupied by a human or by a robot is NOT clean, so omit its (clean ...)
  fact. Pieces do NOT affect cleanliness: an area that contains only pieces is still clean.
- (available <robot>) for every robot, so it can pick.
 
Example problem (FORMAT ONLY - adapt objects, init and goal to the real scene and task):
 
(define (problem test) (:domain gazebo_world)
(:objects
    arm_1 - robot
    workspace_1 conveyor some_place - area
    circle_2 - piece
)
 
(:init
    (available arm_1)
    (at circle_2 workspace_1)
    (at arm_1 some_place)
    (clean workspace_1)
    (clean conveyor)
)
 
(:goal (and
    (at circle_2 conveyor)
    )
)
)
 
Note in the example: some_place has no (clean ...) fact because the arm is there;
workspace_1 stays clean even though a piece sits in it.
 
If a step returns an error, read it, fix the PDDL problem, and retry the relevant steps.
When a plan has been successfully found, STOP calling tools and briefly report success to
the user. Do not call any tool once the problem is solved.
"""



def idle_node(state: AgentState)-> AgentState:
    phase = state.get("phase", "idle")
    if phase == "complete":
        prompt = "Task complete. What would you like to do next?"
    elif phase == "failed":
        prompt = "Task failed. What would you like to do next?"
    else:
        prompt = "What would you like to do?"

    user_input = interrupt(prompt)

    return{
        "messages" : [HumanMessage(content=user_input)],
        "phase" : "idle",
        "cur_problem" : None,
        "cur_plan" : None
    }

def llm_node(state:AgentState)->AgentState:
    messages = [SystemMessage(content=SYSTEM_PROMPT)]+state["messages"]
    response = llm.invoke(messages)
    return {"messages":[response]}


def running_node(state: AgentState, runtime:Runtime[AgentContext])->AgentState:
    
    plan = state.get("cur_plan")
    if not plan:
        return{
            "messages":[AIMessage(content="No plan to execute.")],
            "phase":"failed"
        }
    
    success, info = runtime.context.executor_client.execute_plan(plan)

    if success:
        return {
            "messages":[AIMessage(content="Plan executed successfully.")],
            "phase":"complete"
        }
    
    return{
        "messages":[AIMessage(content=f"Plan execution failed: {info}.")],
        "phase":"failed"
    }

def safe_pos_node(state:AgentState, runtime:Runtime[AgentContext])->AgentState:
    
    success,info = runtime.context.home_pos_client.go_home()
    if success:
        msg = "Execution failed. Arm moved back to the home position"
    else:
        msg = f"Execution failed. Arm cannot move back to home: {info}"

    return{
        "messages":[AIMessage(content=msg)],
        "phase":"failed"
    }