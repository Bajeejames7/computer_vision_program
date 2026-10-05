"""Hand landmark tracking with MediaPipe Tasks, plus a simple gesture classifier."""
import math
import os
import time
import urllib.request
from dataclasses import dataclass

import cv2

MODEL_URL = ('https://storage.googleapis.com/mediapipe-models/hand_landmarker/'
             'hand_landmarker/float16/latest/hand_landmarker.task')
DEFAULT_MODEL_PATH = os.path.expanduser('~/.cache/cv_vision/hand_landmarker.task')

# MediaPipe's 21-point hand topology.
HAND_CONNECTIONS = [
    (0, 1), (1, 2), (2, 3), (3, 4),          # thumb
    (0, 5), (5, 6), (6, 7), (7, 8),          # index
    (5, 9), (9, 10), (10, 11), (11, 12),     # middle
    (9, 13), (13, 14), (14, 15), (15, 16),   # ring
    (13, 17), (17, 18), (18, 19), (19, 20),  # pinky
    (0, 17),
]
FINGER_NAMES = ['thumb', 'index', 'middle', 'ring', 'pinky']


@dataclass
class Hand:
    handedness: str          # 'Left' / 'Right' as reported by MediaPipe
    score: float
    landmarks: list          # 21 x [x, y, z], x/y normalised to the frame
    box: tuple               # normalised (x, y, w, h)
    fingers: list            # extended fingers, in FINGER_NAMES order
    gesture: str

    def to_dict(self):
        return {
            'handedness': self.handedness,
            'score': round(self.score, 3),
            'box': [round(v, 4) for v in self.box],
            'fingers': self.fingers,
            'gesture': self.gesture,
            'landmarks': [[round(v, 4) for v in p] for p in self.landmarks],
        }


def ensure_model(path=DEFAULT_MODEL_PATH):
    if not os.path.exists(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + '.part'
        urllib.request.urlretrieve(MODEL_URL, tmp)
        os.replace(tmp, path)
    return path


def _dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def extended_fingers(lm):
    """Which fingers are straightened, judged by distance from the wrist so it works at any hand rotation."""
    wrist = lm[0]
    up = []
    # Thumb: tip is clearly further from the pinky base than the thumb's IP joint.
    if _dist(lm[4], lm[17]) > _dist(lm[3], lm[17]) * 1.1 and _dist(lm[4], lm[5]) > _dist(lm[0], lm[5]) * 0.45:
        up.append('thumb')
    for name, tip, pip in (('index', 8, 6), ('middle', 12, 10), ('ring', 16, 14), ('pinky', 20, 18)):
        if _dist(lm[tip], wrist) > _dist(lm[pip], wrist) * 1.1:
            up.append(name)
    return up


def classify_gesture(fingers):
    s = set(fingers)
    if not s:
        return 'fist'
    if len(s) == 5:
        return 'open_palm'
    if s == {'thumb'}:
        return 'thumbs_up'
    if s == {'index'}:
        return 'pointing'
    if s == {'index', 'middle'}:
        return 'peace'
    if s == {'index', 'pinky'}:
        return 'rock'
    if s == {'thumb', 'pinky'}:
        return 'call_me'
    return f'{len(s)}_fingers'


def hand_from_landmarks(lm, handedness='Unknown', score=1.0):
    xs = [p[0] for p in lm]
    ys = [p[1] for p in lm]
    x0, y0 = max(0.0, min(xs)), max(0.0, min(ys))
    x1, y1 = min(1.0, max(xs)), min(1.0, max(ys))
    fingers = extended_fingers(lm)
    return Hand(handedness, score, lm, (x0, y0, x1 - x0, y1 - y0), fingers, classify_gesture(fingers))


class HandTracker:
    def __init__(self, model_path=DEFAULT_MODEL_PATH, max_hands=2, min_detection=0.5,
                 min_presence=0.5, min_tracking=0.5):
        # Imported lazily so the rest of the package (and its tests) works without MediaPipe.
        import mediapipe as mp
        from mediapipe.tasks.python import BaseOptions
        from mediapipe.tasks.python import vision

        self._mp = mp
        options = vision.HandLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=ensure_model(model_path)),
            running_mode=vision.RunningMode.VIDEO,
            num_hands=max_hands,
            min_hand_detection_confidence=min_detection,
            min_hand_presence_confidence=min_presence,
            min_tracking_confidence=min_tracking,
        )
        self._landmarker = vision.HandLandmarker.create_from_options(options)
        self._last_ts = 0

    def process(self, frame_bgr):
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        image = self._mp.Image(image_format=self._mp.ImageFormat.SRGB, data=rgb)
        # VIDEO mode needs strictly increasing timestamps.
        ts = max(self._last_ts + 1, int(time.monotonic() * 1000))
        self._last_ts = ts
        result = self._landmarker.detect_for_video(image, ts)

        hands = []
        for i, lms in enumerate(result.hand_landmarks):
            cat = result.handedness[i][0] if i < len(result.handedness) else None
            pts = [[p.x, p.y, p.z] for p in lms]
            hands.append(hand_from_landmarks(
                pts, cat.category_name if cat else 'Unknown', cat.score if cat else 0.0))
        return hands

    def close(self):
        self._landmarker.close()
