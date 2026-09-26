import os
from langchain_core.messages import SystemMessage,HumanMessage,AIMessage
#from langchain_anthropic import ChatAnthropic #USE THIS FOR CLAUDE API CALLING
from langchain_openai import ChatOpenAI
from langgraph.types import interrupt
from langgraph.runtime import Runtime

from agent_state import AgentState
from agent_context import AgentContext
from agent_tools import tools
from agent_prompts import AGENT_GRAMMAR

MAX_REPLAN = 3
MAX_NO_PLAN = 3
MAX_INCOMPLETE = 2
MAX_STEPS = 20

USE_GRAMMAR = os.environ.get("USE_GRAMMAR","0") == "1"
_extra_body = {"stop": ["</tool_call>"],
               "include_stop_str_in_output":True,
               "chat_template_kwargs":{"enable_thinking":True}}
if USE_GRAMMAR:
    _extra_body["guided_grammar"] = AGENT_GRAMMAR

#llm = ChatAnthropic(model="claude-sonnet-4-6", temperature=0).bind_tools(tools)

llm = ChatOpenAI(
    base_url=os.environ.get("VLLM_BASE_URL", "http://192.168.100.162:8001/v1"),
    model=os.environ.get("VLLM_MODEL", "Qwen3.5-4B"),
    api_key="EMPTY",
    temperature=0,
    extra_body={"stop": ["</tool_call>"],
               "include_stop_str_in_output":True,
               "chat_template_kwargs":{"enable_thinking":True}},
    reasoning_effort="high",
).bind_tools(tools)

# Same endpoint, NO tools: used only to summarize a finished task in plain prose.
# Without this, the tool-bound llm could emit a tool_call instead of a summary.
llm_base = ChatOpenAI(
    base_url=os.environ.get("VLLM_BASE_URL", "http://192.168.100.162:8001/v1"),
    model=os.environ.get("VLLM_MODEL", "Qwen3.5-4B"),
    api_key="EMPTY",
    extra_body={"chat_template_kwargs":{"enable_thinking":False}},
    temperature=0
)

# The SYSTEM_PROMPT below works with Qwen3.5-4B (v1, v2 is in the prompts file) ------------------------------------------------------------------------------------------------------------

# SYSTEM_PROMPT = """You control an industrial robot cell only through tools.
# One tool call per turn. When the task is DONE (QUERY answered, or get_plan
# returned a solvable plan), call no more tools and report briefly.
# You handle two types of task:
#     -   QUERY (question about the scene or the robot): call observe_scene or get_domain,
#         answer in plain text, STOP. No PDDL.

#     -   MANIPULATION (move, pick or place pieces): call observe_scene and get_domain;
#         write a domain-consistent PDDL problem and run the CHECKLIST; then call
#         set_problem, send_problem and get_plan.
#         When get_plan returns a solvable plan, the task is DONE: call no more tools,
#         report the plan in one sentence.
# On error: fix the error by running the CHECKLIST and retry with a correct PDDL problem. If the plan was BLOCKED: restart from observe_scene with a
# new problem.

# PDDL RULES
# - Section 1 lines "name (type[, color]) [-> location]": declare name in :objects with
#   that type. "-> loc": (at name loc). "-> held by the arm": (holding robot name).
#   No "->": it is a location. No colors.
# - Types: keep the exact type observe_scene gives. A (waypoint) is declared
#   "- waypoint", an (area) is declared "- area". Never change a type.
# - In :objects write ONE line per type. Every name before "- type" gets that type:
#   "wp1 wp2 - waypoint" makes both waypoints. Never mix types on one line.
# - Section 2 "Graph facts": copy verbatim into :init.
# - Add (available robot) for each robot.
# - Areas and waypoints are both classified as locations.
# - clean: for each location L, add (clean L) unless a (human) line says "-> L".
# - free: for each location L, add (free L) unless it is where the arm is.

# CHECKLIST
# - Every object and location returned by observe_scene (Section 1 and Graph facts)
#   is declared in :objects with its type.
# - Every waypoint is "- waypoint", every area is "- area", one line per type.
# - Every location has (clean ...) unless a human is on it; every location
#   except the arm's has (free ...).
# - Every name in :init and :goal is declared.
# - Only types and predicates from get_domain.
# - Graph facts copied exactly. Parentheses balanced.

# EXAMPLE (structure only)
# (define (problem task) (:domain gazebo_world)
# (:objects
#     arm_1 - robot
#     workspace_1 conveyor - area
#     home wp1 - waypoint
#     circle_2 - piece
# )
# (:init (available arm_1) (at arm_1 home) (at circle_2 workspace_1)
#   (clean home) (clean workspace_1) (clean conveyor) (clean wp1)
#   (free workspace_1) (free conveyor) (free wp1)   ; no (free home): the arm is there
#   ; Graph facts here)
# (:goal (and (at circle_2 conveyor))))
# """
# -------------------------------------------------------------------------------------------

