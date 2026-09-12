import threading
import rclpy

from rclpy.executors import MultiThreadedExecutor
from langgraph.types import Command

from agent_graph import graph
from agent_context import AgentContext
from agent_nodes import STEP_BUDGET

from ros_lib.scene_observer import SceneObserver
from ros_lib.niryo_driver import NiryoDriverClient

def main()->None:
    rclpy.init()

    scene_client = SceneObserver()
    driver_client = NiryoDriverClient()


    # The ROS clients spin on a MultiThreaded executor in a background daemon
    # thread, so they keep servicing futures while the graph runs on the main
    # thread. This is what lets _call_sync block on a response without deadlocking:
    # this executor completes the very future it is waiting on. It also drives
    # SceneObserver's /env/scene subscription, so object poses stay fresh.

    executor = MultiThreadedExecutor()
    executor.add_node(scene_client)
    executor.add_node(driver_client)

    spint_thread = threading.Thread(target=executor.spin, daemon=True)
    spint_thread.start()

    context = AgentContext(
        scene_client = scene_client,
        driver_client = driver_client
    )

    config = {"configurable" : {"thread_id" : "1"}}

    state = {
        "messages" : [],
        "phase" : "idle",
        "step_budget": STEP_BUDGET
    }

    try:
        # Human-in-the-loop driver: the graph runs until it hits an interrupt (the idle
        # or emergency prompt), returns it, and we resume with the user's reply via
        # Command(resume=...). thread_id keys the checkpointer to this one session.        
        result = graph.invoke(state, config=config, context=context)
        while "__interrupt__" in result:
            prompt = result["__interrupt__"][0].value
            user_input = input(f"\n{prompt}\n>")
            result = graph.invoke(
                Command(resume=user_input), config=config, context=context
            )
            for msg in result.get("messages",[]):
                msg.pretty_print() 
        print("\nAgent stopped")

    finally:
        executor.shutdown()
        spint_thread.join(timeout=5.0)
        scene_client.destroy_node()
        driver_client.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()