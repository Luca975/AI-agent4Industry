"""Full-stack bring-up: Niryo driver (in its own venv) + the custom stack."""



from launch import LaunchDescription
from launch.actions import ExecuteProcess, IncludeLaunchDescription, TimerAction
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import PathJoinSubstitution
from launch_ros.substitutions import FindPackageShare

# Seconds to wait for the driver startup

DRIVER_WARMUP = 10.0

def _include(pkg, launch_file):
    """Include a launch file from an installed package's share/<pkg>/launch dir."""
    return IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            PathJoinSubstitution([FindPackageShare(pkg), "launch", launch_file])
        )
    )

def generate_launch_description():
    driver = ExecuteProcess(
        cmd=[
            "bash", "-c",
            "source /opt/ros/jazzy/setup.bash && "
            "source ~/ros2_drivers_ws/install/setup.bash && "
            "source ~/ros2_drivers_ws/venv/bin/activate && "
            "cd ~/ros2_drivers_ws && "
            "ros2 launch niryo_ned_ros2_driver driver.launch.py "
            "drivers_list_file:=./src/ned-ros2-driver/niryo_ned_ros2_driver/config/drivers_list.yaml",
        ],
        output="screen",
    )
 
    stack = TimerAction(
        period=DRIVER_WARMUP,
        actions=[
            _include("niryo_env_perception", "env_perception.launch.py"),
            _include("niryo_safety", "safe_monitor.launch.py"),            
            _include("niryo_world_model", "world_model.launch.py"),
            _include("niryo_plansys2_actions", "niryo_plansys2.launch.py"),
        ],
    )
 
    return LaunchDescription([driver, stack])