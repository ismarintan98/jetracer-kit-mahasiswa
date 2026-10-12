#!/usr/bin/env bash
# Setup PC mahasiswa — jalankan SEKALI sebelum memakai ros.sh.
#
#   ./setup.sh                              # subnet robot default 10.17.36.0/22
#   ./setup.sh --subnet 192.168.1.0/24      # subnet jaringan robot (tanya dosen)
#   ./setup.sh --robot-ip 10.17.36.90       # sekaligus tes sambungan ke robot
#   ./setup.sh --rebuild                    # bangun ulang image (mis. Dockerfile berubah)
#
# Yang dipasang / disiapkan:
#   1. Docker Engine + iproute2 + ping (paket distro)
#   2. user masuk grup docker, service docker menyala sejak boot
#   3. image ROS 2 Humble kit (Nav2, slam_toolbox, teleop, rqt, CycloneDDS)
#   4. aturan firewall agar robot bisa mengirim DDS ke PC (ufw / firewalld)
#   5. folder kerja ros2_ws/src dan peta/
#
# Aman dijalankan berulang: langkah yang sudah beres dilewati.
# Distro: Ubuntu, Debian (dan turunannya: Mint, Pop!_OS, ...), Fedora, Arch.
# Tidak untuk WSL / Docker Desktop — lihat README.md bagian 1.
set -euo pipefail
KIT="$(cd "$(dirname "$0")" && pwd)"

IMAGE="${IMAGE:-mm_hiwonder/ros-laptop:humble}"   # harus sama dengan ros.sh
SUBNET="10.17.36.0/22"
DDS_PORTS="17900:17999"                           # ROS_DOMAIN_ID 42
ROBOT_IP="${ROBOT_IP:-}"
REBUILD=0
MIN_DISK_GB=8

info() { echo ">> $*"; }
warn() { echo "!! $*" >&2; }
die()  { warn "$*"; exit 1; }

usage() { sed -n '2,8p' "$0" | sed 's/^# \{0,1\}//'; exit "${1:-0}"; }

while [[ $# -gt 0 ]]; do
    case "$1" in
        --subnet)   SUBNET="${2:?--subnet butuh nilai, mis. 10.17.36.0/22}"; shift 2 ;;
        --robot-ip) ROBOT_IP="${2:?--robot-ip butuh nilai, mis. 10.17.36.90}"; shift 2 ;;
        --rebuild)  REBUILD=1; shift ;;
        -h|--help)  usage ;;
        *)          warn "Opsi tidak dikenal: $1"; usage 1 ;;
    esac
done

# --- 0. cek lingkungan ------------------------------------------------------
[[ "$(uname -s)" == Linux ]] \
    || die "Kit ini butuh Linux. Di Windows/macOS pakai Ubuntu dual-boot atau PC lab Linux."
grep -qi microsoft /proc/version 2>/dev/null \
    && die "Terdeteksi WSL. DDS dari WSL tidak bisa menjangkau robot; pakai Ubuntu dual-boot atau PC lab Linux."
[[ $EUID -ne 0 ]] \
    || die "Jalankan sebagai user biasa, tanpa sudo: ./setup.sh (script memanggil sudo sendiri)."
[[ -r /etc/os-release ]] || die "/etc/os-release tidak ada — distro tidak dikenali."
# shellcheck disable=SC1091
. /etc/os-release
DISTRO=" ${ID:-} ${ID_LIKE:-} "

info "Kit: $KIT"
info "Distro: ${PRETTY_NAME:-$ID}"
info "Langkah yang butuh root akan meminta password sudo."
sudo -v || die "sudo gagal — user ini harus punya hak sudo."

