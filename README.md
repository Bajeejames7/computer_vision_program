# Computer Vision Program — motion + hand tracking on ROS2

Detects **movement** (bounding boxes + a decaying **motion heatmap**) and **hands** (21-point
**skeleton**, left/right, simple gestures) in a camera feed. The processing runs as **ROS2 Jazzy** nodes;
an **Expo app** (Android, iOS, and web/desktop) sends its camera to ROS and shows the annotated result.

```
 Phone / browser (Expo app)                 PC: WSL2 Ubuntu 24.04 + ROS2 Jazzy
 ┌───────────────────────┐   WebSocket   ┌──────────────┐  /cv/image/compressed  ┌─────────────┐
 │ camera ─ JPEG frames ─┼──────────────▶│  rosbridge   │───────────────────────▶│ motion_node │─┐
 │                       │               │  :9090       │                        ├─────────────┤ │
 │ annotated feed, stats ◀───────────────┤              │◀── /cv/annotated ──┐   │ hand_node   │─┤ detections,
 │ overlay toggles ──────┼──────────────▶│              │── /cv/overlay_config ▶ └─────────────┘ │ heatmap,
 └───────────────────────┘               └──────────────┘                    │   ┌─────────────┐ │ landmarks
 webcam_publisher.py (PC webcam) ───────────────▲                            └───│ overlay_node│◀┘
                                                                                 └─────────────┘
```

## ROS2 interface

| Topic | Type | Notes |
|---|---|---|
| `/cv/image/compressed` | `sensor_msgs/CompressedImage` | **input** (JPEG). Change with `input_topic:=...` |
| `/cv/motion/detections` | `vision_msgs/Detection2DArray` | moving regions, pixel coords, `class_id: motion` |
| `/cv/motion/heatmap/compressed` | `sensor_msgs/CompressedImage` | grayscale heat (255 = most movement) |
| `/cv/motion/level` | `std_msgs/Float32` | fraction of the frame that's moving |
| `/cv/hands/detections` | `vision_msgs/Detection2DArray` | hand boxes, `class_id: Left/Right` |
| `/cv/hands/landmarks` | `std_msgs/String` (JSON) | 21 landmarks per hand + `fingers` + `gesture` |
| `/cv/annotated/compressed` | `sensor_msgs/CompressedImage` | frame with boxes / skeleton / heatmap drawn |
| `/cv/stats` | `std_msgs/String` (JSON) | fps, motion level, hands, gestures |
| `/cv/overlay_config` | `std_msgs/String` (JSON) | `{"boxes":true,"skeleton":true,"heatmap":false}` |

Gestures: `fist`, `open_palm`, `pointing`, `peace`, `thumbs_up`, `rock`, `call_me`, otherwise `N_fingers`.
Because the input is a normal ROS topic, any camera driver works too, e.g.
`ros2 launch cv_vision vision.launch.py input_topic:=/camera/image_raw/compressed`.

## 1. Set up the PC (once)

ROS2 Jazzy lives in WSL (`Ubuntu-24.04`). From the repo folder in PowerShell:

```powershell
wsl -d Ubuntu-24.04 -- bash scripts/setup_wsl.sh      # rosbridge, MediaPipe venv
```

## 2. Start the vision stack

```powershell
wsl -d Ubuntu-24.04 -- bash scripts/run_ros.sh        # builds into ~/cv_ws and launches everything
# options: hands:=false  motion:=false  port:=9091  input_topic:=/some/topic
```

The first run downloads the MediaPipe hand model (~7 MB) to `~/.cache/cv_vision/`.

## 3. Run the app

```powershell
cd app
npm install
npx expo start            # press w for the browser (desktop), or scan the QR with Expo Go on a phone
```

* **Computer:** open the web version (`w`), host `localhost`, **Connect**, choose **Send this camera**.
* **Phone (Android or iOS):** install **Expo Go**, scan the QR code, enter your PC's Wi-Fi IP, **Connect**.
  * **Send this camera** streams the phone camera to ROS and shows the processed feed.
  * **Watch only** shows whatever camera is streaming (e.g. the PC webcam).

### Connecting a phone

WSL2 only exposes ports to Windows itself. To let phones on your Wi-Fi reach rosbridge, run once per boot
in an **Administrator** PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\expose-to-phone.ps1     # prints the IP to type in the app
```

Your Wi-Fi network must be set to *Private* in Windows. Undo with `-Remove`.

### PC webcam without the browser

```powershell
pip install opencv-python websocket-client
python scripts\webcam_publisher.py --preview     # then use "Watch only" in the app
```

## Building installable apps

Expo Go is enough for testing. For a standalone Android APK: `cd app && npx expo prebuild -p android && cd android && ./gradlew assembleRelease`.
iOS standalone builds need a Mac or EAS Build plus an Apple developer account.

## Tests

```bash
# inside WSL, after run_ros.sh has built once
cd ~/cv_ws/src/cv_vision && python3 -m pytest -q test
```

## Layout

```
ros2_ws/src/cv_vision/      ROS2 package (ament_python)
  cv_vision/motion.py       MOG2 background subtraction, boxes, decaying heatmap
  cv_vision/hands.py        MediaPipe Hand Landmarker + finger/gesture classifier
  cv_vision/drawing.py      overlay rendering
  cv_vision/*_node.py       ROS2 nodes
  launch/vision.launch.py   rosbridge + all nodes
  config/params.yaml        tuning (sensitivity, heat decay, confidence...)
app/                        Expo (SDK 57) app — Android, iOS, web
scripts/                    WSL setup/run, phone port forwarding, webcam publisher
```
