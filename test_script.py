#!/usr/bin/env python3
"""
Test director for the reactive replanning validation.

The persistent stack (driver, world model, monitor, PlanSys2, performers, agent)
is launched by hand. This script drives a SINGLE scenario: it prepares the scene,
injects/removes a human at the right moment, and logs the event sequence so the
operator can compare it against the expected oracle.

Two modes:

  single  wait for a given action on a given target, then inject a human on a
          chosen node; optionally remove it after T seconds.
              --on move:home:wp1  --inject wp1                 (persistent)
              --on move:home:wp1  --inject wp1  --transient 2  (transient)
              --on pick:workspace_1 --inject workspace_1       (on a pick)

  static  write one or more humans BEFORE the agent plans, then do nothing. Used
          to make the planner fail to find a plan.
              --inject wp1,wp2

Node coordinates are resolved at startup through the world model's
/world_model_server/get_zone service -- the same map the arm navigates by -- so an
injected human lands exactly on the node, whatever pose that node was loaded with.
This replaces the old CSV + waypoint-derivation path: waypoints are no longer
computed geometrically, they are saved robot poses the world model serves by name.
The node names used below (wp1, workspace_1, ...) must therefore match the
saved-pose names on the robot.

Scenarios:
  1 baseline     (no director)
  2 transient    single --on move:home:wp1 --inject wp1 --transient 2
  3 replan       single --on move:home:wp1 --inject wp1
  4 emergency    single --on pick:workspace_1 --inject workspace_1
  5 fault/noplan static --inject wp1,wp2
"""

import os
import json
import time
import argparse
import threading

import rclpy
from rclpy.node import Node
from plansys2_msgs.msg import ActionExecutionInfo
from niryo_world_interfaces.srv import GetZone

HOME = os.path.expanduser('~/AI-agent4Industry')
SCENE_FILE = os.path.join(HOME, 'scenes', 'scene.json')


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

        if args.on:
            act, *rest = args.on.split(':')
            self._on_action = act
            self._on_args = rest       # ['home','wp1'] for move, ['workspace_1'] for pick
        else:
            self._on_action = None
            self._on_args = []

        # Node poses live in the world model now (loaded from the robot's saved
        # library poses), so it is the only authority on where a node actually is.
        # Resolve every injection target once, up front: node poses are static and
        # doing it here keeps _do_inject a pure dict read -- a get_zone call from
        # inside the /action_execution_info callback would nest a spin and deadlock.
        self._zone_client = self.create_client(GetZone, '/world_model_server/get_zone')
        if not self._zone_client.wait_for_service(timeout_sec=10.0):
            raise SystemExit("/world_model_server/get_zone unavailable -- is the stack running?")
        self._coords = self._resolve_nodes(self._inject)
        missing = [n for n in self._inject if n not in self._coords]
        if missing:
            raise SystemExit(f"cannot resolve node(s) via get_zone: {missing}")

        # always start from a human-free scene so the agent plans normally
        write_scene(clear_humans(load_scene()))

        if self._mode == 'static':
            self._do_inject()
            self.get_logger().warn(
                f"STATIC: humans placed on {self._inject} before planning")
        else:
            self._sub = self.create_subscription(
                ActionExecutionInfo, '/action_execution_info', self._on_info, 100)
            self.get_logger().info(
                f"SINGLE: waiting for {self._on_action}{self._on_args} to inject on {self._inject}")

    def _resolve_nodes(self, names, timeout_sec: float = 5.0) -> dict:
        """Return {name: (x, y)} for each node via /world_model_server/get_zone.

        Unknown or unreachable names are logged and dropped; the caller checks the
        result for completeness before proceeding."""
        coords = {}
        for name in names:
            req = GetZone.Request()
            req.zone = name
            future = self._zone_client.call_async(req)
            rclpy.spin_until_future_complete(self, future, timeout_sec=timeout_sec)
            if not future.done():
                self.get_logger().error(f"get_zone('{name}') timed out")
                continue
            resp = future.result()
            if resp is None or not resp.success:
                self.get_logger().error(f"unknown node '{name}' (get_zone failed)")
                continue
            coords[name] = (resp.position.x, resp.position.y)
        return coords

    def _do_inject(self):
        scene = load_scene()
        for i, node in enumerate(self._inject):
            x, y = self._coords[node]
            scene["objects"].append(human_entry(f"person_{i+1}", x, y))
        write_scene(scene)

    def _on_info(self, msg: ActionExecutionInfo):
        if self._fired or msg.status != ActionExecutionInfo.EXECUTING:
            return
        if msg.action != self._on_action:
            return
        # move: args are [robot, from, to] -> match from/to; pick/place: [robot, area, piece]
        if self._on_action == 'move':
            if len(msg.arguments) < 3 or list(msg.arguments[1:3]) != self._on_args:
                return
        else:
            if len(msg.arguments) < 2 or [msg.arguments[1]] != self._on_args:
                return

        self._fired = True
        self._do_inject()
        self.get_logger().warn(
            f"INJECTED on {self._inject} while executing "
            f"{self._on_action}{list(msg.arguments[1:])}")

        if self._transient is not None:
            threading.Thread(target=self._remove_after, daemon=True).start()

    def _remove_after(self):
        time.sleep(self._transient)
        write_scene(clear_humans(load_scene()))
        self.get_logger().warn(f"REMOVED after {self._transient}s (transient obstacle)")


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--mode', choices=['single', 'static'], required=True)
    p.add_argument('--inject', required=True, help='node(s) to occupy, comma-separated')
    p.add_argument('--on', help='trigger as action:arg1[:arg2], e.g. move:home:wp1 or pick:workspace_1')
    p.add_argument('--transient', type=float, default=None, help='remove human after T seconds')
    args = p.parse_args()

    if args.mode == 'single' and not args.on:
        raise SystemExit("--on is required in single mode")

    rclpy.init()
    director = None
    try:
        director = Director(args)
        rclpy.spin(director)
    except KeyboardInterrupt:
        pass
    finally:
        if director is not None:
            director.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()