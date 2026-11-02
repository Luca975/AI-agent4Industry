import os
from langchain_core.messages import SystemMessage,HumanMessage
#from langchain_anthropic import ChatAnthropic
from langchain_openai import ChatOpenAI
from langgraph.types import interrupt
from langgraph.runtime import Runtime

from agent_state import AgentState
from agent_tools import tools
from agent_prompts import SYSTEM_PROMPT
import bench

STEP_BUDGET = 25

class ChatLLM(ChatOpenAI):
    def _create_chat_result(self, response, generation_info = None):
        result = super()._create_chat_result(response, generation_info)
        resp = response if isinstance(response, dict) else response.model_dump()
        for gen, choice in zip(result.generations, resp.get("choices", [])):
            msg = choice.get("message") or {}
            reasoning = msg.get("reasoning_content") or msg.get("reasoning")
            if reasoning:
                gen.message.additional_kwargs["reasoning_content"] = reasoning
        return result
    def _convert_chunk_to_generation_chunk(self, chunk, default_chunk_class, base_generation_info):
        gen = super()._convert_chunk_to_generation_chunk(chunk, default_chunk_class, base_generation_info)
        if gen is None:
            return None
        choices = chunk.get("choices") or []
        if choices:
            delta = choices[0].get("delta") or {}
            reasoning = delta.get("reasoning_content") or delta.get("reasoning")
            if reasoning:
                gen.message.additional_kwargs["reasoning_content"] = reasoning
        return gen

llm = ChatLLM(
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

# llm = ChatAnthropic(
#     model="claude-sonnet-4-6",
#     temperature=1,
#     thinking={"type": "enabled", "budget_tokens": 2000},
# ).bind_tools(tools)

# llm_base = ChatAnthropic(model="claude-sonnet-4-6", temperature=1)

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
    response = llm.invoke(messages,
                          extra_headers={"X-Request-Id": bench.label} if bench.label else None)
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