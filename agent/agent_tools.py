from langchain_core.tools import tool
from langgraph.prebuilt import ToolRuntime

from niryo_world_interfaces.msg import SceneObject
from agent_context import AgentContext


def _fmt(pose):
    """Render a pose list as '[x, y, z, r, p, yaw]', or 'unavailable' if None."""
    return "[" + ", ".join(f"{v:.4f}" for v in pose) + "]" if pose else "unavailable"


@tool
def dispatch(
    command: str,
    runtime: ToolRuntime[AgentContext],
    kind: str | None = None,
    pose: list[float] | None = None,
    from_node: str | None = None,
    to_node: str | None = None,
    close:bool | None = None,
    node: str | None = None
    )->str:
    """Send one command to the robot arm and report its outcome.

    command="move": drive the arm to a cartesian pose. The pose is copied from
      observe_scene. A move needs a kind:
        kind="transit": travel between stations along a graph arc. Give pose (the
          destination node's pose), from_node (where the arm is now) and to_node
          (the destination). The arc is watched for humans throughout.
        kind="approach": reach onto an object inside the station you are at. Give
          pose (the object's pose) and node (the station). The node is checked for
          humans first.

    command="grip": operate the gripper. Give close (true to grasp, false to
      release) and node (the station you are at). The node is checked for humans
      first.

    To pick: transit to the piece's station, approach the piece's pose, grip
    close=true. To place: transit to the destination station, approach the drop
    pose, grip close=false.

    Returns a short outcome string: "success: ..." on success, or a description of
    the obstacle or error otherwise. Read it and decide what to do next."""

    driver = runtime.context.driver_client

    if command == "move":
        # A move's required node args depend on its kind, so validate per kind.
        # A malformed call is reported as a readable outcome.
        if kind == "transit":
            missing = [n for n, v in (("pose", pose), ("from_node", from_node), ("to_node", to_node)) if v is None]
            if missing:
                return f"move/transit requires {', '.join(missing)}"
            if len(pose) != 6:
                return "pose must be [x, y, z, roll, pitch, yaw] (6 values)"
            ok, message = driver.move(pose, "transit", from_node=from_node, to_node=to_node)
        elif kind == "approach":
            missing = [n for n, v in (("pose", pose), ("node", node)) if v is None]
            if missing:
                return f"move/approach requires {', '.join(missing)}"
            if len(pose) != 6:
                return "pose must be [x, y, z, roll, pitch, yaw] (6 values)"
            ok, message = driver.move(pose, "approach", node=node)
        else:
            return f"move requires kind 'transit' or 'approach' (got '{kind}')"

    elif command == "grip":
        missing = [n for n, v in (("close", close), ("node", node)) if v is None]
        if missing:
            return f"grip requires {', '.join(missing)}"
        ok, message = driver.grip(close, node)

    else:
        return f"unknown command '{command}'; use 'move' or 'grip'"

    # Uniform outcome: success prefixed so the LLM tells it apart at a glance;
    # failures pass the client's own reason through unchanged.
    return f"success: {message}" if ok else message

@tool
def observe_scene(runtime: ToolRuntime[AgentContext]) -> str:
    """Observe the world: detected objects with their cartesian poses, the transit
    graph of nodes (each with a pose) and its arcs with the current free/blocked
    state. Poses are [x, y, z, roll, pitch, yaw]. Arc state is live: call this again
    whenever you need a fresh view before deciding your next move."""

    ok, objects, nodes, paths, info = runtime.context.scene_client.observe_scene()
    if not ok:
        return f"Error while observing the scene: {info}"
    if not objects and not nodes:
        return "Empty scene"

    piece_lines, arm_line = [], None
    for name, type_, location, held, color, pose in objects:
        if type_ == SceneObject.ROBOT:
            arm_line = f"{name} ({type_}) -> at {location or 'some_place'}"
            continue
        descr = f"{name} ({type_}" + (f", {color}" if color else "") + ")"
        if held:
            descr += " -> held by the arm"
        elif location:
            descr += f" -> at {location}"
        descr += f", pose {_fmt(pose)}"
        piece_lines.append(descr)

    node_lines = [f"{name} ({type_}): {_fmt(pose)}" for name, type_, pose in nodes]

    # Arcs arrive doubled (undirected, emitted both ways); collapse to one line
    # per unordered pair. clear is symmetric, so either direction wins.
    seen, arc_lines = set(), []
    for a, b, clear in paths:
        key = frozenset((a, b))
        if key in seen:
            continue
        seen.add(key)
        arc_lines.append(f"{a} <-> {b} : {'clear' if clear else 'BLOCKED'}")

    out = []
    if piece_lines:
        out.append("Objects:\n" + "\n".join(piece_lines))
    if arm_line:
        out.append("Arm:\n" + arm_line)
    if node_lines:
        out.append("Nodes (transit graph, pose [x, y, z, roll, pitch, yaw]):\n" + "\n".join(node_lines))
    if arc_lines:
        out.append("Arcs (free/blocked):\n" + "\n".join(arc_lines))
    return "\n\n".join(out)

tools = [observe_scene, dispatch]