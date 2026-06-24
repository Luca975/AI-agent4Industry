import threading
from rclpy.node import Node
from rclpy.callback_groups import ReentrantCallbackGroup

class PlanSys2ClientBase(Node):
    
    def __init__(self, node_name:str) -> None:
        super().__init__(node_name)
        self.cb_group = ReentrantCallbackGroup()

    def _call_sync(self, client, req, timeout_sec:float):

        if not client.wait_for_service(timeout_sec=timeout_sec):
            self.get_logger().error(
                f"Service {client.srv_name} not available after {timeout_sec}s"
            )
            return None
        future = client.call_async(req)
        done = threading.Event()
        future.add_done_callback(lambda _f: done.set())

        if not done.wait(timeout_sec):
            self.get_logger().error(
                f"Timeout waiting for response from {client.srv_name}"
            )
            return None
        return future.result()