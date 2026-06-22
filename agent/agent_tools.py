from langchain_core.tools import tool
from langgraph.prebuilt import ToolRuntime
from agent_context import AgentContext


@tool
def observe_scene(runtime: ToolRuntime[AgentContext]) -> str:
    """Observe the current scene and return the detected objects in symbolic form,
    ready to build the PDDL problem. Use this tool at the beginning, before generating the problem,
    to know which objects are present, their type and location."""

    success, objects, info = runtime.context.scene_client.observe_scene()
    if not success:
        return f"Error while observing the scene: {info}"
    if not objects:
        return "Empty scene"
    

    lines = []
    for name,type_, location in objects:
        if location:
            lines.append(f"{name} ({type_}) -> {location}")
        else:
            lines.append(f"{name} ({type_})")
    
    return "Objects in the scene:\n" + "\n".join(lines)


@tool
def get_domain(runtime: ToolRuntime[AgentContext]) -> str:
    """Read the current PDDL domain. Use this when you need to know the domain to generate a coherent problem"""

    success, domain, info = runtime.context.domain_client.get_domain()
    if success:
        return domain
    return f"Error while reading the domain: {info}"


@tool
def send_problem(runtime: ToolRuntime[AgentContext]) -> str:
    """Load the generated PDDL problem in the system. Use this after generating the problem; it is read from the agent state"""

    problem_str = runtime.state.get("cur_problem")
    if not problem_str:
        return "No problem generated yet"
    success, info = runtime.context.problem_client.add_problem(problem_str)
    if success:
        return "Problem sent successfully"
    return f"Error while sending the problem: {info}"

@tool
def clear_problem(runtime: ToolRuntime[AgentContext]) -> str:
    """Clear the current problem knowledge in the system. Use this when you want to reset the problem knowledge"""

    success, info = runtime.context.problem_client.clear_problem_knowledge()
    if success:
        return "Problem knowledge cleared successfully"
    return f"Error while clearing the problem knowledge: {info}"

@tool
def get_plan(runtime: ToolRuntime[AgentContext]) -> str:
    """Ask the planner whether a plan exists for the current domain and problem.
    Use this after loading the problem, to verify if it is solvable"""

    ok_domain, domain, info = runtime.context.domain_client.get_domain()
    if not ok_domain:
        return f"Error while reading the domain: {info}"
    
    problem_str = runtime.state.get("cur_problem")
    if not problem_str:
        return "No problem generated yet"
    
    success, info = runtime.context.planner_client.get_plan(domain, problem_str)
    if success:
        return "Plan exists for the current domain and problem"
    return f"No plan found: {info}"

tools = [observe_scene, get_domain, send_problem, clear_problem, get_plan]