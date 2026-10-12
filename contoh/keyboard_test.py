#!/usr/bin/env python3
"""Kendali keyboard gaya ROS 1 (ros1_style) — contoh paling kecil.

    ./ros.sh python3 /workspace/contoh/keyboard_test.py

    w = maju        s = mundur        a / d = belok kiri / kanan
    spasi = berhenti                  q atau Ctrl-C = keluar (robot berhenti)

!! Percobaan pertama: ANGKAT RODA dari lantai.

Yang dipelajari:
  - pola rospy: init_node, Publisher, Subscriber, loop `while` + Rate
  - /cmd_vel harus dikirim TERUS (di sini 10 Hz) — driver menghentikan robot
    0.5 s setelah /cmd_vel berhenti datang
  - Ackermann: belok (angular.z) hanya berpengaruh saat robot maju/mundur
  - rem darurat dari /scan: tidak mau maju kalau ada benda < 0.3 m di depan
"""
import math
import os
import select
import sys
import termios
import tty

import ros1_style as rospy
from geometry_msgs.msg import Twist
from sensor_msgs.msg import LaserScan

KECEPATAN = 0.15            # m/s
BELOK = 0.6                 # rad/s
JARAK_AMAN = 0.3            # m
SEKTOR = math.radians(25)   # sektor depan: -25° .. +25°

jarak_depan = [float("inf")]


def on_scan(scan):
    # Jarak terdekat di sektor depan. Sudut ROS: 0 = depan, positif = ke kiri.
    terdekat = float("inf")
    for i, r in enumerate(scan.ranges):
        sudut = scan.angle_min + i * scan.angle_increment
        if abs(sudut) <= SEKTOR and math.isfinite(r) and r > 0:
            terdekat = min(terdekat, r)
    jarak_depan[0] = terdekat


def baca_tombol():
    """Tombol yang ditekan, atau '' kalau tidak ada. Tidak menunggu."""
    if select.select([sys.stdin], [], [], 0)[0]:
        return os.read(sys.stdin.fileno(), 1).decode(errors="ignore")
    return ""


def main():
    if not sys.stdin.isatty():
        sys.exit("Butuh terminal interaktif: jalankan ./ros.sh langsung dari terminal.")

    rospy.init_node("keyboard_test")
    pub = rospy.Publisher("/cmd_vel", Twist)
    rospy.Subscriber("/scan", LaserScan, on_scan)
    rate = rospy.Rate(10)                       # 10 Hz
    rospy.loginfo("w/s = maju/mundur, a/d = belok, spasi = berhenti, q = keluar")

    cmd = Twist()
    lama = termios.tcgetattr(sys.stdin)
    tty.setcbreak(sys.stdin.fileno())           # tombol langsung terbaca, tanpa Enter
    try:
        while not rospy.is_shutdown():
            k = baca_tombol()
            if k == "q":
                break
            elif k == "w":
                cmd.linear.x, cmd.angular.z = KECEPATAN, 0.0
            elif k == "s":
                cmd.linear.x, cmd.angular.z = -KECEPATAN, 0.0
            elif k == "a":
                cmd.angular.z = BELOK
            elif k == "d":
                cmd.angular.z = -BELOK
            elif k == " ":
                cmd = Twist()
            if k:
                rospy.loginfo("v = %.2f m/s, w = %.2f rad/s" % (cmd.linear.x, cmd.angular.z))
                if k in "ad" and cmd.linear.x == 0:
                    rospy.logwarn("Ackermann: belok baru terasa setelah maju (w) / mundur (s)")

            if cmd.linear.x > 0 and jarak_depan[0] < JARAK_AMAN:
                rospy.logwarn("halangan %.2f m di depan — berhenti" % jarak_depan[0])
                cmd = Twist()

            pub.publish(cmd)
            rate.sleep()
    finally:
        termios.tcsetattr(sys.stdin, termios.TCSADRAIN, lama)
    # Saat program selesai, ros1_style mengirim Twist nol: robot berhenti.


if __name__ == "__main__":
    main()
