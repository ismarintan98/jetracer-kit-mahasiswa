#!/usr/bin/env bash
# ROS 2 Humble (container) yang tersambung ke robot JetRacer di jaringan.
#
#   ROBOT_IP=10.17.36.90 ./ros.sh                  # shell ROS 2
#   ROBOT_IP=10.17.36.90 ./ros.sh rviz2            # langsung jalankan perintah
#   ROBOT_IP=10.17.36.90 ./ros.sh ros2 topic list
#
# Variabel:
#   ROBOT_IP       (wajib)  IP robot — tampil di layar OLED robot
#   ROS_DOMAIN_ID  (42)     harus sama dengan robot (config/robot.env di robot)
#   WORKSPACE      (folder ini)  di-mount ke /workspace di container
#
# Butuh: Linux + Docker Engine (bukan Docker Desktop — lihat README.md).
# Image dibangun otomatis saat pertama kali (~5 GB, sekali saja).
#
# DDS: config Cyclone dibuat otomatis — menyapa robot lewat UNICAST (Peer =
# ROBOT_IP) di interface yang memang dipakai untuk mencapai robot. Jalan baik
# di subnet yang sama maupun beda subnet (dirute router).
set -euo pipefail
KIT="$(cd "$(dirname "$0")" && pwd)"

ROBOT_IP="${ROBOT_IP:-}"
ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-42}"
WORKSPACE="${WORKSPACE:-$KIT}"
IMAGE="${IMAGE:-mm_hiwonder/ros-laptop:humble}"
CFG_DIR="$HOME/.cache/jetracer-ros"
CFG="$CFG_DIR/cyclonedds.xml"

if [[ -z "$ROBOT_IP" ]]; then
    echo "!! ROBOT_IP belum diisi. Contoh: ROBOT_IP=10.17.36.90 $0" >&2
    echo "   IP robot tampil di layar OLED robot." >&2
    exit 1
fi

# --- akses docker -----------------------------------------------------------
# Tanpa cek ini, akses yang ditolak terbaca sebagai "image belum ada" dan
# ros.sh mencoba build ~5 GB yang lalu gagal dengan pesan membingungkan.
if ! command -v docker >/dev/null; then
    echo "!! Docker belum terpasang. Jalankan dulu: ./setup.sh" >&2
    exit 1
fi
if ! err=$(docker info 2>&1 >/dev/null); then
    me=$(id -un)
    if grep -qi "permission denied" <<<"$err"; then
        if id -nG "$me" | tr ' ' '\n' | grep -qx docker; then
            echo "!! $me sudah masuk grup docker, tapi sesi login ini belum." >&2
            echo "   LOGOUT lalu LOGIN lagi (atau reboot). Menutup terminal saja tidak cukup." >&2
            echo "   Sementara, di terminal ini: newgrp docker   lalu jalankan ./ros.sh lagi." >&2
        else
            echo "!! $me belum boleh memakai Docker (bukan anggota grup docker)." >&2
            echo "   Jalankan ./setup.sh (atau: sudo usermod -aG docker $me), lalu LOGOUT & LOGIN lagi." >&2
        fi
    else
        echo "!! Docker tidak bisa dihubungi:" >&2
        sed 's/^/   /' <<<"$err" >&2
        echo "   Daemon mati? Coba: sudo systemctl start docker" >&2
    fi
    exit 1
fi

# --- image ------------------------------------------------------------------
if ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
    echo ">> Membangun image $IMAGE (sekali saja, ~5 GB unduhan)..."
    docker build -t "$IMAGE" --build-arg UID="$(id -u)" --build-arg GID="$(id -g)" "$KIT"
fi

# --- config DDS sesuai jalur ke robot ---------------------------------------
route=$(ip -4 route get "$ROBOT_IP" 2>/dev/null || true)
IFACE=$(sed -n 's/.* dev \([^ ]*\).*/\1/p' <<<"$route")
SRC=$(sed -n 's/.* src \([^ ]*\).*/\1/p' <<<"$route")
if [[ -z "$IFACE" ]]; then
    echo "!! Tidak ada rute ke robot $ROBOT_IP — cek jaringan." >&2
    exit 1
