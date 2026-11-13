"""Per-repetition tool-call counters (troubleshooting only).

For each task repetition it counts, per tool name:
  in_thinking : LLM turns with no parsed tool call but a <tool_call> inside the reasoning
  parsed      : tool calls the server returned to the agent
  executed    : tools actually run by the ToolNode
Only LLM calls made by the "llm" node are counted (the summary call is not).
"""
import re
from collections import Counter

from langchain_core.callbacks import BaseCallbackHandler

_FUNC = re.compile(r"<function=([\w-]+)")


class ToolCounter(BaseCallbackHandler):

    def __init__(self) -> None:
        self._llm_runs = set()
        self.reset()

    def reset(self) -> None:
        self.turns = 0
        self.in_thinking = Counter()
        self.parsed = Counter()
        self.executed = Counter()

    def on_chat_model_start(self, serialized, messages, *, run_id, metadata=None, **kwargs):
        if (metadata or {}).get("langgraph_node") == "llm":
            self._llm_runs.add(run_id)

    def on_llm_end(self, response, *, run_id, **kwargs):
        if run_id not in self._llm_runs:
            return
        self._llm_runs.discard(run_id)
        self.turns += 1
        msg = response.generations[0][0].message
        calls = getattr(msg, "tool_calls", None) or []
        for tc in calls:
            self.parsed[tc["name"]] += 1
        reasoning = msg.additional_kwargs.get("reasoning_content") or ""
        if not calls and "<tool_call>" in reasoning:
            for name in _FUNC.findall(reasoning) or ["?"]:
                self.in_thinking[name] += 1

    def on_llm_error(self, error, *, run_id, **kwargs):
        self._llm_runs.discard(run_id)

    def on_tool_start(self, serialized, input_str, **kwargs):
        name = (serialized or {}).get("name") or kwargs.get("name") or "?"
        self.executed[name] += 1

    def report(self) -> str:
        def fmt(c):
            return ", ".join(f"{k}={v}" for k, v in sorted(c.items())) or "0"
        return (f"LLM turns: {self.turns} | in thinking: {fmt(self.in_thinking)} | "
                f"parsed: {fmt(self.parsed)} | executed: {fmt(self.executed)}")