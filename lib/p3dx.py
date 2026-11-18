"""Robot JetRacer dengan antarmuka Pioneer P3-DX (seperti m_p3dx.py di CoppeliaSim).

Program kelas yang ditulis untuk P3-DX di CoppeliaSim (repo
Coppelia_MObjectFollower) bisa dipindah ke robot dengan perubahan kecil:

    # CoppeliaSim                              # Robot (kit ini)
    import sim                                 import p3dx
    import m_p3dx as p3dx
    clientID = connect()          # sim.simxStart   clientID = p3dx.connect()
    sensorsHandle = p3dx.getSensorsHandle(clientID)      (sama)
    motorsHandle  = p3dx.getMotorHandle(clientID)        (sama)
    sensorValue   = p3dx.getDistance(clientID, sensorsHandle)   (sama)
    p3dx.robotWheelKine(clientID, motorsHandle, [v, w])  (sama)
    p3dx.setWheelVel(clientID, motorsHandle, [phiL, phiR])      (sama)
    keyboard.is_pressed('w')                   k = p3dx.tombol()   ->  k == 'w'

Jalankan:  ./ros.sh python3 /workspace/<program>.py   (modul ini otomatis ada)

Yang terjadi di robot:
  - getDistance(): 16 sonar virtual dari LiDAR (topik /sonar). Model sensornya
    diukur dari P3-DX di scene kelas: indeks 0..15 sama (0 = kiri 90°,
    3/4 = depan ±10°, 7 = kanan, 8..15 belakang), sensor di tepi badan,
    nilai 0.045..1.0 m, TIDAK ADA DETEKSI = 2.0 (sama seperti getDistance()).
    Laju ~7.8 Hz (putaran LiDAR); di antaranya nilai terakhir dikembalikan.
  - setWheelVel(): kecepatan sudut roda P3-DX [kiri, kanan] (rad/s) dikirim ke
    /cmd_wheel_vel. Robot menghitung gerak P3-DX sungguhan (r = 0.0975 m,
    jarak roda 0.331 m) lalu menjalankannya dengan kemudi Ackermann.

PERBEDAAN dengan P3-DX (robot ini mobil Ackermann):
  - TIDAK BISA BERPUTAR DI TEMPAT: φL = -φR (v = 0) membuat robot diam.
    Untuk berbelok robot harus maju/mundur.
  - Radius belok minimum terbatas; ω yang terlalu besar dibanding v "mentok".
  - Batas driver |v| <= 0.5 m/s, |ω| <= 2.0 rad/s.
  - Seperti di Coppelia, perintah roda terakhir terus berlaku sampai diganti.
    Modul ini mengirimnya ulang 20 kali per detik; kalau program berhenti
    (selesai/crash/Ctrl-C), robot berhenti.

!! Percobaan pertama: ANGKAT RODA dari lantai.
"""
import atexit
import os
import re
import select
import signal
import sys
import termios
import threading
import time
import tty

import numpy as np
from numpy.linalg import inv

import rclpy
from rclpy.executors import ExternalShutdownException, SingleThreadedExecutor
from rclpy.signals import SignalHandlerOptions
from std_msgs.msg import Float32MultiArray

TANPA_DETEKSI = 2.0
JUMLAH_SONAR = 16


class _Robot(object):
    """Isi `clientID`. Tidak perlu dipakai langsung."""

    def __init__(self, nama, timeout):
        rclpy.init(signal_handler_options=SignalHandlerOptions.NO)
        self.node = rclpy.create_node(nama)
        self.sonar = None
        self.sonar_waktu = 0.0
        self.roda = [0.0, 0.0]
        self.lock = threading.Lock()
        self.pub = self.node.create_publisher(Float32MultiArray, "/cmd_wheel_vel", 10)
        self.node.create_subscription(Float32MultiArray, "/sonar", self._on_sonar, 10)
        self.node.create_timer(0.05, self._kirim)        # 20 Hz, perintah terakhir tetap berlaku
        self.executor = SingleThreadedExecutor()
        self.executor.add_node(self.node)
        self.thread = threading.Thread(target=self._spin, daemon=True)
        self.thread.start()
        atexit.register(self.tutup)
        signal.signal(signal.SIGTERM, lambda *a: sys.exit(0))      # atexit -> robot berhenti
        _pasang_pesan_ctrl_c()

        t0 = time.monotonic()
        while self.sonar is None and time.monotonic() - t0 < timeout:
            time.sleep(0.05)
        if self.sonar is None:
            self.node.get_logger().warn(
                "belum ada data /sonar setelah %.0f s — robot menyala? ROBOT_IP benar? "
                "getDistance() mengembalikan 2.0 dulu" % timeout)
        else:
            self.node.get_logger().info("tersambung ke robot (sonar %.1f s)" % (time.monotonic() - t0))

    def _spin(self):
        try:
            self.executor.spin()
        except (ExternalShutdownException, Exception):
            pass

    def _on_sonar(self, msg):
        if len(msg.data) == JUMLAH_SONAR:
            self.sonar = list(msg.data)
            self.sonar_waktu = time.monotonic()

    def _kirim(self):
        with self.lock:
            data = list(self.roda)
        self.pub.publish(Float32MultiArray(data=data))

    def set_roda(self, kiri, kanan):
        with self.lock:
            self.roda = [float(kiri), float(kanan)]
        self._kirim()

    def tutup(self):
        if not rclpy.ok():
            return
        try:
            self.set_roda(0.0, 0.0)
            time.sleep(0.1)
        finally:
            self.executor.shutdown(timeout_sec=1.0)
            # Tunggu thread spin selesai SEBELUM node & ROS dimatikan. Kalau
            # tidak, program berakhir dengan "terminate called without an
            # active exception" (abort, kode keluar 134).
            self.thread.join(2.0)
            self.node.destroy_node()
            rclpy.try_shutdown()


