import os
from ament_index_python.packages import get_package_share_directory
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

    world_model_cmd = Node(
        package='niryo_world_model',
        executable='world_model_server_node',
        name='world_model_server',
        namespace=namespace,
        output='screen',
        parameters=[{
            'arm_name': 'arm_1',
            'class_to_type': ['cube:piece', 'person:human'],

            # matching radii, scaled to a desktop layout: the defaults assume a
            # full-size person and would mark every node of this cell occupied
            'zone_thresholds': 0.15,
            'grasp_threshold': 0.05,
            'human_radius': 0.01,
            'path_clearance': 0.01,
            'staleness_threshold': 1.0,
        }])

    ld = LaunchDescription()
    ld.add_action(declare_namespace_cmd)
    ld.add_action(world_model_cmd)

    return ld