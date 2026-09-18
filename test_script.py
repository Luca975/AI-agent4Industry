#!/usr/bin/env python3
"""
Test director for the naive (LLM-as-planner) agent's replanning validation.

The persistent stack (driver, world model, env_perception, agent) is launched by
hand. This script drives ONE scenario: it clears the scene, then injects a human
on a chosen node either before planning or the moment the arm starts moving, and
logs the events so the operator can compare against the expected oracle.

Unlike the formalizer director, there is no PlanSys2 action stream to trigger on.
Motion is detected from the driver's arm state (tcp_speed on
/arm_1/niryo_robot/robot_state).

Modes:

  static   write the human(s) BEFORE the agent observes, then do nothing. The
           agent sees the arc already BLOCKED and must route around it.
               --mode static --inject wp1

  on_move  wait until the arm starts moving (tcp_speed over threshold), then
           inject; optionally remove after T seconds (transient obstacle).
               --mode on_move --inject wp1                 (persistent)
               --mode on_move --inject wp1 --transient 2   (transient)

  manual   inject when the operator presses Enter; remove on the next Enter (or
           after --transient seconds). Full timing control for demos.
               --mode manual --inject wp1

Node coordinates come from zones.csv; waypoints are derived exactly like
world_model_server, so an injected human lands on the real node.
"""

import os
import csv
import json
import math
import time
import argparse
import threading

import rclpy
from rclpy.node import Node
from niryo_ned_ros2_interfaces.msg import RobotState

HOME = os.path.expanduser('~/AI-agent4Industry')
SCENE_FILE = os.path.join(HOME, 'scenes', 'scene.json')
ZONES_FILE = os.path.join(HOME, 'src', 'niryo_world_model', 'config', 'zones.csv')

# must match world_model_server params
WAYPOINT_OFFSETS = [0.02, 0.22]

# arm counts as "moving" above this tcp_speed (m/s); tune if it fires too early/late
MOVE_SPEED_THRESHOLD = 0.01


def load_nodes() -> dict:
    """Return {node_name: (x, y)} for every area, home, and derived waypoint,
    reproducing world_model_server so injected humans land on the real nodes."""
    areas = []
    nodes = {}

    with open(ZONES_FILE) as f:
        for row in csv.reader(f):
            if len(row) < 8:
                continue
            name, kind = row[0], row[1]
            x, y = float(row[2]), float(row[3])
            nodes[name] = (x, y)
            if kind == 'area':
                areas.append((name, x, y))

    wp_index = 1
    for i in range(len(areas) - 1):
        _, ax, ay = areas[i]
        _, bx, by = areas[i + 1]
        ref_x, ref_y = 0.5 * (ax + bx), 0.5 * (ay + by)
        nx, ny = -(by - ay), (bx - ax)
        norm = math.hypot(nx, ny)
        if norm < 1e-6:
            continue
        nx, ny = nx / norm, ny / norm
        if nx * ref_x + ny * ref_y < 0.0:
            nx, ny = -nx, -ny
        for off in WAYPOINT_OFFSETS:
            nodes[f"wp{wp_index}"] = (ref_x + off * nx, ref_y + off * ny)
            wp_index += 1

    return nodes


def human_entry(name: str, x: float, y: float) -> dict:
    return {
        "id": name,
        "class_id": "person",
        "color": "",
        "score": 0.95,
        "position": {"x": x, "y": y, "z": 0.0},
        "rpy": {"roll": 0.0, "pitch": 0.0, "yaw": 0.0},
        "size": {"x": 0.10, "y": 0.10, "z": 0.10},
    }


def load_scene() -> dict:
    with open(SCENE_FILE) as f:
        return json.load(f)


def write_scene(scene: dict) -> None:
    tmp = SCENE_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(scene, f, indent=2)
    os.replace(tmp, SCENE_FILE)


def clear_humans(scene: dict) -> dict:
    scene["objects"] = [o for o in scene["objects"] if o.get("class_id") != "person"]
    return scene


class Director(Node):

    def __init__(self, args, nodes):
        super().__init__('test_director')
        self._nodes = nodes
        self._mode = args.mode
        self._inject = args.inject.split(',')
        self._transient = args.transient
        self._fired = False

        # always start human-free so the agent's first observation is clean
        write_scene(clear_humans(load_scene()))

        if self._mode == 'static':
            self._do_inject()
            self.get_logger().warn(f"STATIC: humans on {self._inject} before observing")

        elif self._mode == 'on_move':
            self._sub = self.create_subscription(
                RobotState, '/arm_1/niryo_robot/robot_state', self._on_state, 10)
            self.get_logger().info(
                f"ON_MOVE: waiting for the arm to move, then inject on {self._inject}")

        elif self._mode == 'manual':
            threading.Thread(target=self._manual_loop, daemon=True).start()

    def _do_inject(self):
        scene = load_scene()
        for i, node in enumerate(self._inject):
            if node not in self._nodes:
                self.get_logger().error(f"Unknown node '{node}'")
                continue
            x, y = self._nodes[node]
            scene["objects"].append(human_entry(f"person_{i+1}", x, y))
        write_scene(scene)
        self.get_logger().warn(f"INJECTED on {self._inject}")

    def _remove(self):
        write_scene(clear_humans(load_scene()))
        self.get_logger().warn("REMOVED humans")

    def _on_state(self, msg: RobotState):
        if self._fired or msg.tcp_speed < MOVE_SPEED_THRESHOLD:
            return
        self._fired = True
        self.get_logger().warn(f"arm moving (tcp_speed={msg.tcp_speed:.3f})")
        self._do_inject()
        if self._transient is not None:
            threading.Thread(target=self._remove_after, daemon=True).start()

    def _remove_after(self):
        time.sleep(self._transient)
        self._remove()
        self.get_logger().warn(f"(transient: removed after {self._transient}s)")

    def _manual_loop(self):
        input("\n[director] Press Enter to INJECT...")
        self._do_inject()
        if self._transient is not None:
            time.sleep(self._transient)
            self._remove()
        else:
            input("[director] Press Enter to REMOVE...")
            self._remove()


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--mode', choices=['static', 'on_move', 'manual'], required=True)
    p.add_argument('--inject', required=True, help='node(s) to occupy, comma-separated')
    p.add_argument('--transient', type=float, default=None, help='remove human after T seconds')
    args = p.parse_args()

    nodes = load_nodes()

    rclpy.init()
    director = Director(args, nodes)
    try:
        rclpy.spin(director)
    except KeyboardInterrupt:
        pass
    finally:
        director.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()