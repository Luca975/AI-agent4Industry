from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode
from langgraph.checkpoint.memory import InMemorySaver

from agent_state import AgentState
from agent_tools import tools
from agent_nodes import idle_node, llm_node, emergency_node
from agent_context import AgentContext

def route_from_idle(state:AgentState)->str:
    last = state['messages'][-1].content.strip().lower()
    return "end" if last == "exit" else "llm"


def route_from_llm(state:AgentState)->str:
    """After an LLM turn: run any tool calls; else the task is done (the model
    stopped calling tools) so return to idle. If the step budget is spent, escalate
    to emergency instead of looping. The budget is the only deterministic guard —
    every reaction decision was already the LLM's."""
    last = state["messages"][-1]
    if getattr(last, "tool_calls", None):
        return "tools"
    if state.get("step_budget", 0) <= 0:
        return "emergency"
    return "idle"

def route_from_tools(state: AgentState) -> str:
    """After tools run, hand control back to the LLM — unless the budget is spent,
    in which case terminate via emergency rather than loop."""
    if state.get("step_budget", 0) <= 0:
        return "emergency"
    return "llm"


builder = StateGraph(AgentState, context_schema=AgentContext)

builder.add_node("idle",idle_node)
builder.add_node("llm",llm_node)
builder.add_node("tools",ToolNode(tools))
builder.add_node("emergency",emergency_node)

builder.add_edge(START,"idle")
builder.add_conditional_edges("idle",route_from_idle,{
  "llm":"llm",
  "end":END  
})
builder.add_conditional_edges("llm",route_from_llm,{
    "tools":"tools",
    "idle":"idle",
    "emergency":"emergency"
})
builder.add_conditional_edges("tools", route_from_tools, {
    "llm":"llm",
    "emergency":"emergency"
})

builder.add_edge("emergency","idle")



graph = builder.compile(checkpointer=InMemorySaver())

