"""Benchmark instrumentation: names each task repetition and records, through a LangChain
callback, the events needed by the metrics. Active only when BENCH_CATEGORY is set."""

import json
import os
import time
from datetime import datetime

from langchain_core.callbacks import BaseCallbackHandler

label = None                     # label of the current repetition
_prefix = None
_rep = 0


def setup(approach: str):
    """Build the session prefix from the environment and return the recorder, or None if disabled."""
    global _prefix
    category = os.environ.get("BENCH_CATEGORY")
    if not category:
        return None
    model = os.environ.get("VLLM_MODEL", "Qwen3.5-4B").split("-")[1]   # Qwen3.5-4B -> 4B
    _prefix = f"{approach}-{model}-{category}-{datetime.now():%Y%m%dT%H%M%S}"
    out_dir = os.environ.get("BENCH_DIR", "bench_results")
    os.makedirs(out_dir, exist_ok=True)
    return BenchRecorder(os.path.join(out_dir, f"{_prefix}.jsonl"))


def next_label(prompt, user_input: str):
    """Called by main.py before resuming the graph: a new repetition starts on every task
    submitted at the idle prompt. Emergency answers and 'exit' are not repetitions."""
    global label, _rep
    if _prefix is None:
        return None
    if str(prompt).startswith("EMERGENCY") or user_input.strip().lower() == "exit":
        label = None
    else:
        _rep += 1
        label = f"{_prefix}-{_rep}"
    return label


class BenchRecorder(BaseCallbackHandler):
    """Writes one JSON line per event of the current repetition:
    task_start      first transition to llm                      -> t_start
    dispatch        start of the dispatch tool, with its command -> ROS sequence
    dispatch_result end of the dispatch tool, with its outcome   -> blocked command, rounds
    task_end        transition to idle/emergency, with origin    -> t_end, closing reason"""

    DISPATCH_ARGS = ("command", "kind", "pose", "from_node", "to_node", "close", "node", "shape", "color")

    def __init__(self, path: str):
        self.path = path
        self._open = None          # label of the repetition whose task_start was written
        self._last_node = None     # graph nodes run one at a time: the previous one is the origin
        self._dispatch_runs = set()

    def _write(self, event: str, **data):
        rec = {"label": label, "event": event, "t_wall": time.time(), "t_mono": time.perf_counter(), **data}
        with open(self.path, "a") as f:
            f.write(json.dumps(rec) + "\n")

    def on_chain_start(self, serialized, inputs, *, run_id, metadata=None, **kwargs):
        node = (metadata or {}).get("langgraph_node")
        if node is None or kwargs.get("name") != node:
            return                                   # inner runnables of a node, not the node itself
        origin, self._last_node = self._last_node, node
        if label is None:
            return
        if node == "llm" and self._open != label:
            self._open = label
            self._write("task_start")
        elif node in ("idle", "emergency") and self._open == label:
            self._open = None
            self._write("task_end", node=node, origin=origin,
                        phase=inputs.get("phase"), step_budget=inputs.get("step_budget"))

    def on_tool_start(self, serialized, input_str, *, run_id, inputs=None, **kwargs):
        name = (serialized or {}).get("name") or kwargs.get("name")
        if name != "dispatch" or label is None:
            return
        self._dispatch_runs.add(run_id)
        args = {k: v for k, v in (inputs or {}).items() if k in self.DISPATCH_ARGS}   # drops the injected runtime
        self._write("dispatch", args=args)

    def on_tool_end(self, output, *, run_id, **kwargs):
        if run_id in self._dispatch_runs:
            self._dispatch_runs.discard(run_id)
            if label is not None:
                self._write("dispatch_result", outcome=str(getattr(output, "content", output)))