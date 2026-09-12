
import math
import threading

from rclpy.callback_groups import ReentrantCallbackGroup
from std_msgs.msg import Empty

from niryo_world_interfaces.srv import ObserveScene, GetZone
from niryo_world_interfaces.msg import SceneObject
from niryo_env_interfaces.msg import EnvScene

from ros_lib.base import ClientBase

def _quat_to_rpy(q):
    """Convert a quaternion to (roll, pitch, yaw), radians.

    Inverse of env_perception's rpy_to_quaternion (fixed-axis XYZ). RobotMove's
    POSE command wants rpy, so object orientation from perception is converted
    here to keep observe_scene's output uniform with the node poses from get_zone.
    """
    sinr_cosp = 2.0 * (q.w * q.x + q.y * q.z)
    cosr_cosp = 1.0 - 2.0 * (q.x * q.x + q.y * q.y)
    roll = math.atan2(sinr_cosp, cosr_cosp)

    sinp = 2.0 * (q.w * q.y - q.z * q.x)
    pitch = math.copysign(math.pi / 2.0, sinp) if abs(sinp) >= 1.0 else math.asin(sinp)

    siny_cosp = 2.0 * (q.w * q.z + q.x * q.y)
    cosy_cosp = 1.0 - 2.0 * (q.y * q.y + q.z * q.z)
    yaw = math.atan2(siny_cosp, cosy_cosp)
    return roll, pitch, yaw


class SceneObserver(ClientBase):

    def __init__(self)->None:
        super().__init__('agent_scene_observer_client')

        self._observe_client = self.create_client(ObserveScene, '/world_model_server/observe_scene',
                                                  callback_group = self.cb_group)
        self._zone_client = self.create_client(GetZone, '/world_model_server/get_zone',
                                               callback_group = self.cb_group)

        # Latest perception frame: object id -> [x,y,z,roll,pitch,yaw]
        self._obj_poses = {}
        self._poses_lock = threading.Lock()
        self.create_subscription(EnvScene, '/env/scene', self._on_scene, 10,
                                 callback_group = ReentrantCallbackGroup())


    def _on_scene(self, msg : EnvScene) -> None:
        """Cache the poses from a fresh /env/scene frame, keyed by object id."""
        fresh = {}
        for obj in msg.objects:
            r,p,y = _quat_to_rpy(obj.pose.orientation)
            fresh[obj.id] = [obj.pose.position.x, obj.pose.position.y, obj.pose.position.z,
                             r,p,y]

        with self._poses_lock:
            self._obj_poses = fresh

    def _object_pose(self, obj_id: str):
        """Cached perception pose for obj_id, or None if not seen in the last frame"""
        with self._poses_lock:
            return self._obj_poses.get(obj_id)

    def _node_pose(self, name: str, timeout_sec: float = 5.0):
        """Pose of a graph node via get_zone, or None if the zone is unknown."""
        req = GetZone.Request()
        req.zone = name
        resp = self._call_sync(self._zone_client, req, timeout_sec)
        if resp is None or not resp.success:
            return None
        return [
            resp.position.x, resp.position.y, resp.position.z,
            resp.rpy.roll, resp.rpy.pitch, resp.rpy.yaw,
        ]

    def observe_scene(self, timeout_sec: float = 5.0):
        """Observe the scene, enriched with cartesian poses.

        Returns (success, objects, nodes, paths, info):
          objects: (name, type, location, held, color, pose|None) - pose from perception
          nodes:   (name, type, pose|None)                        - pose from get_zone
          paths:   (from_node, to_node, clear)
        On failure returns (False, [], [], [], reason).
        """
        req = ObserveScene.Request()
        req.request = Empty()
        resp = self._call_sync(self._observe_client, req, timeout_sec)

        if resp is None:
            info = f"Service call to {self._observe_client.srv_name} failed"
            self.get_logger().error(info)
            return False, [], [], [], info
        if not resp.success:
            info = resp.error_info or f"{self._observe_client.srv_name} returned failure"
            self.get_logger().warn(info)
            return False, [], [], [], info

        objects, nodes = [], []
        for o in resp.objects:
            if o.type == SceneObject.PIECE:
                objects.append((o.name, o.type, o.location, o.held, o.color, self._object_pose(o.name)))
            elif o.type in (SceneObject.AREA, SceneObject.WAYPOINT):
                nodes.append((o.name, o.type, self._node_pose(o.name)))
            elif o.type == SceneObject.ROBOT:
                objects.append((o.name, o.type, o.location, o.held, o.color, None))
            # HUMAN: skipped; obstruction is carried by the arcs' clear flag.

        paths = [(p.from_node, p.to_node, p.clear) for p in resp.paths]
        return True, objects, nodes, paths, ""