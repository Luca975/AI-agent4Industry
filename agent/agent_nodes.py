import os
from langchain_core.messages import SystemMessage,HumanMessage,AIMessage
#from langchain_anthropic import ChatAnthropic
from langchain_openai import ChatOpenAI
from langgraph.types import interrupt
from langgraph.runtime import Runtime

from agent_state import AgentState
from agent_context import AgentContext
from agent_tools import tools
from agent_prompts import SYSTEM_PROMPT
import bench

MAX_REPLAN = 3
MAX_NO_PLAN = 3
MAX_INCOMPLETE = 2
MAX_STEPS = 20

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

#llm = ChatAnthropic(model="claude-sonnet-4-6", temperature=0).bind_tools(tools)
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
        "planning_status": None,
        "incomplete_flow_count": 0,
        "task_start": len(state["messages"]),
        **summary_update,
        "step_count": 0
    }

def llm_node(state:AgentState)->AgentState:

    system = SYSTEM_PROMPT
    if state.get("last_summary"):
        system += f"\n\nPrevious task: {state['last_summary']}"
    curr_prompt = [SystemMessage(content=system)]

    curr_prompt += state["messages"][state.get("task_start",0):]
    #messages = [SystemMessage(content=SYSTEM_PROMPT)]+state["messages"]
    response = llm.invoke(curr_prompt,
                          extra_headers={"X-Request-Id": bench.label} if bench.label else None)
    return {"messages":[response],
            "step_count": state.get("step_count",0)+1}

def planning_node(state: AgentState, runtime:Runtime[AgentContext])->AgentState:

    ctx = runtime.context
    problem = (state.get("cur_problem") or "").strip()
    count = state.get("no_plan_count", 0) + 1
    attempt = f"(attempt {count}/{MAX_NO_PLAN})"

    if not problem:
        return {
            "messages": [HumanMessage(content=(
                f"NO PROBLEM RECEIVED {attempt}: set_problem was called with an empty string.\n"
                "Write the complete PDDL problem (objects, initial state, goal) from the current "
                "scene and domain.\n"
                "Next: call set_problem with the complete problem."))],
            "planning_status": "rejected",
            "no_plan_count": count,
        }

    opened, closed = problem.count("("), problem.count(")")
    if opened != closed:
        return {
            "messages": [HumanMessage(content=(
                f"PROBLEM REJECTED {attempt}.\n"
                f"Error: unbalanced parentheses ({opened} opened, {closed} closed).\n"
                "Next: call set_problem with the complete corrected problem."))],
            "planning_status": "rejected",
            "no_plan_count": count,
        }

    ok, info = ctx.problem_client.clear_problem_knowledge()
    if not ok:
        return {"messages": [AIMessage(content=f"System error while clearing the previous problem: {info}.")],
                "phase": "fault"}

    ok, info = ctx.problem_client.add_problem(problem)
    if not ok:
        return {
            "messages": [HumanMessage(content=(
                f"PROBLEM REJECTED {attempt}.\n"
                f"Error: {info}\n"
                "The problem is not valid PDDL for the current domain: the error could be related EITHER to "
                "undeclared objects, types or predicates not defined in the domain OR you missed some declaration(s) in "
                "the 'objects:' section or 'init:' section. Check the RULES again and RE-OBSERVE the scene if needed\n"
                "Next: call set_problem with the complete corrected problem."))],
            "planning_status": "rejected",
            "no_plan_count": count,
        }

    ok, domain, info = ctx.domain_client.get_domain()
    if not ok:
        return {"messages": [AIMessage(content=f"System error while reading the domain: {info}.")],
                "phase": "fault"}
 
    ok, plan, info = ctx.planner_client.get_plan(domain, problem)
    if not ok:
        return {
            "messages": [HumanMessage(content=(
                f"NO PLAN FOUND {attempt}.\n"
                f"Planner output: {info}\n"
                "The problem is valid, but the goal is not reachable from the initial state. "
                "Compare the initial state and the goal with the latest scene observation.\n"
                "Do not add facts the scene does not report just to make the goal reachable.\n"
                "Next: if you find a mistake, call set_problem with the corrected problem; "
                "otherwise call observe_scene, the scene may have changed."))],
            "planning_status": "no_plan",
            "no_plan_count": count,
        }
 
    return {
        "messages": [AIMessage(content="Plan found. Executing it.")],
        "cur_plan": plan,
        "planning_status": "solved",
        "no_plan_count": 0,
    }

def emergency_node(state: AgentState) -> AgentState:
    user_input = interrupt(
        "EMERGENCY: planning/replanning attempts expired or a station is blocked! "
        "Check the area for safety reasons and press space to restart")

    return {
        "messages": [HumanMessage(content=user_input)],
        "phase": "idle",
        "cur_problem": None,
        "cur_plan": None,
        "replan_count": 0,
        "no_plan_count": 0,
        "planning_status": None,
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
                    f"Re-observe the scene and build a new problem "
                    f"(replan attempt {count}/{MAX_REPLAN})."))],
                "phase": "replan",
                "replan_count": count,
                "cur_plan" : None,
                "cur_problem" : None,
                "planning_status": None
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
    """planning_node rejected the problem or found no plan, and the LLM answered in words
    instead of calling set_problem again. Nudge it back, up to MAX_INCOMPLETE times, then
    degrade to fault."""
 
    count = state.get("incomplete_flow_count",0)+1
 
    if count > MAX_INCOMPLETE:
        return {
            "messages": [AIMessage(content=("The model repeatedly stopped without submitting a valid problem."))],
            "phase":"fault",
            "incomplete_flow_count":count,
            "cur_problem":None,
            "cur_plan":None,
            "planning_status": None
        }
 
    if state.get("planning_status") == "no_plan":
        nudge = ("The task is not done: the last problem has no plan (see above). "
                 "Do not answer in text.\n"
                 "Next: call set_problem with a corrected problem, or observe_scene if the scene may have changed.")
    else:
        nudge = ("The task is not done: the last problem was rejected (see above). "
                 "Do not answer in text.\n"
                 "Next: call set_problem with the complete corrected problem.")
 
    return {
        "messages": [HumanMessage(content=nudge)],
        "phase": "idle",
        "incomplete_flow_count": count
    }