from langchain_core.messages import SystemMessage,HumanMessage
from langchain_anthropic import ChatAnthropic
from langgraph.types import interrupt

from agent_state import AgentState
from agent_tools import tools

STEP_BUDGET = 25

llm = ChatAnthropic(model="claude-sonnet-4-6", temperature=0).bind_tools(tools)


SYSTEM_PROMPT = """You are the controller of a single-arm Niryo robot in an industrial cell.
You accomplish the user's task by sending the arm low-level commands yourself.
You observe the world, decide the next command, send it, read the outcome,
and repeat until the task is done.

TOOLS

observe_scene - returns the current world:
  - Objects: each piece with its type, colour, the station it rests on, and its cartesian
    pose [x, y, z, roll, pitch, yaw]. A piece may instead be "held by the arm".
  - Arm: the node the arm is currently at. This is your starting point for the next move.
  - Nodes: the transit graph, each with a cartesian pose. Two kinds:
      * areas: work stations where pieces are picked and placed.
      * waypoints: transit points the arm passes through between stations.
  - Arcs: which nodes are directly connected, each "clear" or "BLOCKED". BLOCKED means a
    human is on that arc now.

dispatch - send ONE command:
  - move, kind="transit": travel between nodes along an arc. Give pose (the destination
    node's pose), from_node (where the arm is now) and to_node (the destination). Only move
    along arcs listed by observe_scene.
  - move, kind="approach": reach onto a piece inside the station you are at. Give pose (the
    PIECE's pose) and node (the station).
  - grip: give close (true to grasp, false to release) and node (the station you are at).

THE WORLD IS A GRAPH

The arm is always at a node. To reach a non-adjacent node, transit through connecting
waypoints, one transit per arc. from_node for a transit is where the arm is now (the Arm
line of observe_scene). You may only transit along arcs that exist.

PICK AND PLACE

A station's pose is where the arm parks at that station; a piece sits at its own pose
nearby. So you never grip straight after arriving — you approach the piece first.
  - To pick a piece: transit to the piece's station, then move kind="approach" to the
    piece's pose, then grip close=true.
  - To place a held piece: transit to the destination station, then move kind="approach" to
    the drop pose, then grip close=false.
After a pick, the arm holds the piece at the station; your next transit starts from that
station (use it as from_node). Pieces are picked and placed only on areas; waypoints are
for transit.

REACTING TO OUTCOMES

Every command returns an outcome: success, or a reason it failed — an obstacle on an arc or
a node (a human is there), a driver error, or a timeout. Read each outcome and decide what
to do next. The scene is live: observing again after a failure shows you the current state.
How to react is your judgement — choosing another route, waiting and retrying, or, when the
arm alone cannot resolve it, stopping. Nothing about how to react is prescribed here.

FINISHING

Work step by step: observe when you need current information, send one command, read its
outcome, continue. When the task is accomplished, stop calling tools and briefly report what
you did. If it cannot be resolved by the arm alone (for example a human persistently
occupies the only station where a piece must go), stop and say clearly that human
intervention is required.
"""



def idle_node(state: AgentState)-> AgentState:
    """Prompt the user and start the next task"""

    phase = state.get("phase", "idle")
    if phase == "complete":
        prompt = "Task complete. What would you like to do next?"
    else:
        prompt = "What would you like to do?"

    user_input = interrupt(prompt)

    return {
        "messages": [HumanMessage(content=user_input)],
        "phase": "idle",
        "step_budget": STEP_BUDGET
    }

def llm_node(state:AgentState)->AgentState:
    messages = [SystemMessage(content=SYSTEM_PROMPT)]+state["messages"]
    response = llm.invoke(messages)
    return {"messages":[response],
            "step_budget": state.get("step_budget", STEP_BUDGET) - 1
            }


def emergency_node(state: AgentState) -> AgentState:
    user_input = interrupt(
        "EMERGENCY: a persistent obstacle stopped the operation. "
        "Resolve the situation, then tell me how to proceed.")

    return {
        "messages": [HumanMessage(content=user_input)],
        "phase": "idle",
        "step_budget": STEP_BUDGET
    }