_robot = None


def connect(nama="p3dx", timeout=5.0):
    """Sambung ke robot (pengganti sim.simxStart). Mengembalikan clientID."""
    global _robot
    if _robot is None:
        _robot = _Robot(nama, timeout)
        print("Connected to robot (JetRacer, mode P3-DX)")
    return _robot


def disconnect(clientID=None):
    """Hentikan robot & tutup sambungan (pengganti sim.simxFinish)."""
    if _robot is not None:
        _robot.tutup()
    _kb_pulihkan()


def _pasang_pesan_ctrl_c():
    """Ctrl-C tanpa try/except di program: satu baris pesan, bukan traceback.
    Robot tetap dihentikan (atexit). `except KeyboardInterrupt` di program
    kalian tetap bekerja seperti biasa."""
    asli = sys.excepthook

    def kait(jenis, nilai, jejak):
        if issubclass(jenis, KeyboardInterrupt):
            print("\nCtrl-C: robot berhenti")
        else:
            asli(jenis, nilai, jejak)
    sys.excepthook = kait


# ---- keyboard: pengganti modul `keyboard` di program kelas ------------------
_kb = {"siap": False, "fd": -1, "asli": None, "habis": False, "key": "", "t": 0.0}
_KB_ESC = re.compile(r"\x1b(\[[0-9;]*[A-Za-z~]|O.)?")      # tombol panah, F1.., dll.


def _kb_siapkan():
    """Terminal ke mode 'baca per tombol' (tanpa Enter, tanpa gema)."""
    _kb["siap"] = True
    try:
        _kb["fd"] = sys.stdin.fileno()
    except (AttributeError, ValueError, OSError):
        _kb["habis"] = True                 # tidak ada stdin
        return
    try:
        _kb["asli"] = termios.tcgetattr(_kb["fd"])
        tty.setcbreak(_kb["fd"])
        atexit.register(_kb_pulihkan)       # terminal kembali normal saat program selesai
    except termios.error:
        pass                                # stdin bukan terminal (pipe): tetap bisa dibaca


def _kb_pulihkan():
    if _kb["asli"] is not None:
        try:
            termios.tcsetattr(_kb["fd"], termios.TCSADRAIN, _kb["asli"])
        except termios.error:
            pass
        _kb["asli"] = None
        _kb["siap"] = False


def tombol(tahan=0.6):
    """Tombol keyboard yang sedang ditekan, huruf kecil; '' kalau tidak ada.

        k = p3dx.tombol()
        if k == 'w': ...

    Tidak menunggu dan tidak perlu Enter; panggil di setiap putaran loop.
    Terminal tidak memberi tahu kapan tombol dilepas, jadi tombol dianggap
    masih ditekan `tahan` detik setelah karakter terakhirnya datang (tahan
    tombolnya -> keyboard mengulang sendiri). Terminal disiapkan otomatis
    pada panggilan pertama dan dipulihkan saat program selesai.
    """
    if not _kb["siap"]:
        _kb_siapkan()
    while not _kb["habis"] and select.select([_kb["fd"]], [], [], 0)[0]:
        data = os.read(_kb["fd"], 1024)
        if not data:
            _kb["habis"] = True
            break
        teks = _KB_ESC.sub("", data.decode(errors="ignore"))
        if teks:
            _kb["key"], _kb["t"] = teks[-1].lower(), time.monotonic()
    return _kb["key"] if time.monotonic() - _kb["t"] < tahan else ""


def lepasTombol():
    """Anggap tombol yang sedang ditekan sudah dilepas. Untuk tombol 'sekali
    tekan' (ganti mode): tanpa ini satu tekan terbaca di banyak putaran loop."""
    _kb["key"] = ""


def getSensorsHandle(clientID):
    return np.arange(JUMLAH_SONAR, dtype=np.int32)


def getDistance(clientID, sensorsHandle):
    """16 jarak sonar (m) sebagai numpy array; tidak ada deteksi = 2.0."""
    s = clientID.sonar
    if s is None:
        s = [TANPA_DETEKSI] * JUMLAH_SONAR
    return np.array([s[int(i)] for i in sensorsHandle], dtype=float)


def sensorAge(clientID):
    """Umur data sonar terakhir (detik). Besar = LiDAR/robot tidak mengirim."""
    return float("inf") if clientID.sonar is None else time.monotonic() - clientID.sonar_waktu


def getMotorHandle(clientID):
    return (0, 1)        # (kiri, kanan), sama urutannya dengan Coppelia


def setWheelVel(clientID, motorsHandle, veloCmd):
    """veloCmd[i] = kecepatan sudut roda motorsHandle[i] (rad/s), seperti Coppelia."""
    roda = [0.0, 0.0]
    for h, w in zip(motorsHandle, veloCmd):
        roda[int(h)] = float(w)
    clientID.set_roda(roda[0], roda[1])
    return 0


def robotWheelKine(clientID, motorHandle, Vel):
    """Sama persis dengan m_p3dx.robotWheelKine() di repo kelas."""
    # Robot parameters
    r = 0.0975  # Wheel radius [m]
    L = 0.28    # widthbody

    # Robot kinematics
    r_2 = r / 2
    r_2L = r_2 * L

    matrixKine = np.array([[r_2, r_2],
                           [-r_2L, r_2L]])

    matrixKineInv = inv(matrixKine)
    velWheel = np.dot(matrixKineInv, Vel)
    # Set wheel velocity
    setWheelVel(clientID, motorHandle, velWheel)

    return 0
