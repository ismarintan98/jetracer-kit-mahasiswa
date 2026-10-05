# Kit Mahasiswa — Robot JetRacer ROS 2

Robot ini adalah **host sensor & aktuator**. Semua sensor dan motor tersedia
sebagai topik ROS 2 Humble, dan **sistem navigasinya kalian buat di PC
kalian sendiri**. PC dan robot tersambung lewat jaringan (ROS 2 multi-machine,
DDS).

```
 PC mahasiswa (kit ini)                          Robot (Jetson Nano)
 ┌──────────────────────────┐   WiFi / LAN    ┌──────────────────────────┐
 │ node navigasi kalian     │ ── /cmd_vel ──▶ │ motor + kemudi           │
 │ SLAM, Nav2, RViz         │ ◀── /scan ───── │ LiDAR RPLIDAR A1         │
 │                          │ ◀── /odom, /imu │ encoder, IMU             │
 │                          │ ◀── /camera/... │ kamera                   │
 └──────────────────────────┘                 └──────────────────────────┘
```

---

## 1. Kebutuhan PC

- **Linux** dengan **Docker Engine** (Ubuntu, Debian, Fedora, Arch, dll.).
  Ruang disk sekitar 6 GB untuk image ROS 2.
- **Bukan Docker Desktop (Windows/macOS).** Docker Desktop menjalankan
  container di dalam VM, sehingga `--net=host` tidak benar-benar memakai
  jaringan PC dan DDS tidak bisa menemukan robot. Di Windows, pakai Ubuntu
  dual-boot atau PC lab Linux.
- Terhubung ke jaringan yang bisa mencapai robot: tes dengan `ping <IP robot>`.

Pasang Docker (Ubuntu): `sudo apt install docker.io`, lalu
`sudo usermod -aG docker $USER`, lalu **logout & login lagi**.

### Firewall PC

Robot harus bisa **mengirim** data ke PC kalian lewat UDP. Kalau PC memakai
`ufw` (cek: `sudo ufw status`), buka port DDS untuk subnet robot:

```bash
# Ganti 10.17.36.0/22 dengan subnet jaringan robot (tanya dosen).
# Port 17900-17999 = ROS_DOMAIN_ID 42.
sudo ufw allow proto udp from 10.17.36.0/22 to any port 17900:17999
```

Tanpa ini: `ros2 topic list` di PC hanya menampilkan `/parameter_events`
dan `/rosout`.

---

## 2. Menyambung ke robot

1. Nyalakan robot. Tunggu sekitar 1 menit sampai **IP robot muncul di layar
   OLED**-nya.
2. Di PC, dari folder kit ini:

```bash
ROBOT_IP=10.17.36.90 ./ros.sh ros2 topic list     # IP dari OLED
```

Pertama kali dijalankan, image ROS 2 dibangun otomatis (sekitar 5 GB unduhan,
sekali saja). Topik yang harus muncul:

| Topik | Tipe | Arah | Keterangan |
|---|---|---|---|
| `/cmd_vel` | `geometry_msgs/Twist` | PC → robot | `linear.x` = v (m/s), `angular.z` = ω (rad/s) |
| `/odom` | `nav_msgs/Odometry` | robot → PC | 50 Hz, dari encoder roda (dihitung firmware) |
| `/imu` | `sensor_msgs/Imu` | robot → PC | 50 Hz, MPU9250 |
| `/scan` | `sensor_msgs/LaserScan` | robot → PC | ~7.8 Hz, 360 sampel, 0.15–12 m |
| `/camera/image_raw/compressed` | `sensor_msgs/CompressedImage` | robot → PC | JPEG 640×360, 15 fps |
| `/battery` | `sensor_msgs/BatteryState` | robot → PC | 1 Hz, baterai 3S (9.0–12.6 V) |
| `/tf`, `/tf_static` | | robot → PC | `odom → base_footprint → base_link → {laser_frame, imu_link, camera_link}` |
| `/motor/{lvel,rvel,lset,rset}` | `std_msgs/Int32` | robot → PC | kecepatan roda terukur & setpoint (satuan firmware, ~110 per m/s) |

Perintah lain:

```bash
ROBOT_IP=10.17.36.90 ./ros.sh                     # shell ROS 2 interaktif
ROBOT_IP=10.17.36.90 ./ros.sh rviz2               # RViz
export ROBOT_IP=10.17.36.90                       # supaya tidak diulang terus
```

Folder kit ini ter-mount di **`/workspace`** di dalam container. Simpan kode
dan peta kalian di sini supaya tidak hilang saat container ditutup.

---

## 3. Sifat robot yang harus kalian tahu