# --- 1. paket: docker, ip, ping ---------------------------------------------
pkgs=()
case "$DISTRO" in
    *" ubuntu "*|*" debian "*)
        command -v docker >/dev/null || pkgs+=(docker.io)
        command -v ip     >/dev/null || pkgs+=(iproute2)
        command -v ping   >/dev/null || pkgs+=(iputils-ping)
        pkg_install() { sudo apt-get update && sudo apt-get install -y "$@"; } ;;
    *" fedora "*)
        command -v docker >/dev/null || pkgs+=(moby-engine)
        command -v ip     >/dev/null || pkgs+=(iproute)
        command -v ping   >/dev/null || pkgs+=(iputils)
        pkg_install() { sudo dnf install -y "$@"; } ;;
    *" arch "*)
        command -v docker >/dev/null || pkgs+=(docker docker-buildx)
        command -v ip     >/dev/null || pkgs+=(iproute2)
        command -v ping   >/dev/null || pkgs+=(iputils)
        pkg_install() { sudo pacman -S --needed --noconfirm "$@"; } ;;
    *)
        command -v docker >/dev/null \
            || die "Distro '$ID' belum didukung script ini. Pasang Docker Engine manual, lalu jalankan ulang."
        pkg_install() { die "Pasang manual: $*"; } ;;
esac

