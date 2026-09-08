from typing import TypedDict

class PlanStep(TypedDict):
    """One durative plan step; maps 1:1 to a plansys2_msgs/PlanItem (see Executor._to_ros_plan)"""
    time:float
    action:str
    duration:float