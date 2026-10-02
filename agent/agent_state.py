from typing import TypedDict, Annotated, Literal, Optional, Sequence
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from agent_types import PlanStep

class AgentState(TypedDict):
    """Graph state, checkpointed by InMemorySaver and threaded through every node.
    
    Holds only serializable working data. Live ROS clients are NOT here; they are
    injected separately as AgentContext"""

    messages: Annotated[Sequence[BaseMessage], add_messages]
    cur_problem:Optional[str]                                                   # PDDL problem being built this cycle; None between tasks
    cur_plan: Optional[list[PlanStep]]                                          # plan returned by the planner, ready to run; None until found
    # found_plan:Optional[bool]
    phase: Literal["idle","running","complete","replan", "emergency", "fault"]
    replan_count : int                                                          # obstacle hit DURING execution (a move got blocked); capped by MAX_REPLAN
    no_plan_count : int                                                         # planning cycles that produces no solvable plan; capped by MAX_NO_PLAN
    planning_status: Optional[Literal["pending", "rejected", "no_plan",
                                      "solved"]]                                # status of cur_problem; "pending" = set by set_problem, waiting for planning_node; None = no problem
    incomplete_flow_count: int                                                  # incomplete manipulation flows left by the LLM (problem setted, not carried to a plan); capped by MAX_INCOMPLETE
    task_start: int                                                             # messages' index where the new task begins; the history of the previous tasks is not sended to the LLM
    last_summary: Optional[str]                                                 # Last task's summary
    step_count: int                                                             # LLM turns spent on the current task; capped by MAX_STEPS