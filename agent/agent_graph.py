from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode
from langgraph.checkpoint.memory import InMemorySaver

from agent_state import AgentState
from agent_tools import tools
from agent_nodes import idle_node, llm_node, running_node, emergency_node, recover_node, MAX_NO_PLAN
from agent_context import AgentContext

def route_from_idle(state:AgentState)->str:
    last = state['messages'][-1].content.strip().lower()
    return "end" if last == "exit" else "llm"


def route_from_llm(state: AgentState) -> str:
    """Route after an LLM turn. Branches are checked in priority order, most specific
    first; the first match wins.

    1. pending tool calls        -> tools     : the model wants to call a tool; run it.
    2. a plan is ready           -> running   : cur_plan is set, hand off to execution.
    3. planner already failed     -> emergency : no_plan_count > 0 means get_plan was
                                                called and found nothing; deterministic escape.
    4. a problem was defined     -> recover   : no tool call, no plan, planner never
                                                complained, yet cur_problem is set. The model
                                                started a manipulation flow and stopped without
                                                carrying it to a plan. This case used to fall
                                                through to idle silently; recover catches it.
    5. otherwise                 -> idle      : nothing in progress and no problem defined —
                                                a finished QUERY, or nothing to do.

    The discriminator between a finished query (5) and an abandoned manipulation (4) is
    cur_problem, read from state — never inferred from message text. A query never sets it.
    """
    last = state["messages"][-1]
    if getattr(last, "tool_calls", None):
        return "tools"
    if state.get("cur_plan") is not None:
        return "running"
    if state.get("no_plan_count", 0) > 0:
        return "emergency"
    if state.get("cur_problem") is not None:
        return "recover"
    return "idle"

def route_from_running(state:AgentState)->str:
    """Map the phase set by running_node to the next node. 'fault' is wired to idle
    in the edge table: a system error ends the task and returns to the prompt.
    """    
    phase = state.get("phase")
    if phase == "complete":
        return "idle"
    if phase == "replan":
        return "llm"
    if phase == "emergency":
        return "emergency"
    return "fault"

def route_from_tools(state:AgentState)->str:
    """Guard the planning loop: once MAX_NO_PLAN cycles have failed to yield a
    solvable plan, escalate to emergency instead of letting the LLM retry forever.
    """    
    if state.get("no_plan_count",0) >= MAX_NO_PLAN:
        return "emergency"
    return "llm"

def route_from_recover(state: AgentState) -> str:
    """Route out of the recovery node, based on the phase it set.

    - fault -> idle : the incomplete-flow cap (MAX_INCOMPLETE) was exceeded; give up and return to
                      the prompt, reusing the existing fault path.
    - else  -> llm  : a scenario-specific nudge was issued; let the model try again.

    The MAX_INCOMPLETE cap makes the llm <-> recover loop safe: without it, a structurally
    incapable model (e.g. the 3B) would bounce between the two forever.
    """
    return "fault" if state.get("phase") == "fault" else "llm"

builder = StateGraph(AgentState, context_schema=AgentContext)

builder.add_node("idle",idle_node)
builder.add_node("llm",llm_node)
builder.add_node("tools",ToolNode(tools))
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
    "running":"running",
    "emergency":"emergency",
    "recover":"recover"
})
builder.add_conditional_edges("tools", route_from_tools, {
    "llm":"llm",
    "emergency":"emergency"
})

builder.add_conditional_edges("recover", route_from_recover, {
    "llm":"llm",
    "fault":"idle"
})

builder.add_conditional_edges("running", route_from_running, {
    "idle":"idle",
    "llm":"llm",
    "emergency":"emergency",
    "fault":"idle"
})
builder.add_edge("emergency","idle")



graph = builder.compile(checkpointer=InMemorySaver())

