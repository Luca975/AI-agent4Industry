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

tools = [observe_scene]