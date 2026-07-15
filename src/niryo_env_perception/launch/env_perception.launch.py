import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description() -> LaunchDescription:
    scene_file = os.path.join(
        get_package_share_directory('niryo_env_perception'),
        'config',
        'scene.json',
    )

    return LaunchDescription([
        Node(
            package='niryo_env_perception',
            executable='env_perception',
            name='env_perception',
            output='screen',
            parameters=[{
                'scene_file': scene_file,
                # TODO: il frame reale in cui sono espresse le coordinate delle aree
                'frame_id': 'base_link',
                'publish_rate': 10.0,
            }],
        ),
    ])