- **Mobil Ackermann** (seperti mobil sungguhan): roda belakang = penggerak,
  roda depan = kemudi.
  - **Tidak bisa berputar di tempat.** `linear.x = 0` membuat robot diam,
    berapa pun `angular.z`-nya. Untuk berbelok, robot harus maju atau mundur.
  - Firmware menghitung sendiri sudut kemudi dan beda kecepatan roda
    kiri/kanan dari `(v, ω)`.
  - Radius belok minimum terbatas, jadi ω yang terlalu besar dibanding v
    akan "mentok". Untuk Nav2, pilih controller yang mendukung Ackermann
    (mis. Regulated Pure Pursuit) dan batasi `min_turning_radius`.
- **Batas kecepatan driver:** |v| ≤ 0.5 m/s, |ω| ≤ 2.0 rad/s. Nilai lebih
  besar dipotong.
- **Pengaman:** kalau `/cmd_vel` berhenti datang selama **0.5 detik**, robot
  berhenti sendiri. Node kalian harus mengirim `/cmd_vel` terus-menerus
  (mis. 10 Hz) selama ingin bergerak.
- **LiDAR & kamera menyala sesuai permintaan:** motor LiDAR dan kamera hanya
  aktif kalau ada yang berlangganan. Scan pertama datang **sekitar 1.5 detik**
  setelah kalian mulai berlangganan. Itu normal.
- **QoS:** semua topik robot memakai **Reliable**, jadi cocok dengan QoS
  default (`10`) maupun `qos_profile_sensor_data`.
- **Satu robot, satu pengendali.** Kalau dua PC mengirim `/cmd_vel`
  bersamaan, robot mengikuti pesan yang paling baru dan bergerak tidak
  karuan. Sepakati siapa yang memegang `/cmd_vel`.

---

## 4. Contoh

### Hindari halangan (node Python paling sederhana)

> ⚠ Percobaan pertama: **angkat roda dari lantai**.

```bash
./ros.sh python3 /workspace/contoh/hindari_halangan.py
./ros.sh python3 /workspace/contoh/hindari_halangan.py --ros-args -p kecepatan:=0.1 -p jarak_aman:=0.5
```

Robot maju pelan dan berhenti kalau ada benda < 0.6 m di depannya. Baca
kodenya di [`contoh/hindari_halangan.py`](contoh/hindari_halangan.py).

### Teleop keyboard

```bash
./ros.sh ros2 run teleop_twist_keyboard teleop_twist_keyboard --ros-args -p speed:=0.15 -p turn:=0.8
```

Tombol `i` maju, `,` mundur, `u`/`o` maju belok kiri/kanan, `k` berhenti.
**Tahan tombolnya**: robot berhenti 0.5 s setelah tombol dilepas.

### SLAM (membuat peta) — slam_toolbox

Shell 1:

```bash
./ros.sh ros2 launch slam_toolbox online_async_launch.py \
    slam_params_file:=/workspace/contoh/slam.yaml use_sim_time:=false
```

Shell 2: `./ros.sh rviz2`. Set **Fixed Frame = `map`**, lalu tambahkan display
**Map** (`/map`), **LaserScan** (`/scan`), dan **TF**.

Shell 3: jalankan robot pelan keliling ruangan (teleop di atas). Simpan peta:

```bash
./ros.sh ros2 run nav2_map_server map_saver_cli -f /workspace/peta_lab
```

### Navigasi — Nav2

Image kit sudah berisi `navigation2` dan `nav2_bringup`. Frame yang dipakai:
`map` → `odom` → `base_footprint`, scan `/scan`, odometri `/odom`, perintah
`/cmd_vel`. Ingat batasan Ackermann di bagian 3.

---

## 5. Kalau ada masalah

| Gejala | Penyebab | Solusi |
|---|---|---|
| `ros2 topic list` hanya `/parameter_events` dan `/rosout` | firewall PC memblokir UDP dari robot; IP robot salah; `ROS_DOMAIN_ID` beda | aturan ufw (bagian 1); cek IP di OLED; domain = 42 |
| Node kalian sendiri di PC yang sama tidak saling melihat | firewall memblokir discovery lokal | pakai `ros.sh` terbaru (sudah menambahkan peer `127.0.0.1`) |
| `/scan` kosong beberapa detik pertama | LiDAR baru dinyalakan karena ada subscriber | tunggu ~1.5 s |
| Robot tidak bergerak dengan `angular.z` saja | Ackermann: v = 0 → berhenti | beri `linear.x` juga |
| Robot berhenti-berhenti sendiri | `/cmd_vel` dikirim < 2 kali per detik | kirim ≥ 10 Hz |
| RViz: display baru diam tanpa error | Fixed Frame tidak ada (mis. `map` tanpa SLAM) | ganti Fixed Frame ke `odom` |
| Docker Desktop (Windows/macOS) tidak melihat robot | `--net=host` tidak didukung penuh | pakai Linux |
| `docker: permission denied` | user belum di grup docker | `sudo usermod -aG docker $USER`, lalu login ulang |
