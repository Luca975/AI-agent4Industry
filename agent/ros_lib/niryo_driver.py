"""Driver-facing client for the naive agent: cartesian arm moves + gripper.

The arm is commanded point-to-point in cartesian space (RobotMove, POSE): a move
just goes to a pose. So move() takes a kind that selects which check
guards the motion, matching its two physical phases:
  - transit: travel along an arc between stations -> check_path, pre-check plus
    polling while the motion is in flight (the arc is long and shared).
  - approach: local reach onto the object inside a station -> check_node,
    pre-check only (short, local motion).
grip() opens/closes the tool at a node, pre-checking it with check_node.

All of this is mechanism only: whether to wait, retry, reroute or escalate on a
reported obstacle is the LLM's decision, never taken here.
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
        super().__init__('agent_niryo_driver_client')
        self._tool_id = tool_id
        self._poll_period = poll_period

        self._move_client = ActionClient(self, RobotMove, self.MOVE_ACTION, callback_group=self.cb_group)
        self._tool_client = ActionClient(self, Tool, self.TOOL_ACTION, callback_group=self.cb_group)
        self._check_path_client = self.create_client(CheckPath, self.CHECK_PATH, callback_group=self.cb_group)
        self._check_node_client = self.create_client(CheckNode, self.CHECK_NODE, callback_group=self.cb_group)

    # --- world-model safety checks -------------------------------------------

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

    # --- primitives ----------------------------------------------------------

    def move(self, pose, kind: str, from_node: str = None, to_node: str = None,
             node: str = None, timeout_sec: float = 60.0):
        """Move the arm to a cartesian pose. The motion is point-to-point; kind
        selects only which world-model check guards it.

          kind="transit": travel along an arc. Needs from_node/to_node. Pre-checks
            the arc (check_path) and keeps polling it while the motion is in
            flight, cancelling the goal on a block.
          kind="approach": local move onto the object inside a station. Needs node.
            Pre-checks the node (check_node) only; no continuous polling.

        pose is [x, y, z, roll, pitch, yaw]. Returns (ok, message): an
        'obstacle on arc/node ...' or driver message on failure, driver message on
        success.
        """
        # kind-specific pre-check
        if kind == "transit":
            if not self._path_clear(from_node, to_node):
                return False, f"obstacle on arc {from_node}->{to_node}"
        elif kind == "approach":
            if not self._node_clear(node):
                return False, f"obstacle on node {node}"
        else:
            return False, f"unknown move kind '{kind}'"

        if not self._move_client.wait_for_server(timeout_sec=5.0):
            return False, f"Action server {self.MOVE_ACTION} not available"

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

        # transit polls the arc while the motion runs; approach is short, local and
        # already pre-checked, so it just waits for the result.
        if kind == "transit":
            deadline = time.monotonic() + timeout_sec
            while not result_done.wait(self._poll_period):
                if time.monotonic() > deadline:
                    goal_handle.cancel_goal_async()
                    return False, f"Timeout during transit to {to_node}"
                if not self._path_clear(from_node, to_node):
                    goal_handle.cancel_goal_async()
                    result_done.wait(5.0)          # let the cancellation settle
                    return False, f"obstacle on arc {from_node}->{to_node}"
        else:
            if not result_done.wait(timeout_sec):
                goal_handle.cancel_goal_async()
                return False, f"Timeout during approach to {node}"

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