import threading

from rclpy.action import ActionClient

from niryo_ned_ros2_interfaces.action import RobotMove
from niryo_ned_ros2_interfaces.msg import ArmMoveCommand

from plansys2_lib.base import PlanSys2ClientBase

class ArmCommander(PlanSys2ClientBase):
    """Agent-side client that drives the arm to a fixed home configuration."""

    HOME_JOINTS = [0.0, 0.5, -1.25, 0.0, 0.0, 0.0]
    ACTION_NAME = "/arm_1/niryo_robot_arm_commander/robot_action"


    def __init__(self)->None:
        super().__init__('agent_arm_commander_client')
        self._move_client = ActionClient(
            self, RobotMove, self.ACTION_NAME, callback_group=self.cb_group
        )

    def go_home(self, timeout_sec:float = 30.0)->tuple[bool,str]:
        """Send the arm home and block until it arrives. Returns (ok, error_info)"""
        
        if not self._move_client.wait_for_server(timeout_sec=5.0):
            info = f"Action server {self.ACTION_NAME} not available"
            self.get_logger().error(info)
            return False, info
        
        cmd = ArmMoveCommand()
        cmd.cmd_type = ArmMoveCommand.JOINTS
        cmd.joints = self.HOME_JOINTS

        goal = RobotMove.Goal()
        goal.cmd = cmd

        goal_done = threading.Event()
        goal_future = self._move_client.send_goal_async(goal)
        goal_future.add_done_callback(lambda _f: goal_done.set())

        if not goal_done.wait(timeout_sec):
            info = f"Timeout waiting for goal acceptance from {self.ACTION_NAME}"
            self.get_logger().error(info)
            return False, info
        
        goal_handle = goal_future.result()
        if goal_handle is None or not goal_handle.accepted:
            info = f"Home goal rejected by {self.ACTION_NAME}"
            self.get_logger().error(info)
            return False, info
        

        result_done = threading.Event()
        result_future = goal_handle.get_result_async()
        result_future.add_done_callback(lambda _f: result_done.set())


        if not result_done.wait(timeout_sec):
            info = f"Timeout waiting for result from {self.ACTION_NAME}"
            self.get_logger().error(info)
            return False, info
        
        result = result_future.result()
        if result is None:
            info = f"No result returned from {self.ACTION_NAME}"
            self.get_logger().error(info)
            return False, info
        
        if result.result.status < 0:
            info = f"Move to home failed: {result.result.message}"
            self.get_logger().error(info)
            return False, info
        
        return True,""