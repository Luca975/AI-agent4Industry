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
 
1. Call observe_scene to see which objects are in the environment, their type, and their area.
2. Call get_domain to read the PDDL domain (types, predicates, actions).
3. Write a PDDL problem that satisfies the user's task, consistent with the domain and the
   observed scene.
4. Call set_problem with the full PDDL problem (a single string) to store it.
5. Call send_problem to load it into PlanSys2.
6. Call get_plan to verify that a plan exists.
 
When writing the :init section, remember that observe_scene gives you only the object
locations (the `at` facts). You must also add the predicates the actions require but that
are not observed:
- (clean <area>) for every area, so robots can move into it;
- (available <robot>) for every robot, so it can pick.
 
Example problem (FORMAT ONLY - adapt objects, init and goal to the real scene and task):
 
(define (problem task) (:domain gazebo_world)
(:objects
    arm_1 - robot
    workspace_1 conveyor - area
    red_cube - piece
)
(:init
    (available arm_1)
    (at arm_1 workspace_1)
    (at red_cube workspace_1)
    (clean workspace_1)
    (clean conveyor)
)
(:goal (and
    (at red_cube conveyor)
))
)
 
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
    if plan is None or not plan.items:
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