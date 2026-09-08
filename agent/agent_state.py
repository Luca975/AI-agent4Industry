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