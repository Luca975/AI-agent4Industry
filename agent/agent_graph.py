from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode
from langgraph.checkpoint.memory import InMemorySaver

from agent_state import AgentState
from agent_tools import tools
from agent_nodes import idle_node, llm_node
from agent_context import AgentContext

def route_from_idle(state:AgentState)->str:
    last = state['messages'][-1].content.strip().lower()
    return "end" if last == "exit" else "llm"

def route_from_llm(state:AgentState)->str:
    last=state["messages"][-1]
    if getattr(last,"tool_calls",None):
        return "tools"
    return "idle"


builder = StateGraph(AgentState)

builder.add_node("idle",idle_node)
builder.add_node("llm",llm_node)
builder.add_node("tools",ToolNode(tools))

builder.add_edge(START,"idle")
builder.add_conditional_edges("idle",route_from_idle,{
  "llm":"llm",
  "end":END  
})
builder.add_conditional_edges("llm",route_from_llm,{
    "tools":"tools",
    "idle":"idle"
})
builder.add_edge("tools","llm")

graph = builder.compile(checkpointer=InMemorySaver(), context_schema=AgentContext)

