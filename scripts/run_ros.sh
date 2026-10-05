#!/usr/bin/env bash
# Build (if needed) and launch the vision stack inside WSL Ubuntu.
#   From Windows:  wsl -d Ubuntu-24.04 -- bash scripts/run_ros.sh [launch args...]
set -e
cd "$(dirname "$0")/.."
REPO="$(pwd)"
VENV="${CV_VENV:-$HOME/cv_venv}"
# colcon on a Windows (OneDrive) mount is slow and fights over file locks, so build in the Linux home.
BUILD_ROOT="${CV_BUILD_ROOT:-$HOME/cv_ws}"

set +u
source /opt/ros/jazzy/setup.bash
set -u

if [ ! -d "$VENV" ]; then
  echo "MediaPipe venv not found at $VENV - run scripts/setup_wsl.sh first" >&2
  exit 1
fi

mkdir -p "$BUILD_ROOT/src"
rsync -a --delete "$REPO/ros2_ws/src/cv_vision/" "$BUILD_ROOT/src/cv_vision/"
(cd "$BUILD_ROOT" && colcon build --symlink-install --packages-select cv_vision >/dev/null)

set +u
source "$BUILD_ROOT/install/setup.bash"
set -u
# ROS entry points use /usr/bin/python3; put the venv's packages (mediapipe) on its path.
export PYTHONPATH="$(echo "$VENV"/lib/python3.*/site-packages):${PYTHONPATH:-}"

IP=$(hostname -I | awk '{print $1}')
echo "rosbridge: ws://localhost:9090 on this PC (WSL IP $IP). Phones: see README 'Connecting a phone'."
exec ros2 launch cv_vision vision.launch.py "$@"
