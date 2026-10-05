#!/usr/bin/env python3
"""Contoh paling sederhana: maju pelan, berhenti kalau ada halangan di depan.

    ./ros.sh python3 /workspace/contoh/hindari_halangan.py
    ./ros.sh python3 /workspace/contoh/hindari_halangan.py --ros-args -p kecepatan:=0.1 -p jarak_aman:=0.5

!! Percobaan pertama: ANGKAT RODA dari lantai. Ctrl-C = robot berhenti.

Yang dipelajari:
  - subscribe /scan (sensor_msgs/LaserScan), publish /cmd_vel (geometry_msgs/Twist)
  - konvensi sudut ROS (REP-103): 0 rad = depan, positif = ke KIRI
  - robot berhenti sendiri 0.5 s setelah /cmd_vel berhenti datang (pengaman
    driver) — node yang crash tidak membuat robot kabur
"""
import math

import rclpy
from geometry_msgs.msg import Twist
from rclpy.node import Node
from sensor_msgs.msg import LaserScan


class HindariHalangan(Node):
    def __init__(self):
        super().__init__("hindari_halangan")
        self.kecepatan = self.declare_parameter("kecepatan", 0.15).value      # m/s
        self.jarak_aman = self.declare_parameter("jarak_aman", 0.6).value     # m
        self.lebar_sektor = math.radians(self.declare_parameter("sektor_deg", 25.0).value)
        self.pub = self.create_publisher(Twist, "cmd_vel", 10)
        self.create_subscription(LaserScan, "scan", self.on_scan, 10)
        self.jarak_depan = None
        self.create_timer(0.1, self.kendali)            # 10 Hz
        self.get_logger().info("maju %.2f m/s, berhenti kalau ada halangan < %.2f m"
                               % (self.kecepatan, self.jarak_aman))

    def on_scan(self, scan):
        # Ambil jarak terdekat di sektor depan (-sektor .. +sektor rad).
        terdekat = float("inf")
        for i, r in enumerate(scan.ranges):
            sudut = scan.angle_min + i * scan.angle_increment
            if abs(sudut) <= self.lebar_sektor and math.isfinite(r):
                terdekat = min(terdekat, r)
        self.jarak_depan = terdekat

    def kendali(self):
        cmd = Twist()
        if self.jarak_depan is None:
            return                                       # belum ada data LiDAR
        if self.jarak_depan > self.jarak_aman:
            cmd.linear.x = self.kecepatan
        self.pub.publish(cmd)
        self.get_logger().info("depan %.2f m -> v = %.2f" % (self.jarak_depan, cmd.linear.x),
                               throttle_duration_sec=1.0)

    def berhenti(self):
        self.pub.publish(Twist())


def main():
    rclpy.init()
    node = HindariHalangan()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.berhenti()
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
