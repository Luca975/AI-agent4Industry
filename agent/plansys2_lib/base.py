import threading
from rclpy.node import Node
from rclpy.callback_groups import ReentrantCallbackGroup

class PlanSys2ClientBase(Node):

    """Base for the agent's PlanSys2 clients: a Node with a reentrant callback group
    and one blocking server-call helper
    
    The reentrant group is the load-bearing choice: these clients are called
    synchronously from inside other running callbacks, so the future's completion
    must be free to run while the caller is blocking waiting on it. A mutually-exclusive group would
    lead to a deadlock"""
    
    def __init__(self, node_name:str) -> None:
        super().__init__(node_name)
        self.cb_group = ReentrantCallbackGroup()

    def _call_sync(self, client, req, timeout_sec:float):
        """Call a service and block until the response; None on timeout or if unavailable
        
        Uses call_async + a threading.Event instead of spin_until_future_complete:
        the node already runs inside a (multi-threaded) executor, so it must not spin
        itself - it lets the running executor complete the future and only waits on it"""

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