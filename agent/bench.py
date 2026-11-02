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
    problem         entry in planning, with cur_problem          -> generated problem
    planning_result exit from planning, with planning_status     -> attempts, valid problems
    task_end        transition to idle/emergency, with origin    -> t_end, closing reason"""

    def __init__(self, path: str):
        self.path = path
        self._open = None          # label of the repetition whose task_start was written
        self._last_node = None     # graph nodes run one at a time: the previous one is the origin
        self._planning_runs = set()

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
        elif node == "planning":
            self._planning_runs.add(run_id)
            self._write("problem", problem=inputs.get("cur_problem"))
        elif node in ("idle", "emergency") and self._open == label:
            self._open = None
            self._write("task_end", node=node, origin=origin,
                        phase=inputs.get("phase"), step_count=inputs.get("step_count"))

    def on_chain_end(self, outputs, *, run_id, **kwargs):
        if run_id in self._planning_runs:
            self._planning_runs.discard(run_id)
            if label is not None:
                self._write("planning_result", planning_status=outputs.get("planning_status"),
                            no_plan_count=outputs.get("no_plan_count"))