if [[ ${#pkgs[@]} -gt 0 ]]; then
    info "[1/5] Memasang: ${pkgs[*]}"
    pkg_install "${pkgs[@]}"
else
    info "[1/5] Docker, ip, ping sudah terpasang — dilewati."
fi

# Docker Desktop for Linux memakai VM, sama seperti di Windows/macOS.
if [[ "$(docker context show 2>/dev/null || true)" == desktop-linux ]]; then
    die "Docker Desktop terdeteksi (--net=host tidak sampai ke robot). Pindah ke Docker Engine: docker context use default"
fi

# --- 2. service & grup docker -----------------------------------------------
info "[2/5] Service & grup docker"
if command -v systemctl >/dev/null; then
    if ! systemctl is-active --quiet docker || ! systemctl is-enabled --quiet docker; then
        sudo systemctl enable --now docker
    fi
fi
getent group docker >/dev/null || sudo groupadd docker

RELOGIN=0
if ! id -nG "$USER" | tr ' ' '\n' | grep -qx docker; then
    info "   menambahkan $USER ke grup docker"
    sudo usermod -aG docker "$USER"
fi
# Grup baru baru berlaku setelah login ulang; sampai saat itu pakai sudo.
if docker info >/dev/null 2>&1; then
    DOCKER=(docker)
else
    DOCKER=(sudo docker)
    RELOGIN=1
fi
"${DOCKER[@]}" info >/dev/null 2>&1 || die "Docker daemon tidak menjawab. Cek: sudo systemctl status docker"

if command -v getenforce >/dev/null && [[ "$(getenforce)" == Enforcing ]]; then
    warn "SELinux Enforcing: mount folder kit ke container bisa ditolak (Permission denied)."
    warn "Kalau terjadi: sudo chcon -Rt container_file_t \"$KIT\""
fi

# --- 3. image ROS 2 ---------------------------------------------------------
if [[ $REBUILD == 0 ]] && "${DOCKER[@]}" image inspect "$IMAGE" >/dev/null 2>&1; then
    info "[3/5] Image $IMAGE sudah ada — dilewati (pakai --rebuild untuk membangun ulang)."
else
    root_dir=$("${DOCKER[@]}" info -f '{{.DockerRootDir}}' 2>/dev/null || echo /var/lib/docker)
    avail=$(df -BG --output=avail "$root_dir" 2>/dev/null | tail -1 | tr -dc 0-9 || true)
    if [[ -n "$avail" && "$avail" -lt $MIN_DISK_GB ]]; then
        die "Ruang kosong di $root_dir hanya ${avail} GB; image butuh ±${MIN_DISK_GB} GB."
    fi
    build_args=(-t "$IMAGE" --build-arg UID="$(id -u)" --build-arg GID="$(id -g)")
    [[ $REBUILD == 1 ]] && build_args+=(--pull --no-cache)
    info "[3/5] Membangun image $IMAGE (±5 GB unduhan, 10–30 menit tergantung internet)..."
    "${DOCKER[@]}" build "${build_args[@]}" "$KIT"
fi

info "   cek paket ROS 2 di image"
"${DOCKER[@]}" run --rm "$IMAGE" bash -c '
    source /opt/ros/humble/setup.bash
    ok=1
    for p in rmw_cyclonedds_cpp nav2_bringup slam_toolbox teleop_twist_keyboard rviz2 rqt_image_view; do
        if ros2 pkg prefix "$p" >/dev/null 2>&1; then echo "   ok  $p"; else echo "   !!  $p TIDAK ADA"; ok=0; fi
    done
    [ $ok = 1 ]' || die "Image tidak lengkap. Bangun ulang: ./setup.sh --rebuild"

# --- 4. firewall ------------------------------------------------------------
info "[4/5] Firewall: izinkan UDP $DDS_PORTS dari $SUBNET"
fw_done=0
if command -v ufw >/dev/null && sudo ufw status 2>/dev/null | grep -q "Status: active"; then
    sudo ufw allow proto udp from "$SUBNET" to any port "$DDS_PORTS" comment 'ROS2 DDS robot JetRacer'
    fw_done=1
fi
if command -v firewall-cmd >/dev/null && sudo firewall-cmd --state >/dev/null 2>&1; then
    rule="rule family=ipv4 source address=$SUBNET port port=${DDS_PORTS/:/-} protocol=udp accept"
    if ! sudo firewall-cmd --permanent --query-rich-rule="$rule" >/dev/null 2>&1; then
        sudo firewall-cmd --permanent --add-rich-rule="$rule"
        sudo firewall-cmd --reload
    fi
    fw_done=1
fi
[[ $fw_done == 1 ]] || info "   ufw/firewalld tidak aktif — tidak ada yang perlu diubah."

# --- 5. folder kerja --------------------------------------------------------
info "[5/5] Folder kerja"
mkdir -p "$KIT/ros2_ws/src" "$KIT/peta"
chmod +x "$KIT/ros.sh" "$KIT/nav/simpan_peta.sh"

# --- tes sambungan (opsional) -----------------------------------------------
if [[ -n "$ROBOT_IP" ]]; then
    info "Tes sambungan ke robot $ROBOT_IP ..."
    if [[ $RELOGIN == 0 ]]; then
        topics=$(ROBOT_IP="$ROBOT_IP" "$KIT/ros.sh" ros2 topic list </dev/null || true)
    elif command -v sg >/dev/null; then
        topics=$(sg docker -c "ROBOT_IP='$ROBOT_IP' '$KIT/ros.sh' ros2 topic list" </dev/null || true)
    else
        topics=""
        warn "Tes dilewati: grup docker belum aktif di sesi ini (login ulang dulu)."
    fi
    if grep -qx /odom <<<"$topics"; then
        info "   OK — topik robot terlihat:"
        sed 's/^/      /' <<<"$topics"
    elif [[ -n "$topics" ]]; then
        warn "Topik robot (/odom, /scan, ...) tidak terlihat. Kemungkinan:"
        warn "  - IP robot salah (lihat OLED) atau robot belum selesai boot"
        warn "  - subnet firewall salah: jalankan ulang dengan --subnet <subnet robot>"
        warn "  - PC dan robot tidak satu jaringan: ping $ROBOT_IP"
    fi
fi

# --- ringkasan --------------------------------------------------------------
echo
info "Setup selesai."
if [[ $RELOGIN == 1 ]]; then
    warn "PENTING: LOGOUT lalu LOGIN lagi (atau reboot) supaya grup docker berlaku."
    warn "Sebelum itu ./ros.sh akan gagal dengan 'permission denied'."
fi
cat <<EOF

Langkah berikutnya (IP robot tampil di layar OLED robot):
  cd "$KIT"
  export ROBOT_IP=10.17.36.90        # ganti dengan IP robot
  ./ros.sh ros2 topic list           # cek sambungan
  ./ros.sh rviz2                     # RViz
  ./ros.sh                           # shell ROS 2 interaktif

Panduan lengkap: README.md
EOF
