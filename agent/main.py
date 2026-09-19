import threading
import rclpy

from rclpy.executors import MultiThreadedExecutor
from langgraph.types import Command
from langchain_core.messages import AIMessage, ToolMessage, HumanMessage
from rich.console import Console
from rich.text import Text
from rich.syntax import Syntax
from rich.markup import escape

from agent_graph import graph
from agent_context import AgentContext

from plansys2_lib.problem_expert import ProblemExpert
from plansys2_lib.domain_expert import DomainExpert
from plansys2_lib.planner import Planner
from plansys2_lib.scene_observer import SceneObserver
from plansys2_lib.executor import Executor
#from plansys2_lib.arm_commander import ArmCommander


console = Console()

USER_NODES = {"idle","emergency"}
#MAX_RESULT_LEN = 300

def print_message(msg, node):
    if isinstance(msg, HumanMessage):
        if node not in USER_NODES:           # system messages: replan, recover
            console.print(Text.assemble(("\nℹ️  ", "bold yellow"), (str(msg.content), "yellow")))
    elif isinstance(msg, ToolMessage):
        text = str(msg.content)
#        if len(text) > MAX_RESULT_LEN:
#            text = text[:MAX_RESULT_LEN] + " ..."
        console.print(Text.assemble(("   ↳ ", "green"), text))
    elif isinstance(msg, AIMessage):
        if msg.content:
            console.print(Text.assemble(("\n🤖 ", "bold blue"), str(msg.content)))
        for tc in msg.tool_calls:
            console.print(Text.assemble(("\n🔧 ", "bold cyan"), (tc["name"], "bold cyan")))
            for value in tc["args"].values():
                if tc["name"] == "set_problem":
                    # PDDL exactly as the LLM wrote it, with syntax highlighting only
                    console.print(Syntax(str(value), "lisp", background_color="default", word_wrap=True))
                else:                
                    console.print(Text(str(value)))

def run_streaming(payload, config, context):
    """Run the graph, printing each message as soon as a node adds it to the history.
    Returns the Interrupt if the graph stopped on an interrupt, otherwise None."""
    interrupt = None
    with console.status("Working", spinner="simpleDotsScrolling"):
        for chunk in graph.stream(payload, config=config, context=context, stream_mode="updates"):
            if "__interrupt__" in chunk:
                interrupt = chunk["__interrupt__"][0]
                continue
            for node, update in chunk.items():
                # ToolNode returns a list of updates when several tool calls return a Command
                for upd in (update if isinstance(update, list) else [update]):
                    if isinstance(upd, dict):
                        for msg in upd.get("messages", []):
                            print_message(msg, node)
    return interrupt

def main()->None:
    rclpy.init()

    problem_client = ProblemExpert()
    domain_client = DomainExpert()
    planner_client = Planner()
    scene_client = SceneObserver()
    executor_client = Executor()
#    go_home_client = ArmCommander()

    # The PlanSys2 clients spin on a MultiThreaded executor in a background daemon
    # thread, so they keep servicing futures while the graph runs on the main thread.
    # This is what lets PlanSys2ClientBase._call_sync block on a response without
    # deadlocking: this executor completes the very future it is waiting on.

    executor = MultiThreadedExecutor()
    executor.add_node(problem_client)
    executor.add_node(domain_client)
    executor.add_node(planner_client)
    executor.add_node(scene_client)
    executor.add_node(executor_client)
#    executor.add_node(go_home_client)

    spint_thread = threading.Thread(target=executor.spin, daemon=True)
    spint_thread.start()

    context = AgentContext(
        problem_client = problem_client,
        domain_client = domain_client,
        scene_client = scene_client,
        planner_client = planner_client,
        executor_client = executor_client
#        home_pos_client=go_home_client
    )

    config = {"configurable" : {"thread_id" : "1"}}

    state = {
        "messages" : [],
        "cur_problem" : None,
        "cur_plan":None,
        "phase" : "idle",
        "replan_count": 0,
        "no_plan_count": 0
    }

    try:
        # Human-in-the-loop driver: the graph runs until it hits an interrupt (the idle
        # or emergency prompt), returns it, and we resume with the user's reply via
        # Command(resume=...). thread_id keys the checkpointer to this one session.

        interrupt = run_streaming(state, config, context)     
        while interrupt is not None:
            user_input = console.input(
                f"\n[bold yellow]💬 {escape(str(interrupt.value))}[/]\n> "
            )
            interrupt = run_streaming(Command(resume=user_input), config, context)
        console.print("\nAgent stopped")

    finally:
        executor.shutdown()
        spint_thread.join(timeout=5.0)
        problem_client.destroy_node()
        domain_client.destroy_node()
        planner_client.destroy_node()
        scene_client.destroy_node()
        executor_client.destroy_node()
#        go_home_client.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()