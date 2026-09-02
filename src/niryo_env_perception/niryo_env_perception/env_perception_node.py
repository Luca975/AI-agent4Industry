"""env_perception: mock perception node.

Reads a scene from a JSON file and republishes it on /env/scene as an EnvScene
at a fixed rate. Stands is for the real vision model; when that lands, only
_read_scene() changes.
"""

import json
import math

import rclpy
from rclpy.node import Node

from geometry_msgs.msg import Quaternion
from niryo_env_interfaces.msg import EnvObject, EnvScene

def rpy_to_quaternion(roll: float, pitch: float, yaw: float) -> Quaternion:
    """Convert roll/pitch/yaw (radians) to a quaternion.

    Fixed-axis XYZ convention (R = Rz(yaw) * Ry(pitch) * Rx(roll)), the same one
    used by tf_transformations.quaternion_from_euler with default axes. Written
    inline to avoid pulling a dependency for four lines of trigonometry.
    """
    cr, sr = math.cos(roll * 0.5), math.sin(roll * 0.5)
    cp, sp = math.cos(pitch * 0.5), math.sin(pitch * 0.5)
    cy, sy = math.cos(yaw * 0.5), math.sin(yaw * 0.5)

    q = Quaternion()
    q.w = cr * cp * cy + sr * sp * sy
    q.x = sr * cp * cy - cr * sp * sy
    q.y = cr * sp * cy + sr * cp * sy
    q.z = cr * cp * sy - sr * sp * cy
    return q


class EnvPerception(Node):
    """
        Parameters:
            scene_file Path to the JSON scene description, re-read every tick.
            frame_id Frame stamped on every published EnvScene.
            publish_rate Publish frequency, in Hz
    """

    def __init__(self) -> None:
        super().__init__('env_perception')

        self.declare_parameter('scene_file', '')
        self.declare_parameter('frame_id', 'base_link')
        self.declare_parameter('publish_rate', 10.0)

        self._scene_file = self.get_parameter('scene_file').value
        self._frame_id = self.get_parameter('frame_id').value
        rate = self.get_parameter('publish_rate').value

        self._pub = self.create_publisher(EnvScene, '/env/scene', 10)
        self._timer = self.create_timer(1.0 / rate, self._tick)

        self.get_logger().info(
            f"Publishing /env/scene at {rate} Hz "
            f"(frame '{self._frame_id}', scene '{self._scene_file}')"
        )

    def _read_scene(self) -> list | None:
        """Return the list of detected objects, or None if the scene is unreadable.

        MOCK: reads the JSON file. This is the only method the real vision model
        will replace.
        """
        try:
            with open(self._scene_file) as f:
                return json.load(f).get('objects', [])
        except (OSError, json.JSONDecodeError) as e:
            # The file may be mid-write while edited by hand: skip this tick
            # rather than publishing a wrong scene.
            self.get_logger().warn(f"Cannot read scene file: {e}", throttle_duration_sec=5.0)
            return None

    def _to_env_object(self, obj: dict) -> EnvObject:
        """ Map one JSON object dict to an EnvObject.

        id, class_id and position are required (a missing one raises and the object is skipped by the caller);
        color, score, rpy and size are optional and fall back to neutral defaults.
        """

        out = EnvObject()
        out.id = obj['id']
        out.class_id = obj['class_id']
        out.color = obj.get('color', '')
        out.score = float(obj.get('score', 1.0))
 
        pos = obj['position']
        out.pose.position.x = float(pos['x'])
        out.pose.position.y = float(pos['y'])
        out.pose.position.z = float(pos['z'])
 
        rpy = obj.get('rpy', {})
        out.pose.orientation = rpy_to_quaternion(
            float(rpy.get('roll', 0.0)),
            float(rpy.get('pitch', 0.0)),
            float(rpy.get('yaw', 0.0)),
        )
 
        size = obj.get('size', {})
        out.size.x = float(size.get('x', 0.0))
        out.size.y = float(size.get('y', 0.0))
        out.size.z = float(size.get('z', 0.0))
 
        return out

    def _tick(self) -> None:
        """Read the scene once and publish it; skip the tick if the file is unreadable."""
        objects = self._read_scene()
        if objects is None:
            return

        stamp = self.get_clock().now().to_msg()

        msg = EnvScene()
        msg.header.stamp = stamp
        msg.header.frame_id = self._frame_id

        for obj in objects:
            try:
                msg.objects.append(self._to_env_object(obj))
            except (KeyError, TypeError, ValueError) as e:
                self.get_logger().warn(f"Skipping malformed object {obj}: {e}")

        # Published even when empty: consumers must be able to tell "nothing
        # detected" from "perception is dead" by looking at the stamp.
        self._pub.publish(msg)


def main() -> None:
    rclpy.init()
    node = EnvPerception()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()