"""Starts rosbridge (for the app) + motion, hand and overlay nodes.

    ros2 launch cv_vision vision.launch.py                 # everything
    ros2 launch cv_vision vision.launch.py hands:=false    # skip MediaPipe
    ros2 launch cv_vision vision.launch.py port:=9091 input_topic:=/camera/image_raw/compressed
"""
import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.conditions import IfCondition
from launch.launch_description_sources import AnyLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    params = os.path.join(get_package_share_directory('cv_vision'), 'config', 'params.yaml')
    input_topic = LaunchConfiguration('input_topic')
    common = [params, {'input_topic': input_topic}]

    rosbridge = IncludeLaunchDescription(
        AnyLaunchDescriptionSource(os.path.join(
            get_package_share_directory('rosbridge_server'), 'launch', 'rosbridge_websocket_launch.xml')),
        launch_arguments={'port': LaunchConfiguration('port'), 'address': ''}.items(),
        condition=IfCondition(LaunchConfiguration('rosbridge')),
    )

    return LaunchDescription([
        DeclareLaunchArgument('input_topic', default_value='/cv/image/compressed'),
        DeclareLaunchArgument('port', default_value='9090'),
        DeclareLaunchArgument('rosbridge', default_value='true'),
        DeclareLaunchArgument('motion', default_value='true'),
        DeclareLaunchArgument('hands', default_value='true'),
        rosbridge,
        Node(package='cv_vision', executable='motion_node', parameters=common, output='screen',
             condition=IfCondition(LaunchConfiguration('motion'))),
        Node(package='cv_vision', executable='hand_node', parameters=common, output='screen',
             condition=IfCondition(LaunchConfiguration('hands'))),
        Node(package='cv_vision', executable='overlay_node', parameters=common, output='screen'),
    ])
