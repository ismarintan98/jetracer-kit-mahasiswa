"""ROS 2 dengan gaya rospy (ROS 1): loop `while`, tanpa class dan tanpa boilerplate.

    import ros1_style as rospy
    from geometry_msgs.msg import Twist
    from sensor_msgs.msg import LaserScan

    rospy.init_node("tes")
    pub = rospy.Publisher("/cmd_vel", Twist)
    rospy.Subscriber("/scan", LaserScan, lambda msg: rospy.loginfo("%d titik" % len(msg.ranges)))
    rate = rospy.Rate(10)                       # 10 Hz
    while not rospy.is_shutdown():
        pub.publish(Twist())
        rate.sleep()

Modul ini otomatis tersedia di `./ros.sh` (lewat PYTHONPATH), dari folder mana pun.

Perilaku yang perlu diketahui:
  - Callback subscriber jalan di thread latar belakang (seperti rospy), jadi
    loop `while` kalian tetap jalan sambil data sensor terus masuk.
  - Ctrl-C: is_shutdown() menjadi True dan rate.sleep() langsung kembali,
    sehingga loop selesai dengan rapi. Ctrl-C kedua = paksa berhenti.
  - Saat program selesai, semua Publisher bertipe Twist mengirim Twist nol
    (robot berhenti), baru kemudian ROS dimatikan.
  - Butuh API ROS 2 yang lengkap? `rospy.node` adalah rclpy Node biasa.
"""
import atexit
import signal
import threading

import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.signals import SignalHandlerOptions

node = None                 # rclpy Node, dibuat oleh init_node()
_stop = threading.Event()   # di-set saat Ctrl-C / signal_shutdown()
_spinner = None
_twist_pubs = []


def init_node(name):
    """Buat node dan mulai menjalankan callback di belakang. Panggil sekali di awal."""
    global node, _spinner
    if node is not None:
        raise RuntimeError("init_node() sudah dipanggil")
    rclpy.init(signal_handler_options=SignalHandlerOptions.NO)
    node = rclpy.create_node(name)
    signal.signal(signal.SIGINT, _on_sigint)
    signal.signal(signal.SIGTERM, _on_sigint)
    _spinner = threading.Thread(target=_spin, daemon=True)
    _spinner.start()
    atexit.register(_cleanup)
    return node


def is_shutdown():
    return _stop.is_set() or not rclpy.ok()


def signal_shutdown(reason=""):
    """Hentikan program dari dalam kode (loop `while not is_shutdown()` selesai)."""
    if reason and node is not None:
        node.get_logger().info("shutdown: %s" % reason)
    _stop.set()


class Rate:
    """rate.sleep() menunggu sisa waktu sampai periode berikutnya (jam dinding)."""

    def __init__(self, hz):
        self.period = 1.0 / hz
        self._next = None

    def sleep(self):
        import time
        now = time.monotonic()
        if self._next is None or now - self._next > self.period:
            self._next = now                    # pertama kali / tertinggal jauh: mulai ulang
        self._next += self.period
        _stop.wait(max(0.0, self._next - now))  # kembali segera kalau Ctrl-C


def sleep(seconds):
    """Seperti time.sleep(), tapi langsung kembali kalau Ctrl-C."""
    _stop.wait(seconds)


def spin():
    """Diam sampai Ctrl-C (untuk program yang hanya berisi callback)."""
    while not is_shutdown():
        _stop.wait(0.1)


def Publisher(topic, msg_type, queue_size=10):
    _cek_init()
    pub = node.create_publisher(msg_type, topic, queue_size)
    if msg_type.__name__ == "Twist":
        _twist_pubs.append((pub, msg_type))
    return pub


def Subscriber(topic, msg_type, callback, queue_size=10):
    _cek_init()
    return node.create_subscription(msg_type, topic, callback, queue_size)


def wait_for_message(topic, msg_type, timeout=None):
    """Tunggu satu pesan dari topik. Mengembalikan pesannya, atau None kalau timeout/Ctrl-C."""
    _cek_init()
    hasil = []
    datang = threading.Event()

    def cb(msg):
        if not hasil:
            hasil.append(msg)
            datang.set()
    sub = node.create_subscription(msg_type, topic, cb, 10)
    try:
        import time
        batas = None if timeout is None else time.monotonic() + timeout
        while not datang.is_set() and not is_shutdown():
            if batas is not None and time.monotonic() >= batas:
                break
            datang.wait(0.05)
    finally:
        node.destroy_subscription(sub)
    return hasil[0] if hasil else None


def loginfo(msg):
    _cek_init()
    node.get_logger().info(str(msg))


def logwarn(msg):
    _cek_init()
    node.get_logger().warn(str(msg))


def logerr(msg):
    _cek_init()
    node.get_logger().error(str(msg))


# --- internal ---------------------------------------------------------------

def _cek_init():
    if node is None:
        raise RuntimeError("panggil rospy.init_node('nama') dulu")


def _spin():
    try:
        rclpy.spin(node)
    except ExternalShutdownException:
        pass


def _on_sigint(signum, frame):
    if _stop.is_set():
        raise KeyboardInterrupt                 # Ctrl-C kedua: paksa
    _stop.set()


def _cleanup():
    _stop.set()
    for pub, msg_type in _twist_pubs:           # pengaman: robot berhenti
        try:
            pub.publish(msg_type())
        except Exception:
            pass
    rclpy.try_shutdown()
    if _spinner is not None:
        _spinner.join(timeout=2.0)
