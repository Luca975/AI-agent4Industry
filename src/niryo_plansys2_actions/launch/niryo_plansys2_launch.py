import os
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node

def generate_launch_description():

    pkg_dir = get_package_share_directory('niryo_plansys2_actions')
    namespace = LaunchConfiguration('namespace')
    model_file = LaunchConfiguration('model_file')

    declare_namespace_cmd = DeclareLaunchArgument(
        'namespace',
        default_value='',
        description='Namespace')

    declare_model_file_cmd = DeclareLaunchArgument(
        'model_file',
        default_value=os.path.join(
            os.path.expanduser('~'), 'AI-agent4Industry', 'pddl', 'domain.pddl'),
        description='PDDL domain file')

    plansys2_cmd = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(os.path.join(
            get_package_share_directory('plansys2_bringup'),
            'launch',
            'plansys2_bringup_launch_monolithic.py')),
        launch_arguments={
            'model_file': model_file,
            'namespace': namespace
        }.items())

    zone_map_server_cmd = Node(
        package='niryo_plansys2_actions',
        executable='zone_map_server_node',
        name='zone_map_server_node',
        namespace=namespace,
        output='screen',
        parameters=[{
            'zones_file': os.path.join(pkg_dir, 'config', 'zones.csv'),
            'zone_thresholds': 0.15
            }])

    move_cmd = Node(
        package='niryo_plansys2_actions',
        executable='move_action_node',
        name='move_action_node',
        namespace=namespace,
        output='screen',
        parameters=[])

    pick_cmd = Node(
        package='niryo_plansys2_actions',
        executable='pick_action_node',
        name='pick_action_node',
        namespace=namespace,
        output='screen',
        parameters=[])

    place_cmd = Node(
        package='niryo_plansys2_actions',
        executable='place_action_node',
        name='place_action_node',
        namespace=namespace,
        output='screen',
        parameters=[])

    ld = LaunchDescription()
    ld.add_action(declare_namespace_cmd)
    ld.add_action(declare_model_file_cmd)
    ld.add_action(plansys2_cmd)
    ld.add_action(zone_map_server_cmd)
    ld.add_action(move_cmd)
    ld.add_action(pick_cmd)
    ld.add_action(place_cmd)

    return ld