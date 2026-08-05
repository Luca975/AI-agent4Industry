from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode
from langgraph.checkpoint.memory import InMemorySaver

from agent_state import AgentState
from agent_tools import tools
from agent_nodes import idle_node, llm_node, running_node, emergency_node, MAX_NO_PLAN
from agent_context import AgentContext

def route_from_idle(state:AgentState)->str:
    last = state['messages'][-1].content.strip().lower()
    return "end" if last == "exit" else "llm"


def route_from_llm(state:AgentState)->str:
    last=state["messages"][-1]
    if getattr(last,"tool_calls",None):
        return "tools"
    if state.get("cur_plan") is not None:
        return "running"
    if state.get("no_plan_count",0) > 0:
        return "emergency"
    return "idle"

def route_from_running(state:AgentState)->str:
    phase = state.get("phase")
    if phase == "complete":
        return "idle"
    if phase == "replan":
        return "llm"
    if phase == "emergency":
        return "emergency"
    return "fault"

def route_from_tools(state:AgentState)->str:
    if state.get("no_plan_count",0) >= MAX_NO_PLAN:
        return "emergency"
    return "llm"


builder = StateGraph(AgentState, context_schema=AgentContext)

builder.add_node("idle",idle_node)
builder.add_node("llm",llm_node)
builder.add_node("tools",ToolNode(tools))
builder.add_node("running",running_node)
builder.add_node("emergency",emergency_node)

builder.add_edge(START,"idle")
builder.add_conditional_edges("idle",route_from_idle,{
  "llm":"llm",
  "end":END  
})
builder.add_conditional_edges("llm",route_from_llm,{
    "tools":"tools",
    "idle":"idle",
    "running":"running",
    "emergency":"emergency"
})
builder.add_conditional_edges("tools", route_from_tools, {
    "llm":"llm",
    "emergency":"emergency"
})
builder.add_conditional_edges("running", route_from_running, {
    "idle":"idle",
    "llm":"llm",
    "emergency":"emergency",
    "fault":"idle"
})
builder.add_edge("emergency","idle")



graph = builder.compile(checkpointer=InMemorySaver())

