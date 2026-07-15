import json
import math

import rclpy
from rclpy.node import Node

from geometry_msgs.msg import Quaternion
from vision_msgs.msg import (
    Detection3D,
    Detection3DArray,
    ObjectHypothesisWithPose,
)


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

    def __init__(self) -> None:
        super().__init__('env_perception')

        self.declare_parameter('scene_file', '')
        self.declare_parameter('frame_id', 'base_link')
        self.declare_parameter('publish_rate', 10.0)

        self._scene_file = self.get_parameter('scene_file').value
        self._frame_id = self.get_parameter('frame_id').value
        rate = self.get_parameter('publish_rate').value

        self._pub = self.create_publisher(Detection3DArray, '/env/detections', 10)
        self._timer = self.create_timer(1.0 / rate, self._tick)

        self.get_logger().info(
            f"Publishing /env/detections at {rate} Hz "
            f"(frame '{self._frame_id}', scene '{self._scene_file}')"
        )

    def _read_scene(self) -> list | None:
        """Return the list of detected objects, or None if the scene is unreadable.

        MOCK: reads the JSON file. This is the only method the real vision model
        will replace.
        """
        try:
            with open(self._scene_file) as f:
                return json.load(f).get('detections', [])
        except (OSError, json.JSONDecodeError) as e:
            # The file may be mid-write while edited by hand: skip this tick
            # rather than publishing a wrong scene.
            self.get_logger().warn(f"Cannot read scene file: {e}", throttle_duration_sec=5.0)
            return None

    def _to_detection(self, obj: dict, stamp) -> Detection3D:
        """Compose one Detection3D out of the flat facts of the scene file.

        The two poses of the message carry different things, on purpose:

        - bbox      -> the raw box: the object CENTER plus its extent. This is
                       what a detector actually produces, and what the JSON holds.
        - results[] -> the SUPPORT POINT: the bottom of the box. Consumers match
                       objects against zones, and a zone's z is its resting
                       surface, so both sides of the comparison must be "where
                       the thing rests". Publishing the center instead would work
                       by luck for a flat cube (1 cm off) and fail for a standing
                       human (90 cm off).

        Deriving the support point from the box needs no per-class special case:
        a 2 cm cube centred at z=0.01 and a 1.8 m human centred at z=0.9 both
        come out resting at z=0.0.
        """
        pos = obj['position']
        size = obj.get('size', {})
        sz = float(size.get('z', 0.0))

        rpy = obj.get('rpy', {})
        orientation = rpy_to_quaternion(
            float(rpy.get('roll', 0.0)),
            float(rpy.get('pitch', 0.0)),
            float(rpy.get('yaw', 0.0)),
        )

        det = Detection3D()
        det.header.stamp = stamp
        det.header.frame_id = self._frame_id
        det.id = obj.get('id', '')

        det.bbox.center.position.x = float(pos['x'])
        det.bbox.center.position.y = float(pos['y'])
        det.bbox.center.position.z = float(pos['z'])
        det.bbox.center.orientation = orientation
        det.bbox.size.x = float(size.get('x', 0.0))
        det.bbox.size.y = float(size.get('y', 0.0))
        det.bbox.size.z = sz

        hyp = ObjectHypothesisWithPose()
        hyp.hypothesis.class_id = obj['class_id']
        hyp.hypothesis.score = float(obj.get('score', 1.0))
        hyp.pose.pose.position.x = float(pos['x'])
        hyp.pose.pose.position.y = float(pos['y'])
        hyp.pose.pose.position.z = float(pos['z']) - sz / 2.0
        hyp.pose.pose.orientation = orientation
        det.results.append(hyp)

        return det

    def _tick(self) -> None:
        objects = self._read_scene()
        if objects is None:
            return

        stamp = self.get_clock().now().to_msg()

        msg = Detection3DArray()
        msg.header.stamp = stamp
        msg.header.frame_id = self._frame_id

        for obj in objects:
            try:
                msg.detections.append(self._to_detection(obj, stamp))
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