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
    task_start: int                                                            # index in messages where the current task began
    last_summary: Optional[str]                                                # one-line summary of the previous task, injected next