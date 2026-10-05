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
# If PyPI downloads stall on your network, use a mirror, e.g.
#   PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/ bash scripts/setup_wsl.sh
PIP=("$VENV/bin/pip" install --timeout 60 --retries 5)
"${PIP[@]}" mediapipe
# MediaPipe needs NumPy 2; Ubuntu's matplotlib is built for NumPy 1, so give the venv its own copy.
"${PIP[@]}" --ignore-installed matplotlib
"$VENV/bin/python" -c "import mediapipe; print('mediapipe', mediapipe.__version__)"
# Fetch the hand model now rather than on first launch.
PYTHONPATH="$(dirname "$0")/../ros2_ws/src/cv_vision" "$VENV/bin/python" -c "from cv_vision.hands import ensure_model; print('model', ensure_model())"
echo "Done. Start with: bash scripts/run_ros.sh"
