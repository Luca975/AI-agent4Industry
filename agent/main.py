import threading
import rclpy

from rclpy.executors import MultiThreadedExecutor
from langgraph.types import Command

from agent_graph import graph
from agent_context import AgentContext

from plansys2_lib.problem_expert import ProblemExpert
from plansys2_lib.domain_expert import DomainExpert
from plansys2_lib.planner import Planner
from plansys2_lib.scene_observer import SceneObserver

def main()->None:
    rclpy.init()

    problem_client = ProblemExpert()
    domain_client = DomainExpert()
    planner_client = Planner()
    scene_client = SceneObserver()

    executor = MultiThreadedExecutor()
    executor.add_node(problem_client)
    executor.add_node(domain_client)
    executor.add_node(planner_client)
    executor.add_node(scene_client)

    spint_thread = threading.Thread(target=executor.spin, daemon=True)
    spint_thread.start()

    context = AgentContext(
        problem_client = problem_client,
        domain_client = domain_client,
        scene_client = scene_client,
        planner_client = planner_client
    )

    config = {"configurable" : {"thread_id" : "1"}}

    state = {
        "messages" : [],
        "cur_problem" : None,
        "phase" : "idle"
    }

    try:
        result = graph.invoke(state, config=config, context=context)
        while "__interrupt__" in result:
            prompt = result["__interrupt__"][0].value
            user_input = input(f"\n{prompt}>")
            result = graph.invoke(
                Command(resume=user_input), config=config, context=context
            )
            for msg in result.get("messages",[]):
                msg.pretty_print() 
        print("\nAgent stopped")

    finally:
        executor.shutdown()
        problem_client.destroy_node()
        domain_client.destroy_node()
        planner_client.destroy_node()
        scene_client.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()