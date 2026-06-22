from agent_state import AgentState
from langchain_core.tools import tool



@tool
def clear_problem_knowledge_base(state:AgentState):
    """This tool clears the problem knowledge base in the Problem_Expert node"""
    #if state['cur_problem'] is None:
    #    raise ValueError("No problem to clear")

@tool
def send_problem(state:AgentState):
    """This tool sends the PDDL problem to the Problem_Expert node"""
    #if state['cur_problem'] is None:
    #    raise ValueError("No problem to send")
   # elif 

tools = [send_problem, clear_problem_knowledge_base]