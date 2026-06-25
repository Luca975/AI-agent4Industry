import threading

from rclpy.action import ActionClient
from plansys2_msgs.action import ExecutePlan
from plansys2_msgs.msg import Plan, PlanItem
from agent_types import PlanStep

from plansys2_lib.base import PlanSys2ClientBase

class Executor(PlanSys2ClientBase):

    def __init__(self)->None:
        super().__init__('agent_executor_client')
        self._execute_plan_client = ActionClient(
            self, ExecutePlan, '/execute_plan', callback_group=self.cb_group
        )
    
    @staticmethod
    def _to_ros_plan(plan_steps:list[PlanStep]) -> Plan:
        plan = Plan()
        for step in plan_steps:
            item = PlanItem()
            item.time = step["time"]
            item.action = step["action"]
            item.duration = step["duration"]
            plan.items.append(item)
        return plan

    def execute_plan(self, plan_steps:list[PlanStep], timeout_sec:float = 120.0)->tuple[bool, str]:

        if not self._execute_plan_client.wait_for_server(timeout_sec=5.0):
            info = "Action server /execute_plan not available"
            self.get_logger().error(info)
            return False,info
        
        goal = ExecutePlan.Goal()
        goal.plan = self._to_ros_plan(plan_steps)

        goal_done = threading.Event()
        goal_future = self._execute_plan_client.send_goal_async(goal)
        goal_future.add_done_callback(lambda _f: goal_done.set())

        if not goal_done.wait(timeout_sec):
            info = "Timeout waiting for goal acceptance from /execute_plan"
            self.get_logger().error(info)
            return False, info
        
        goal_handle = goal_future.result()
        if goal_handle is None or not goal_handle.accepted:
            info = "Goal rejected by /execute_plan"
            self.get_logger().error(info)
            return False, info
        
        result_done = threading.Event()
        result_future = goal_handle.get_result_async()
        result_future.add_done_callback(lambda _f: result_done.set())

        if not result_done.wait(timeout_sec):
            info = "Timeout waiting result from /execute_plan"
            self.get_logger().error(info)
            return False,info
        
        result=result_future.result()
        if result is None:
            info = "No result returned from /execute_plan"
            self.get_logger().error(info)
            return False, info
        

        if not result.result.success:
            info = "Plan execution failed"
            self.get_logger().error(info)
            return False, info
        
        return True, ""