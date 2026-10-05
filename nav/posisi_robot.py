#!/usr/bin/env python3
"""Tampilkan posisi robot di peta (TF map -> base_footprint), 2x per detik.

    ./ros.sh python3 /workspace/nav/posisi_robot.py

Jalankan bersama mapping.launch.py atau localization.launch.py. Contoh cara
membaca hasil lokalisasi dari kode: slam_toolbox (Humble) TIDAK menerbitkan
topik pose — posisinya ada di pohon TF.
"""
import math

import rclpy
import tf2_ros
from rclpy.node import Node


class PosisiRobot(Node):
    def __init__(self):
        super().__init__("posisi_robot")
        self.buf = tf2_ros.Buffer()
        self.tf = tf2_ros.TransformListener(self.buf, self)
        self.create_timer(0.5, self.cetak)

    def cetak(self):
        try:
            t = self.buf.lookup_transform("map", "base_footprint", rclpy.time.Time())
        except tf2_ros.TransformException as e:
            self.get_logger().warn("belum ada TF map->base_footprint: %s" % e,
                                   throttle_duration_sec=3.0)
            return
        p, q = t.transform.translation, t.transform.rotation
        yaw = math.atan2(2 * (q.w * q.z + q.x * q.y), 1 - 2 * (q.y * q.y + q.z * q.z))
        self.get_logger().info("di peta: x %+.2f m  y %+.2f m  arah %+.0f°"
                               % (p.x, p.y, math.degrees(yaw)))


def main():
    rclpy.init()
    n = PosisiRobot()
    try:
        rclpy.spin(n)
    except KeyboardInterrupt:
        pass
    finally:
        n.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
