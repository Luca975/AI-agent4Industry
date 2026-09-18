from langchain_core.tools import tool
from langgraph.prebuilt import ToolRuntime
from langchain_core.messages import ToolMessage
from agent_context import AgentContext
from langgraph.types import Command


@tool
def observe_scene(runtime: ToolRuntime[AgentContext]) -> str:
    """Return the objects currently in the scene and the transit graph (topology),
    in symbolic form. Use it whenever you need to know what is present, where things
    are, their colors, or how locations are connected — both to ANSWER QUESTIONS about
    the scene and to build a PDDL problem for a manipulation task."""

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
        # Pre-compose the topology as verbatim :init snippets so the LLM copies it
        # rather than deriving it: (connected a b) for every arc, plus (clean_path a b)
        # only when that segment is currently human-free. A missing clean_path is how a
        # blocked arc is signalled to the planner.        
        arc_lines = []
        for from_node, to_node, clear in paths:
            fact = f"(connected {from_node} {to_node})"
            if clear:
                fact += f" (clean_path {from_node} {to_node})"
            arc_lines.append(fact);

        out += ("\n\nGraph facts (copy these verbatim into :init):\n"
                + "\n".join(arc_lines))

    return out

@tool
def get_domain(runtime: ToolRuntime[AgentContext]) -> str:
    """Return the current PDDL domain: types, predicates and actions. Use it to ANSWER
    QUESTIONS about what the robot can do (its actions) or about the domain structure,
    and to build a PDDL problem consistent with the domain."""

    success, domain, info = runtime.context.domain_client.get_domain()
    if success:
        return domain
    return f"Error while reading the domain: {info}"


@tool
def send_problem(runtime: ToolRuntime[AgentContext]) -> Command:
    """Load the generated PDDL problem in the system. Use this after generating the problem; it is read from the agent state"""

    problem_str = runtime.state.get("cur_problem")
    if not problem_str:
        return Command(update={
            "messages":[ToolMessage(content="No problem generated yet", tool_call_id=runtime.tool_call_id)]
        })
    success, info = runtime.context.problem_client.add_problem(problem_str)
    if success:
        return Command(update={
            "load_status": "ok",
            "messages":[ToolMessage(content="Problem sent successfully", tool_call_id=runtime.tool_call_id)]
        })
    return Command(update={
        "load_status": "failed",
        "messages":[ToolMessage(content=f"Error while sending the problem: {info}", tool_call_id=runtime.tool_call_id)]
    })

@tool
def clear_problem(runtime: ToolRuntime[AgentContext]) -> Command:
    """Clear the current problem knowledge in the system. Use this when you want to reset the problem knowledge"""

    success, info = runtime.context.problem_client.clear_problem_knowledge()
    if success:
        return Command(update={
            "cur_problem": None,
            "load_status": None,
            "messages":[ToolMessage(content="Problem knowledge cleared successfully", tool_call_id=runtime.tool_call_id)]
        })
    return Command(update={
        "messages":[ToolMessage(content=f"Error while clearing the problem knowledge: {info}", tool_call_id=runtime.tool_call_id)]
    })

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
        # Bump the planning-loop guard: route_from_tools escalates to emergency once
        # this reaches MAX_NO_PLAN, and route_from_llm uses it as the deterministic
        # escape when the LLM stops calling tools without a plan. Reset to 0 on success        
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
            "load_status": None,
            "messages":[
                ToolMessage(
                    content="Problem stored in the agent state.",
                    tool_call_id=runtime.tool_call_id,
                )
            ],
        }
    )

tools = [observe_scene, get_domain, send_problem, clear_problem, get_plan, set_problem]