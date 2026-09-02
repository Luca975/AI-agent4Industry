import threading

from rclpy.action import ActionClient
from plansys2_msgs.action import ExecutePlan
from plansys2_msgs.msg import Plan, PlanItem, ActionExecutionInfo
from agent_types import PlanStep

from plansys2_lib.base import PlanSys2ClientBase

class Executor(PlanSys2ClientBase):
    """Agent-side client that dispatches a plan to PlanSys2 and reports which action broke it"""


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

    @staticmethod
    def _failed_action(result) -> tuple[str, str]:

        """Pick the action that broke the plan: the FAILED one, or the first CANCELLED if none is FAILED.
        
        FAILED wins because it is the real cause; a CANCELLED action is usually a side effect of the plan
        being torn down. Returns (action, message) so the graph can route replan vs emergency, or ("", reason)
        if nothing is marked"""

        failed = None
        cancelled = None
        for info in result.action_execution_status:
            if info.status == ActionExecutionInfo.FAILED:
                failed = info
                break
            if info.status == ActionExecutionInfo.CANCELLED and cancelled is None:
                cancelled = info

        chose = failed or cancelled
        if chose is not None:
            return chose.action, chose.message_status
        return "", "Plan failed but no action is marked FAILED or CANCELLED"

    def execute_plan(self, plan_steps:list[PlanStep], timeout_sec:float = 120.0)->tuple[bool, str, str]:
        """Dispatch a plan and block until it finishes. Returns (ok, failed_action, message):
        the offending action and its status message on failure, empty strings on success"""

        if not self._execute_plan_client.wait_for_server(timeout_sec=5.0):
            info = "Action server /execute_plan not available"
            self.get_logger().error(info)
            return False, "", info
        
        goal = ExecutePlan.Goal()
        goal.plan = self._to_ros_plan(plan_steps)

        goal_done = threading.Event()
        goal_future = self._execute_plan_client.send_goal_async(goal)
        goal_future.add_done_callback(lambda _f: goal_done.set())

        if not goal_done.wait(timeout_sec):
            info = "Timeout waiting for goal acceptance from /execute_plan"
            self.get_logger().error(info)
            return False, "", info
        
        goal_handle = goal_future.result()
        if goal_handle is None or not goal_handle.accepted:
            info = "Goal rejected by /execute_plan"
            self.get_logger().error(info)
            return False, "", info
        
        result_done = threading.Event()
        result_future = goal_handle.get_result_async()
        result_future.add_done_callback(lambda _f: result_done.set())

        if not result_done.wait(timeout_sec):
            info = "Timeout waiting result from /execute_plan"
            self.get_logger().error(info)
            return False, "", info
        
        result=result_future.result()
        if result is None:
            info = "No result returned from /execute_plan"
            self.get_logger().error(info)
            return False, "", info
        

        if not result.result.success:
            action, message = self._failed_action(result.result)
            self.get_logger().error(f"Plan execution failed on '{action}':{message}")
            return False, action, message
        
        return True, "", ""