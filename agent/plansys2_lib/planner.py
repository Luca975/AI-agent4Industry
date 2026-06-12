import rclpy
from rclpy.node import Node

from plansys2_msgs.srv import GetPlan

class Planner(Node):

    def __init__(self)->None:
        super().__init__('agent_planner_client')
        self._get_plan_client = self.create_client(GetPlan, '/planner/get_plan')

    def get_plan(self, domain:str, problem:str, timeout_sec:float=5.0)->tuple[bool, str]:

        client = self._get_plan_client
        if not client.wait_for_service(timeout_sec=timeout_sec):
            info=f"Service {client.srv_name} not available after waiting for {timeout_sec} seconds"
            self.get_logger().error(info)
            return False, info
        req = GetPlan.Request()
        req.domain = domain
        req.problem = problem
        future = client.call_async(req)
        rclpy.spin_until_future_complete(self, future)
        response = future.result()

        if response is None:
            info=f"Service call to {client.srv_name} failed"
            self.get_logger().error(info)
            return False, info
        if not response.success:
            info=f"Service call to {client.srv_name} returned failure: {response.error_info}"
            self.get_logger().warn(info)
            return False, response.error_info
        return True,""