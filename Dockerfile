# ROS 2 Humble untuk LAPTOP (x86_64): RViz, alat debug, SLAM & Nav2.
#
# Laptop memakai CachyOS (Arch) — ROS 2 Humble tidak tersedia native, jadi
# lewat container. Di sini paket biner apt tersedia lengkap (beda dengan
# robot/bionic), karena itu navigasi berat dijalankan di sisi laptop.
#
# Dibangun otomatis oleh ros.sh (kit mahasiswa) — tidak perlu dipanggil manual.
FROM osrf/ros:humble-desktop

RUN apt-get update && apt-get install -y --no-install-recommends \
        ros-humble-rmw-cyclonedds-cpp \
        ros-humble-navigation2 \
        ros-humble-nav2-bringup \
        ros-humble-slam-toolbox \
        ros-humble-teleop-twist-keyboard \
        ros-humble-rqt-image-view \
        ros-humble-rqt-robot-steering \
        ros-humble-image-transport-plugins \
        iproute2 iputils-ping \
    && rm -rf /var/lib/apt/lists/*

# User yang UID/GID-nya sama dengan user laptop — file yang dibuat container
# (peta SLAM, bag) tidak jadi milik root, dan socket X11 bisa dipakai.
ARG UID=1000
ARG GID=1000
RUN groupadd -g ${GID} ros || true \
    && useradd -m -u ${UID} -g ${GID} -s /bin/bash ros || true \
    && echo 'source /opt/ros/humble/setup.bash' >> /etc/bash.bashrc \
    && echo '[ -f /workspace/ros2_ws/install/setup.bash ] && source /workspace/ros2_ws/install/setup.bash' >> /etc/bash.bashrc

ENV RMW_IMPLEMENTATION=rmw_cyclonedds_cpp \
    ROS_DOMAIN_ID=42
WORKDIR /workspace
