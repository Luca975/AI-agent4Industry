#!/usr/bin/env python3
"""
Test director for the naive (LLM-as-planner) agent's replanning validation.

Injects a human into scene.json to simulate an obstacle; env_perception publishes
it, the world model marks the affected arcs/nodes blocked, the agent must react.

Node positions are fetched from the world model's get_zone service — the SAME
source it uses for occupancy — so an injected human lands exactly where the world
model places the node. (The old zones.csv geometry is gone: the world model now
loads poses from the robot.)

Modes:
  static   write the human(s) BEFORE the agent observes.
               --mode static --inject wp1
  on_move  inject when the arm starts moving (tcp_speed over threshold);
           optionally remove after T seconds (transient).
               --mode on_move --inject wp1 [--transient 2]
  manual   inject on Enter, remove on next Enter (or after --transient).
               --mode manual --inject wp1
"""

import os
import json
import time
import argparse
import threading

import rclpy
from rclpy.node import Node
from niryo_ned_ros2_interfaces.msg import RobotState
from niryo_world_interfaces.srv import GetZone

HOME = os.path.expanduser('~/AI-agent4Industry')
SCENE_FILE = os.path.join(HOME, 'scenes', 'scene.json')

# The graph nodes the world model knows (see build_arcs in world_model_server).
GRAPH_NODES = ["home", "workspace", "conveyor", "wp1", "wp2"]

# arm counts as "moving" above this tcp_speed (m/s)
MOVE_SPEED_THRESHOLD = 0.01


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

    def __init__(self, args):
        super().__init__('test_director')
        self._mode = args.mode
        self._inject = args.inject.split(',')
        self._transient = args.transient
        self._fired = False

        self._nodes = self._fetch_nodes()   # from get_zone, not a CSV

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

    def _fetch_nodes(self) -> dict:
        """{node: (x, y)} from the world model's get_zone — the authoritative source."""
        client = self.create_client(GetZone, "/world_model_server/get_zone")
        if not client.wait_for_service(timeout_sec=10.0):
            self.get_logger().error("get_zone service unavailable")
            return {}

        nodes = {}
        for name in GRAPH_NODES:
            req = GetZone.Request()
            req.zone = name
            fut = client.call_async(req)
            rclpy.spin_until_future_complete(self, fut, timeout_sec=5.0)
            resp = fut.result()
            if resp is not None and resp.success:
                nodes[name] = (resp.position.x, resp.position.y)
                self.get_logger().info(f"  {name}: ({resp.position.x:.3f}, {resp.position.y:.3f})")
            else:
                self.get_logger().warn(f"get_zone('{name}') failed/unknown")
        return nodes

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

    rclpy.init()
    director = Director(args)
    try:
        rclpy.spin(director)
    except KeyboardInterrupt:
        pass
    finally:
        director.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()