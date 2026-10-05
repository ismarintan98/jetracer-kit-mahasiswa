"""Tahap 1 — MAPPING: bangun peta dengan slam_toolbox sambil robot dijalankan.

    ./ros.sh ros2 launch /workspace/nav/mapping.launch.py

Lalu jalankan robot PELAN keliling ruangan (teleop), dan simpan peta:

    ./ros.sh /workspace/nav/simpan_peta.sh lab

Output TF: map -> odom (robot sendiri menerbitkan odom -> base_footprint).
Topik: /map (OccupancyGrid). Posisi robot: TF map -> base_footprint (posisi_robot.py).
"""
import os

from launch import LaunchDescription
from launch_ros.actions import Node

HERE = os.path.dirname(os.path.abspath(__file__))


def generate_launch_description():
    return LaunchDescription([
        Node(package="slam_toolbox", executable="async_slam_toolbox_node",
             name="slam_toolbox", output="screen",
             parameters=[os.path.join(HERE, "slam.yaml"),
                         {"mode": "mapping", "use_sim_time": False}]),
    ])