fi
if ! ping -c 1 -W 2 "$ROBOT_IP" >/dev/null 2>&1; then
    echo "!! Robot $ROBOT_IP tidak menjawab ping — robot mati / IP salah / beda jaringan?" >&2
fi
mkdir -p "$CFG_DIR"
cat > "$CFG" <<XML
<?xml version="1.0" encoding="UTF-8"?>
<!-- Dibuat otomatis oleh ros.sh — jangan diedit. -->
<CycloneDDS xmlns="https://cdds.io/config">
  <Domain id="any">
    <General>
      <Interfaces><NetworkInterface name="$IFACE" priority="default"/></Interfaces>
    </General>
    <Discovery>
      <ParticipantIndex>auto</ParticipantIndex>
      <MaxAutoParticipantIndex>32</MaxAutoParticipantIndex>
      <Peers>
        <Peer address="$ROBOT_IP"/>
        <!-- Node-node di PC ini sendiri. Tanpa ini, firewall (ufw dsb.) yang
             hanya mengizinkan subnet robot membuang multicast discovery lokal
             -> slam_toolbox / rviz / node sendiri tidak saling melihat. -->
        <Peer address="127.0.0.1"/>
      </Peers>
    </Discovery>
    <Internal><SocketReceiveBufferSize max="4MB"/></Internal>
    <Tracing><Verbosity>warning</Verbosity><OutputFile>stderr</OutputFile></Tracing>
  </Domain>
</CycloneDDS>
XML
echo ">> robot $ROBOT_IP lewat $IFACE ($SRC), ROS_DOMAIN_ID=$ROS_DOMAIN_ID" >&2

# --- tampilan (X11 / XWayland) ----------------------------------------------
X_ARGS=()
if [[ -n "${DISPLAY:-}" ]]; then
    X_ARGS+=(-e DISPLAY="$DISPLAY" -v /tmp/.X11-unix:/tmp/.X11-unix:ro)
    if [[ -n "${XAUTHORITY:-}" && -f "$XAUTHORITY" ]]; then
        X_ARGS+=(-e XAUTHORITY=/tmp/.Xauthority -v "$XAUTHORITY:/tmp/.Xauthority:ro")
    fi
    [[ -e /dev/dri ]] && X_ARGS+=(--device /dev/dri)
fi

TTY_ARGS=(-i)
[[ -t 0 && -t 1 ]] && TTY_ARGS=(-it)

exec docker run --rm "${TTY_ARGS[@]}" \
    --net=host --ipc=host \
    --user "$(id -u):$(id -g)" \
    -e HOME=/tmp/home -e ROS_DOMAIN_ID="$ROS_DOMAIN_ID" \
    -e RMW_IMPLEMENTATION=rmw_cyclonedds_cpp \
    -e CYCLONEDDS_URI=file:///cfg/cyclonedds.xml \
    -v "$CFG:/cfg/cyclonedds.xml:ro" \
    -v "$WORKSPACE:/workspace" \
    -v "$KIT/model:/opt/jetracer_model:ro" \
    -v "$KIT/lib:/opt/jetracer_lib:ro" \
    -e AMENT_PREFIX_PATH=/opt/jetracer_model \
    "${X_ARGS[@]}" \
    "$IMAGE" bash -c 'mkdir -p "$HOME"; source /opt/ros/humble/setup.bash
        # Paket buatan sendiri (colcon build di /workspace/ros2_ws) — supaya
        # `./ros.sh ros2 run <paket> ...` juga menemukannya, bukan hanya shell interaktif.
        [ -f /workspace/ros2_ws/install/setup.bash ] && source /workspace/ros2_ws/install/setup.bash
        export PYTHONPATH="/opt/jetracer_lib:$PYTHONPATH"     # import ros1_style
        exec "${@:-bash}"' _ "$@"
