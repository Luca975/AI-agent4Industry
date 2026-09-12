from typing import TypedDict, Annotated, Literal, Optional, Sequence
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

class AgentState(TypedDict):
    """Graph state, checkpointed by InMemorySaver and threaded through every node.
    
    Holds only serializable working data. Live ROS clients are NOT here; they are
    injected separately as AgentContext"""

    messages: Annotated[Sequence[BaseMessage], add_messages]
    phase: Literal["idle","running","complete", "emergency"]
    step_budget : int                                                          # LLM turns left for this task; hits emergency at 0