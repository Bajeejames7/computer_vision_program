import numpy as np

from cv_vision.drawing import blend_heatmap, draw_hands, draw_motion_boxes
from cv_vision.hands import classify_gesture, extended_fingers, hand_from_landmarks
from cv_vision.motion import MotionDetector


def _frame_with_square(x, size=40, w=320, h=240):
    f = np.full((h, w, 3), 90, np.uint8)
    f[100:100 + size, x:x + size] = 255
    return f


def test_static_scene_has_no_motion():
    det = MotionDetector()
    for _ in range(30):
        res = det.update(np.full((240, 320, 3), 90, np.uint8))
    assert res.boxes == []
    assert res.level == 0.0


def test_moving_square_is_detected_and_heats_up():
    det = MotionDetector()
    for _ in range(30):
        det.update(np.full((240, 320, 3), 90, np.uint8))
    for x in range(20, 200, 15):
        res = det.update(_frame_with_square(x))
    assert res.boxes, 'expected a motion box'
    b = res.boxes[0]
    cx = b.x + b.w / 2
    assert 0.45 < cx < 0.8          # box is around the square's last position (x~185..225 of 320)
    assert 0.3 < b.y + b.h / 2 < 0.65
    assert res.level > 0
    assert res.heat.max() > 0


def test_resolution_change_resets_model():
    det = MotionDetector()
    det.update(np.zeros((240, 320, 3), np.uint8))
    res = det.update(np.zeros((320, 240, 3), np.uint8))
    assert res.heat.shape == (320, 240)


def _hand(extended):
    """Synthetic upright right hand: wrist at bottom, fingers pointing up; curled fingers fold back."""
    lm = [[0.5, 0.9, 0.0]] + [[0, 0, 0]] * 20
    lm = [list(p) for p in lm]
    bases = {'thumb': (1, 0.38), 'index': (5, 0.45), 'middle': (9, 0.5), 'ring': (13, 0.55), 'pinky': (17, 0.6)}
    for name, (start, x) in bases.items():
        if name == 'thumb':
            xs = [0.42, 0.36, 0.30, 0.24] if 'thumb' in extended else [0.44, 0.42, 0.45, 0.48]
            ys = [0.82, 0.76, 0.71, 0.67] if 'thumb' in extended else [0.82, 0.76, 0.72, 0.70]
            for i in range(4):
                lm[start + i] = [xs[i], ys[i], 0.0]
            continue
        ys = [0.65, 0.5, 0.4, 0.3] if name in extended else [0.65, 0.55, 0.62, 0.7]
        for i in range(4):
            lm[start + i] = [x, ys[i], 0.0]
    return lm


def test_gestures():
    assert classify_gesture(extended_fingers(_hand([]))) == 'fist'
    assert classify_gesture(extended_fingers(_hand(['index']))) == 'pointing'
    assert classify_gesture(extended_fingers(_hand(['index', 'middle']))) == 'peace'
    assert classify_gesture(extended_fingers(_hand(['thumb', 'index', 'middle', 'ring', 'pinky']))) == 'open_palm'


def test_hand_box_and_drawing_do_not_crash():
    hand = hand_from_landmarks(_hand(['index']), 'Right', 0.9)
    x, y, w, h = hand.box
    assert 0 <= x < x + w <= 1 and 0 <= y < y + h <= 1
    frame = np.zeros((240, 320, 3), np.uint8)
    draw_hands(frame, [hand.to_dict()])
    draw_motion_boxes(frame, [{'x': 0.1, 'y': 0.1, 'w': 0.2, 'h': 0.2}])
    assert frame.any()
    heat = np.zeros((60, 80), np.float32)
    heat[10:20, 10:20] = 1.0
    out = blend_heatmap(frame, heat)
    assert out.shape == frame.shape