#--------------------------PROMPT for 9B
SYSTEM_PROMPT = """You control a robot cell through tools. One tool call per turn.
There are two kinds of task:

    ORDER — the robot must act. Always run the STEPS. Never reply with words instead of acting.

    QUESTION — "where", "how many", "what": call observe_scene or get_domain, answer
    in words, stop. No PDDL.

STEPS — do them in this order, one per turn:
1. observe_scene
2. get_domain
3. write the problem
4. check the problem
5. clear_problem
6. set_problem
7. send_problem
8. get_plan
If step 8 says "No plan found", or any tool returns an error: rewrite the problem
and go back to step 5.
If a message says the plan was blocked: go back to step 1 and write a new problem
from the new scene.

HOW TO WRITE THE PROBLEM
:objects — one line per type, "<names> - <type>". Types: robot, area, waypoint,
  piece, human.
:init —
  (available arm_1)
  (at X P) for each "-> P" line, object first, place second. Only a robot, a piece
    or a human. An area or a waypoint never gets an (at ...).
    "-> held by the arm" becomes (holding arm_1 X), with no (at ...) for it.
  every "Graph facts" line, copied exactly: they all start with (connected ...).
    Never add a (clean_path ...) that is not printed: a missing one means a human
    blocks that segment, and adding it sends the arm into the human.
  (clean L) for every area and every waypoint, except where a human is.
  (free L) for every area and every waypoint, except where the arm is.
:goal — (at cube_1 conveyor) to move a piece, (at arm_1 home) to move only the arm.
Nothing else: no colors, no :precondition, no :action.

CHECK before set_problem: count the areas and waypoints; (clean) and (free) must
match that count minus their exception; the (clean_path) count must equal the one in
the Graph facts; every name used is in :objects; parentheses balanced.

=== START OF EXAMPLE — these names are not the real ones ===

Task: "move the blue block to station_b"

observe_scene printed:
block_7 (piece, blue) -> station_a
worker_2 (human) -> w2
arm_1 (robot) -> base
station_a (area)
station_b (area)
base (waypoint)
w1 (waypoint)
w2 (waypoint)

Graph facts (copy these verbatim into :init):
(connected base w1) (clean_path base w1)
(connected w1 station_a) (clean_path w1 station_a)
(connected station_a w2)

The correct problem:
(define (problem task)
(:domain gazebo_world)
(:objects
    arm_1 - robot
    station_a station_b - area
    base w1 w2 - waypoint
    block_7 - piece
    worker_2 - human
)
(:init
    (available arm_1)
    (at arm_1 base)
    (at block_7 station_a)
    (at worker_2 w2)
    (clean station_a) (clean station_b) (clean base) (clean w1)
    (free station_a) (free station_b) (free w1) (free w2)
    (connected base w1) (clean_path base w1)
    (connected w1 station_a) (clean_path w1 station_a)
    (connected station_a w2)
)
(:goal (and (at block_7 station_b)))
)

5 locations, so 4 (clean) because w2 has the human and 4 (free) because base has
the arm. The w2 arc keeps no (clean_path).

=== END OF EXAMPLE — always use the real names observe_scene gives you ===
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

    summary_update = {}
    if phase in ("complete","fault"):
        task_msgs = state["messages"][state.get("task_start",0):]
        summary_prompt = [
            SystemMessage(content=("Summarize in one sentence, max 30 words: task, outcome")),
            *task_msgs
        ]
        summary = llm_base.invoke(summary_prompt)
        summary_update["last_summary"] = summary.content

    return {
        "messages": [HumanMessage(content=user_input)],
        "phase": "idle",
        "cur_problem": None,
        "cur_plan": None,
        "replan_count": 0,
        "no_plan_count": 0,
        "load_status": None,
        "incomplete_flow_count": 0,
        "task_start": len(state["messages"]),
        **summary_update,
        "step_count": 0
    }   

def llm_node(state:AgentState)->AgentState:
    #curr_prompt = [SystemMessage(content=SYSTEM_PROMPT)]

    system = SYSTEM_PROMPT
    if state.get("last_summary"):
        system += f"\n\nPrevious task: {state['last_summary']}"
    curr_prompt = [SystemMessage(content=system)]

    curr_prompt += state["messages"][state.get("task_start",0):]
    #messages = [SystemMessage(content=SYSTEM_PROMPT)]+state["messages"]
    response = llm.invoke(curr_prompt)
    return {"messages":[response],
            "step_count": state.get("step_count",0)+1}


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
        "incomplete_flow_count": 0,
        "task_start": len(state["messages"]),
        "last_summary": None,
        "step_count":0
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
        "incomplete_flow_count": count,
        "no_plan_count": 0
    }        