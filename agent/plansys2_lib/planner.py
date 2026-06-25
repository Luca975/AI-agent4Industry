# import rclpy
# from rclpy.node import Node

from plansys2_lib.base import PlanSys2ClientBase
from plansys2_msgs.srv import GetPlan
from agent_types import PlanStep
# from plansys2_msgs.msg import Plan

class Planner(PlanSys2ClientBase):

    def __init__(self)->None:
        super().__init__('agent_planner_client')
        self._get_plan_client = self.create_client(GetPlan, '/planner/get_plan', callback_group=self.cb_group)

    def get_plan(self, domain:str, problem:str, timeout_sec:float=15.0)->tuple[bool, list[PlanStep], str]:

        # client = self._get_plan_client
        # if not client.wait_for_service(timeout_sec=timeout_sec):
        #     info=f"Service {client.srv_name} not available after waiting for {timeout_sec} seconds"
        #     self.get_logger().error(info)
        #     return False, info
        req = GetPlan.Request()
        req.domain = domain
        req.problem = problem
        # future = client.call_async(req)
        # rclpy.spin_until_future_complete(self, future)
        # response = future.result()

        response = self._call_sync(self._get_plan_client, req, timeout_sec)

        if response is None:
            info=f"Service call to {self._get_plan_client.srv_name} failed"
            self.get_logger().error(info)
            return False, [], info
        if not response.success:
            info=f"Service call to {self._get_plan_client.srv_name} returned failure: {response.error_info}"
            self.get_logger().warn(info)
            return False, [], response.error_info
        
        plan : list[PlanStep] = [
            {"time": item.time, "action": item.action, "duration":item.duration} for item in response.plan.items
        ]


        return True,plan,response.error_info