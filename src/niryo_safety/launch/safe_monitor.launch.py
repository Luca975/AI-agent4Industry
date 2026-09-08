from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():

    namespace = LaunchConfiguration('namespace')

    declare_namespace_cmd = DeclareLaunchArgument(
        'namespace',
        default_value='',
        description='Namespace')

    safe_monitor_cmd = Node(
        package='niryo_safety',
        executable='safe_monitor_node',
        name='safe_monitor',
        namespace=namespace,
        output='screen',
        parameters=[{
            'check_rate': 10.0,
        }])

    ld = LaunchDescription()
    ld.add_action(declare_namespace_cmd)
    ld.add_action(safe_monitor_cmd)

    return ld