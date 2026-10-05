#!/usr/bin/env bash
# Simpan peta dari slam_toolbox yang sedang jalan (mapping.launch.py).
#
#   ./ros.sh /workspace/nav/simpan_peta.sh lab
#
# Menghasilkan di /workspace/peta/ (= folder peta/ di kit):
#   lab.posegraph + lab.data  -> untuk localization.launch.py (slam_toolbox)
#   lab.pgm + lab.yaml        -> peta gambar, untuk Nav2 / AMCL / laporan
set -euo pipefail
NAMA="${1:?pakai: simpan_peta.sh <nama>}"
DIR=/workspace/peta
mkdir -p "$DIR"

echo ">> pose graph (untuk lokalisasi slam_toolbox)..."
ros2 service call /slam_toolbox/serialize_map slam_toolbox/srv/SerializePoseGraph \
    "{filename: '$DIR/$NAMA'}" | tail -1
echo ">> peta gambar .pgm/.yaml (untuk Nav2)..."
ros2 service call /slam_toolbox/save_map slam_toolbox/srv/SaveMap \
    "{name: {data: '$DIR/$NAMA'}}" | tail -1
sleep 1
ls -la "$DIR/$NAMA".* 2>/dev/null || echo "!! file peta tidak terbentuk — mapping.launch.py jalan?"
