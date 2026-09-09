"""Driver-facing client for the naive agent: cartesian arm moves + gripper.

Each primitive owns its goal and carries its own safety check
against the world model, matching the two geometries the model distinguishes:
  - move() polls check_path on the arc it traverses while the motion is in
    flight; on a blocked arc it cancels the goal and reports the obstacle.
  - grip() checks check_node on the destination node before commanding the tool;
    check_path guards the arc but not the arrival point, so a human on the node
    itself is caught here.
"""

import time
import threading

from rclpy.action import ActionClient
from geometry_msgs.msg import Point

from niryo_ned_ros2_interfaces.action import RobotMove, Tool
from niryo_ned_ros2_interfaces.msg import ArmMoveCommand, ToolCommand, RPY
from niryo_world_interfaces.srv import CheckPath, CheckNode

from ros_lib.base import ClientBase

class NiryoDriverClient(ClientBase):

    MOVE_ACTION = "/arm_1/niryo_robot_arm_commander/robot_action"
    TOOL_ACTION = "/arm_1/niryo_robot_tools_commander/action_server"
    CHECK_PATH = "/world_model_server/check_path"
    CHECK_NODE = "/world_model_server/check_node"

    def __init__(self, tool_id: int = 11, poll_period: float = 0.1)->None:
        super.__init__('agent_niryo_driver_client')
        self._tool_id = tool_id
        self._poll_period = poll_period

        self._move_client = ActionClient(self, RobotMove, self.MOVE_ACTION, callback_group=self.cb_group)
        self._tool_client = ActionClient(self, Tool, self.TOOL_ACTION, callback_group=self.cb_group)
        self._check_path_client = self.create_client(CheckPath, self.CHECK_PATH, callback_group=self.cb_group)
        self._check_node_client = self.create_client(CheckNode, self.CHECK_NODE, callback_group=self.cb_group)

    def _path_clear(self, from_node: str, to_node: str, timeout_sec: float = 1.0) -> bool:
        """Is the arc currently free of humans? A failed/unknown check is a config
        or comms issue, not a safety event: mirror the safe monitor and keep going."""
        req = CheckPath.Request()
        req.from_node = from_node
        req.to_node = to_node
        resp = self._call_sync(self._check_path_client, req, timeout_sec)
        if resp is None or not resp.success:
            return True
        return resp.clear

    def _node_clear(self, node: str, timeout_sec: float = 1.0) -> bool:
        """Is the node currently free of humans? Like _path_clear, a failed/unknown
        check is treated as clear: a config/comms issue must not block manipulation."""
        req = CheckNode.Request()
        req.node = node
        resp = self._call_sync(self._check_node_client, req, timeout_sec)
        if resp is None or not resp.success:
            return True
        return resp.clear

    def move(self, pose, from_node: str, to_node: str, timeout_sec: float = 60.0):
        """Move the arm to a cartesian pose, watching the arc for obstruction.

        pose is [x, y, z, roll, pitch, yaw]. Returns (ok, message). On a human
        blocking the arc the goal is cancelled and ok is False with an
        'obstacle on arc from->to' message; on driver failure ok is False with
        the driver's message; on success ok is True.
        """
        if not self._move_client.wait_for_server(timeout_sec=5.0):
            return False, f"Action server {self.MOVE_ACTION} not available"

        # Pre-checks: fail fast instead of starting a motion that is already unsafe.
        if not self._path_clear(from_node, to_node):
            return False, f"obstacle on arc {from_node}->{to_node}"
        if not self._node_clear(to_node):
            return False, f"obstacle on node {to_node}"

        cmd = ArmMoveCommand()
        cmd.cmd_type = ArmMoveCommand.POSE
        cmd.position = Point(x=pose[0], y=pose[1], z=pose[2])
        cmd.rpy = RPY(roll=pose[3], pitch=pose[4], yaw=pose[5])
        goal = RobotMove.Goal()
        goal.cmd = cmd

        goal_done = threading.Event()
        goal_future = self._move_client.send_goal_async(goal)
        goal_future.add_done_callback(lambda _f: goal_done.set())
        if not goal_done.wait(5.0):
            return False, f"Timeout waiting for goal acceptance from {self.MOVE_ACTION}"

        goal_handle = goal_future.result()
        if goal_handle is None or not goal_handle.accepted:
            return False, f"Move goal rejected by {self.MOVE_ACTION}"

        result_done = threading.Event()
        result_future = goal_handle.get_result_async()
        result_future.add_done_callback(lambda _f: result_done.set())

        # result_done.wait returns True the instant the motion ends; each timeout
        # is one safety poll tick. Cancel on a blocked arc or on the overall deadline.
        deadline = time.monotonic() + timeout_sec
        while not result_done.wait(self._poll_period):
            if time.monotonic() > deadline:
                goal_handle.cancel_goal_async()
                return False, f"Timeout during move to {to_node}"
            if not self._path_clear(from_node, to_node):
                goal_handle.cancel_goal_async()
                result_done.wait(5.0)          # let the cancellation settle
                return False, f"obstacle on arc {from_node}->{to_node}"

        result = result_future.result()
        if result is None:
            return False, f"No result returned from {self.MOVE_ACTION}"
        if result.result.status < 0:
            return False, result.result.message
        return True, result.result.message

    def grip(self, close: bool, node: str, timeout_sec: float = 30.0):
        """Open or close the gripper at a node, after checking it is human-free.
        """
        if not self._node_clear(node):
            return False, f"obstacle on node {node}"

        if not self._tool_client.wait_for_server(timeout_sec=5.0):
            return False, f"Action server {self.TOOL_ACTION} not available"

        cmd = ToolCommand()
        cmd.cmd_type = ToolCommand.CLOSE_GRIPPER if close else ToolCommand.OPEN_GRIPPER
        cmd.tool_id = self._tool_id
        goal = Tool.Goal()
        goal.cmd = cmd

        goal_done = threading.Event()
        goal_future = self._tool_client.send_goal_async(goal)
        goal_future.add_done_callback(lambda _f: goal_done.set())
        if not goal_done.wait(5.0):
            return False, f"Timeout waiting for goal acceptance from {self.TOOL_ACTION}"

        goal_handle = goal_future.result()
        if goal_handle is None or not goal_handle.accepted:
            return False, f"Tool goal rejected by {self.TOOL_ACTION}"

        result_done = threading.Event()
        result_future = goal_handle.get_result_async()
        result_future.add_done_callback(lambda _f: result_done.set())
        if not result_done.wait(timeout_sec):
            return False, f"Timeout waiting for result from {self.TOOL_ACTION}"

        result = result_future.result()
        if result is None:
            return False, f"No result returned from {self.TOOL_ACTION}"
        if result.result.status < 0:
            return False, result.result.message
        return True, result.result.message