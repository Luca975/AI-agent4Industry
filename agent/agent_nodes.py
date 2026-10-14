from langchain_core.messages import SystemMessage,HumanMessage
from langchain_anthropic import ChatAnthropic
from langgraph.types import interrupt

from agent_state import AgentState
from agent_tools import tools
from agent_prompts import SYSTEM_PROMPT

STEP_BUDGET = 25

llm = ChatAnthropic(
    model="claude-sonnet-4-6",
    temperature=1,
    thinking={"type": "enabled", "budget_tokens": 2000},
).bind_tools(tools)

llm_base = ChatAnthropic(model="claude-sonnet-4-6", temperature=1)

SYSTEM_PROMPT = SYSTEM_PROMPT

def idle_node(state: AgentState)-> AgentState:
    """Prompt the user and start the next task"""

    phase = state.get("phase", "idle")
    summary_update = {}
    if phase == "complete":
        task_msgs = state["messages"][state.get("task_start", 0):]
        summary = llm_base.invoke([
            SystemMessage(content="Summarize in one sentence, max 30 words: the task and its outcome."),
            *task_msgs,
        ])
        summary_update["last_summary"] = summary.content

    prompt = "Task complete. What would you like to do next?" if phase == "complete" \
        else "What would you like to do?"

    user_input = interrupt(prompt)

    return {
        "messages": [HumanMessage(content=user_input)],
        "phase": "idle",
        "step_budget": STEP_BUDGET,
        "task_start": len(state["messages"]),   # new task starts after this point
        **summary_update,
    }


def llm_node(state:AgentState)->AgentState:
    system = SYSTEM_PROMPT
    if state.get("last_summary"):
        system += f"\n\nPrevious task: {state['last_summary']}"

    messages = [SystemMessage(content=system)] + state["messages"][state.get("task_start", 0):]
    response = llm.invoke(messages)
    return {
        "messages": [response],
        "step_budget": state.get("step_budget", STEP_BUDGET) - 1,
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