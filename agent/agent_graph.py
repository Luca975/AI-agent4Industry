from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode
from langgraph.checkpoint.memory import InMemorySaver

from agent_state import AgentState
from agent_tools import tools
from agent_nodes import idle_node, llm_node, running_node, safe_pos_node
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
    return "idle"

def route_from_running(state:AgentState)->str:
    return "idle" if state.get("phase") == "complete" else "safe_pos"


builder = StateGraph(AgentState, context_schema=AgentContext)

builder.add_node("idle",idle_node)
builder.add_node("llm",llm_node)
builder.add_node("tools",ToolNode(tools))
builder.add_node("running",running_node)
builder.add_node("safe_pos",safe_pos_node)

builder.add_edge(START,"idle")
builder.add_conditional_edges("idle",route_from_idle,{
  "llm":"llm",
  "end":END  
})
builder.add_conditional_edges("llm",route_from_llm,{
    "tools":"tools",
    "idle":"idle",
    "running":"running"
})
builder.add_edge("tools","llm")
builder.add_conditional_edges("running", route_from_running, {
    "idle":"idle",
    "safe_pos":"safe_pos"
})
builder.add_edge("safe_pos","idle")



graph = builder.compile(checkpointer=InMemorySaver())

