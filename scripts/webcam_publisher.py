"""Stream a Windows/macOS/Linux webcam into ROS2 through rosbridge.

WSL can't see USB webcams, so this runs on the host OS and publishes JPEG frames to
/cv/image/compressed. Phones can then "Watch only" the processed feed.

    pip install opencv-python websocket-client
    python scripts/webcam_publisher.py                       # camera 0 -> ws://localhost:9090
    python scripts/webcam_publisher.py --camera 1 --fps 20 --preview
"""
import argparse
import base64
import json
import os
import socket
import time

import cv2
import websocket  # websocket-client

TOPIC = '/cv/image/compressed'
TYPE = 'sensor_msgs/msg/CompressedImage'


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--url', default='ws://localhost:9090')
    ap.add_argument('--camera', type=int, default=0)
    ap.add_argument('--width', type=int, default=640)
    ap.add_argument('--fps', type=float, default=15)
    ap.add_argument('--quality', type=int, default=70)
    ap.add_argument('--mirror', action='store_true', help='flip horizontally (selfie view)')
    ap.add_argument('--preview', action='store_true', help='show the raw camera in a window')
    args = ap.parse_args()

    # DirectShow opens most Windows webcams much faster than the default MSMF backend.
    backend = cv2.CAP_DSHOW if os.name == 'nt' else cv2.CAP_ANY
    cap = cv2.VideoCapture(args.camera, backend)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, args.width)
    if not cap.isOpened():
        raise SystemExit(f'Could not open camera {args.camera}')

    frame_id = f'webcam-{socket.gethostname()}'
    period = 1.0 / args.fps
    ws = None
    sent, t_report = 0, time.time()
    try:
        while True:
            if ws is None:
                try:
                    ws = websocket.create_connection(args.url, timeout=5)
                    ws.send(json.dumps({'op': 'advertise', 'topic': TOPIC, 'type': TYPE}))
                    print(f'Connected to {args.url}, publishing {TOPIC}')
                except OSError as e:
                    print(f'rosbridge not reachable at {args.url} ({e}); retrying...')
                    ws = None
                    time.sleep(2)
                    continue

            t0 = time.time()
            ok, frame = cap.read()
            if not ok:
                time.sleep(0.1)
                continue
            if frame.shape[1] > args.width:
                frame = cv2.resize(frame, (args.width, int(frame.shape[0] * args.width / frame.shape[1])))
            if args.mirror:
                frame = cv2.flip(frame, 1)
            ok, buf = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), args.quality])
            now = time.time()
            msg = {
                'op': 'publish', 'topic': TOPIC,
                'msg': {
                    'header': {'stamp': {'sec': int(now), 'nanosec': int((now % 1) * 1e9)}, 'frame_id': frame_id},
                    'format': 'jpeg',
                    'data': base64.b64encode(buf.tobytes()).decode('ascii'),
                },
            }
            try:
                ws.send(json.dumps(msg))
            except OSError:
                print('Connection lost; reconnecting...')
                ws = None
                continue

            sent += 1
            if now - t_report >= 5:
                print(f'{sent / (now - t_report):.1f} fps sent')
                sent, t_report = 0, now
            if args.preview:
                cv2.imshow('webcam (q to quit)', frame)
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break
            time.sleep(max(0.0, period - (time.time() - t0)))
    except KeyboardInterrupt:
        pass
    finally:
        cap.release()
        if ws:
            ws.close()
        cv2.destroyAllWindows()


if __name__ == '__main__':
    main()
