#!/usr/bin/env python3
"""Bring up Shutter with mock hardware and RViz, and make it mirror (fake) human affect.

Starts:
  * shutter_hardware_interface/shutter_control.launch.py with hardware:=mock -- Shutter's
    ros2_control stack without a real robot (also starts robot_state_publisher)
  * RViz, showing the robot model
  * fake_affect -- fake affect scores on /affect/visual and /affect/audio
  * behavior_controller -- turns the affect into joint commands for the joint_group_controller

Usage:
    ros2 launch shutter_emotion milestone.launch.py
    ros2 launch shutter_emotion milestone.launch.py rviz:=false fake_affect:=false
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    rviz_arg = DeclareLaunchArgument(
        'rviz',
        default_value='true',
        description='Start RViz'
    )

    fake_affect_arg = DeclareLaunchArgument(
        'fake_affect',
        default_value='true',
        description='Start the fake_affect node (set to false once the real perception nodes run)'
    )

    # Shutter's ros2_control stack with mock hardware. hardware:=mock must be given:
    # shutter_control.launch.py drives the real robot by default.
    mock_bringup_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource([
            PathJoinSubstitution([
                FindPackageShare('shutter_hardware_interface'),
                'launch',
                'shutter_control.launch.py'
            ])
        ]),
        launch_arguments={
            'hardware': 'mock',
            'startup_pose': 'false',
        }.items()
    )

    rviz_node = Node(
        package='rviz2',
        executable='rviz2',
        name='rviz',
        arguments=['-d', PathJoinSubstitution([
            FindPackageShare('shutter_emotion'),
            'config',
            'milestone.rviz'
        ])],
        condition=IfCondition(LaunchConfiguration('rviz'))
    )

    fake_affect_node = Node(
        package='shutter_emotion',
        executable='fake_affect',
        name='fake_affect',
        output='screen',
        condition=IfCondition(LaunchConfiguration('fake_affect'))
    )

    behavior_controller_node = Node(
        package='shutter_emotion',
        executable='behavior_controller',
        name='behavior_controller',
        output='screen'
    )

    return LaunchDescription([
        rviz_arg,
        fake_affect_arg,
        mock_bringup_launch,
        rviz_node,
        fake_affect_node,
        behavior_controller_node
    ])
