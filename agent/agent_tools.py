from langchain_core.tools import tool
from langgraph.prebuilt import ToolRuntime
from langchain_core.messages import ToolMessage
from agent_context import AgentContext
from langgraph.types import Command


@tool
def observe_scene(runtime: ToolRuntime[AgentContext]) -> str:
    """Observe the current scene and return the detected objects and the graph of transit path in symbolic form,
    ready to build the PDDL problem. Use this tool at the beginning, before generating the problem."""

    success, objects, paths, info = runtime.context.scene_client.observe_scene()
    if not success:
        return f"Error while observing the scene: {info}"
    if not objects:
        return "Empty scene"
    

    lines = []
    for name,type_, location, held, color in objects:
        descr = f"{name} ({type_}"
        if color:
            descr += f", {color}"
        descr += ")"

        if held:
            descr += " -> held by the arm"
        elif location:
            descr += f" -> {location}"
        
        lines.append(descr)
    
    out = "Objects in the scene:\n" + "\n".join(lines)

    if paths:
        arc_lines = []
        for from_node, to_node, clear in paths:
            fact = f"(connected {from_node} {to_node}) "
            if clear:
                fact += f"(clean_path {from_node} {to_node})"
            arc_lines.append(fact);

        out += ("\n\nGraph facts (copy these verbatim into :init):\n"
                + "\n".join(arc_lines))

    return out

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
def get_plan(runtime: ToolRuntime[AgentContext]):
    """Ask the planner whether a plan exists for the current domain and problem.
    Use this after loading the problem, to verify if it is solvable"""

    ok_domain, domain, info = runtime.context.domain_client.get_domain()
    if not ok_domain:
        return f"Error while reading the domain: {info}"
    
    problem_str = runtime.state.get("cur_problem")
    if not problem_str:
        return "No problem generated yet"
    
    success, plan, info = runtime.context.planner_client.get_plan(domain, problem_str)

    if not success:
        count = runtime.state.get("no_plan_count",0) + 1
        return Command(
            update={
                "no_plan_count":count,
                "messages":[
                    ToolMessage(
                        content=f"No plan found: {info}",
                        tool_call_id=runtime.tool_call_id
                    )
                ]
            }
        )
    
    return Command(
        update={
            "cur_plan": plan,
            "no_plan_count": 0,
            "messages":[
                ToolMessage(
                    content="Plan found: the problem is solvable",
                    tool_call_id=runtime.tool_call_id
                )
            ]
        }
    )

@tool
def set_problem(problem_str:str, runtime: ToolRuntime[AgentContext]) -> Command:
    """Store the generated problem in the agent state, to be later sent to the system with the send_problem tool.
    Pass the full PDDL problem as a single string. Call this once you have written the problem"""

    return Command(
        update={
            "cur_problem": problem_str,
            "messages":[
                ToolMessage(
                    content="Problem stored in the agent state.",
                    tool_call_id=runtime.tool_call_id,
                )
            ],
        }
    )

tools = [observe_scene, get_domain, send_problem, clear_problem, get_plan, set_problem]