""" This file defines the dependencies of the agent, which are the ROS nodes that the agent interacts with."""


from dataclasses import dataclass


from ros_lib.scene_observer import SceneObserver
from ros_lib.executor import Executor
#from plansys2_lib.arm_commander import ArmCommander

@dataclass
class AgentContext:
    """Runtime dependecies injected into the graph via context_schema=AgentContext.
    They are deliberately kept out of AgentState: these are live ROS client nodes, not serializable data,
    so they must never land on checkpointed state"""
    
    problem_client: ProblemExpert
    planner_client: Planner
    domain_client: DomainExpert
    scene_client: SceneObserver
    executor_client:Executor
#    home_pos_client:ArmCommander