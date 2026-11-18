from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode
from langgraph.checkpoint.memory import InMemorySaver

from agent_state import AgentState
from agent_tools import tools
from agent_nodes import (idle_node, llm_node, running_node, emergency_node, recover_node, planning_node, MAX_NO_PLAN, MAX_STEPS)
from agent_context import AgentContext

def route_from_idle(state:AgentState)->str:
    last = state['messages'][-1].content.strip().lower()
    return "end" if last == "exit" else "llm"


def route_from_llm(state: AgentState) -> str:
    """Route after an LLM turn. First match wins.
 
    1. step cap reached      -> fault   : MAX_STEPS LLM turns spent on this task.
    2. pending tool calls    -> tools   : the model wants to call a tool; run it.
    3. a problem was defined -> recover : planning_node rejected the problem or found no plan,
                                          and the model answered in words instead of calling
                                          set_problem again.
    4. otherwise             -> idle    : a finished QUERY, or nothing to do.
 
    Plans and planning escalation never pass through here: planning_node decides them.
    cur_problem is the discriminator between 3 and 4; a QUERY never sets it.
    """

    if state.get("step_count",0)>=MAX_STEPS:
        return "fault"

    last = state["messages"][-1]
    if getattr(last, "tool_calls", None):
        return "tools"
    if state.get("cur_problem") is not None:
        return "recover"
    return "idle"

def route_from_planning(state: AgentState) -> str:
    """Map the outcome of planning_node.
 
    - fault     -> idle      : ROS/system error, the model cannot fix it.
    - solved    -> running   : plan found, execute it.
    - cap       -> emergency : MAX_NO_PLAN failed attempts (empty, rejected or unsolvable).
    - otherwise -> llm       : guidance was sent, let the model fix the problem.
    """
    if state.get("phase") == "fault":
        return "fault"
    if state.get("planning_status") == "solved":
        return "running"
    if state.get("no_plan_count", 0) >= MAX_NO_PLAN:
        return "emergency"
    return "llm"

def route_from_running(state: AgentState) -> str:
    """Map the phase set by running_node to the next node. 'fault' is wired to idle."""
    phase = state.get("phase")
    if phase == "complete":
        return "idle"
    if phase == "replan":
        return "llm"
    if phase == "emergency":
        return "emergency"
    return "fault"

def route_from_tools(state: AgentState) -> str:
    """set_problem marks the problem as "pending": hand it to the planning pipeline.
    observe_scene / get_domain leave planning_status unchanged and go back to the LLM."""
    if state.get("planning_status") == "pending":
        return "planning"
    return "llm"

def route_from_recover(state: AgentState) -> str:
    """fault -> idle once MAX_INCOMPLETE is exceeded; otherwise nudge the LLM again."""
    return "fault" if state.get("phase") == "fault" else "llm"

builder = StateGraph(AgentState, context_schema=AgentContext)

builder.add_node("idle",idle_node)
builder.add_node("llm",llm_node)
builder.add_node("tools",ToolNode(tools))
builder.add_node("planning",planning_node)
builder.add_node("running",running_node)
builder.add_node("emergency",emergency_node)
builder.add_node("recover", recover_node)

builder.add_edge(START,"idle")
builder.add_conditional_edges("idle",route_from_idle,{
  "llm":"llm",
  "end":END  
})
builder.add_conditional_edges("llm",route_from_llm,{
    "tools":"tools",
    "idle":"idle",
    "recover":"recover",
    "fault":"idle"
})
builder.add_conditional_edges("tools", route_from_tools, {
    "llm":"llm",
    "planning":"planning"
})

builder.add_conditional_edges("planning", route_from_planning, {
    "running": "running",
    "llm": "llm",
    "emergency": "emergency",
    "fault": "idle",
})

builder.add_conditional_edges("running", route_from_running, {
    "idle": "idle",
    "llm": "llm",
    "emergency": "emergency",
    "fault": "idle",
})
builder.add_conditional_edges("recover", route_from_recover, {
    "llm": "llm",
    "fault": "idle",
})
builder.add_edge("emergency", "idle")



graph = builder.compile(checkpointer=InMemorySaver())

