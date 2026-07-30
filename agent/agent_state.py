from typing import TypedDict, Annotated, Literal, Optional, Sequence
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from agent_types import PlanStep

class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]
    cur_problem:Optional[str]
    cur_plan: Optional[list[PlanStep]]
    # found_plan:Optional[bool]
    phase: Literal["idle","running","complete","replan", "emergency", "fault"]
    replan_count : int
    no_plan_count : int