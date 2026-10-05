#!/usr/bin/env bash
# One-time setup inside WSL Ubuntu 24.04 with ROS2 Jazzy already installed.
#   wsl -d Ubuntu-24.04 -- bash scripts/setup_wsl.sh
set -e
SUDO=""; [ "$(id -u)" -ne 0 ] && SUDO="sudo"
export DEBIAN_FRONTEND=noninteractive
$SUDO apt-get update
$SUDO apt-get install -y ros-jazzy-rosbridge-suite ros-jazzy-vision-msgs python3-pip python3-venv \
  python3-colcon-common-extensions python3-pytest rsync

VENV="${CV_VENV:-$HOME/cv_venv}"
# --system-site-packages keeps rclpy and the ROS message packages importable from the venv.
python3 -m venv --system-site-packages "$VENV"
"$VENV/bin/pip" install --upgrade pip
"$VENV/bin/pip" install mediapipe
"$VENV/bin/python" -c "import mediapipe; print('mediapipe', mediapipe.__version__)"
echo "Done. Start with: bash scripts/run_ros.sh"
