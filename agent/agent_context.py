""" This file defines the dependencies of the agent, which are the ROS nodes that the agent interacts with."""


from dataclasses import dataclass

from plansys2_lib.problem_expert import ProblemExpert
from plansys2_lib.planner import Planner
from plansys2_lib.domain_expert import DomainExpert
from plansys2_lib.scene_observer import SceneObserver
from plansys2_lib.executor import Executor
from plansys2_lib.arm_commander import ArmCommander

@dataclass
class AgentContext:
    problem_client: ProblemExpert
    planner_client: Planner
    domain_client: DomainExpert
    scene_client: SceneObserver
    executor_client:Executor
    home_pos_client:ArmCommander