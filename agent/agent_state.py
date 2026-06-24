from typing import TypedDict, Annotated, Literal, Optional, Sequence
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from plansys2_msgs.msg import Plan

class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]
    cur_problem:Optional[str]
    cur_plan: Optional[Plan]
    # found_plan:Optional[bool]
    phase: Literal["idle","running","complete","failed"]