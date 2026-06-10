from typing import TypedDict, Annotated, Literal, Optional, Sequence
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]
    cur_problem:Optional[str]
    found_plan:Optional[bool]
    phase: Literal["idle","running","complete","failed"]