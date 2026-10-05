"""Tahap 2 — LOKALISASI: posisi robot di peta yang sudah disimpan.

    ./ros.sh ros2 launch /workspace/nav/localization.launch.py peta:=lab
    ./ros.sh ros2 launch /workspace/nav/localization.launch.py peta:=lab x:=1.2 y:=0.5 theta:=1.57

Peta dibaca dari /workspace/peta/<peta>.posegraph + .data (hasil simpan_peta.sh).
Peta TIDAK diubah di mode ini — hanya posisi robot yang diperkirakan.

POSE AWAL — penting, scan matching hanya bisa mengoreksi salah posisi yang kecil:
  - Tanpa x/y/theta: robot dianggap berada di TITIK AWAL MAPPING ("dock" =
    pose pertama di pose graph). Letakkan robot di tempat & arah yang sama
    dengan saat mapping dimulai. Nilai odometri robot tidak berpengaruh.
  - Dengan x/y/theta: robot dianggap di koordinat itu (frame map, meter/rad).
  - Kapan saja: "2D Pose Estimate" di RViz (topik /initialpose).

Output: TF map -> odom (jadi map -> base_footprint lengkap), dan /map.
Posisi robot di peta = lookup TF map -> base_footprint (lihat posisi_robot.py).
"""
import os

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, OpaqueFunction
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node

HERE = os.path.dirname(os.path.abspath(__file__))
PETA_DIR = os.path.join(os.path.dirname(HERE), "peta")


def node(context):
    nama = LaunchConfiguration("peta").perform(context)
    path = nama if os.path.isabs(nama) else os.path.join(PETA_DIR, nama)
    if not os.path.exists(path + ".posegraph"):
        raise RuntimeError("peta %s.posegraph tidak ada — buat dulu dengan "
                           "mapping.launch.py + simpan_peta.sh" % path)
    xyz = [LaunchConfiguration(k).perform(context) for k in ("x", "y", "theta")]
    params = {"mode": "localization", "use_sim_time": False, "map_file_name": path}
    if any(xyz):
        params.update(map_start_at_dock=False,
                      map_start_pose=[float(v or 0.0) for v in xyz])
        awal = "pose (%s, %s, %s)" % tuple(v or "0" for v in xyz)
    else:
        params.update(map_start_at_dock=True)
        awal = "titik awal mapping (dock)"
    print("[localization] peta %s, mulai di %s" % (path, awal))
    return [Node(package="slam_toolbox", executable="localization_slam_toolbox_node",
                 name="slam_toolbox", output="screen",
                 parameters=[os.path.join(HERE, "slam.yaml"), params])]


def generate_launch_description():
    return LaunchDescription([
        DeclareLaunchArgument("peta", description="nama peta di /workspace/peta (tanpa ekstensi)"),
        DeclareLaunchArgument("x", default_value=""),
        DeclareLaunchArgument("y", default_value=""),
        DeclareLaunchArgument("theta", default_value=""),
        OpaqueFunction(function=node),
    ])
