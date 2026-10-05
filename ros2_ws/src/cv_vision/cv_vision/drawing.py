"""Overlay rendering: motion boxes, motion heatmap, hand skeletons, HUD."""
import cv2

from .hands import HAND_CONNECTIONS
from .motion import colorize_heat

MOTION_COLOR = (0, 200, 255)      # amber (BGR)
HAND_COLORS = {'Left': (255, 160, 60), 'Right': (120, 255, 120)}
JOINT_COLOR = (255, 255, 255)


def blend_heatmap(frame, heat, alpha=0.5):
    """heat: float 0..1 map at any resolution (already gain-adjusted)."""
    h, w = frame.shape[:2]
    heat = cv2.resize(heat, (w, h), interpolation=cv2.INTER_LINEAR)
    color = colorize_heat(heat, gain=1.0)
    mask = heat > 0.08
    out = frame.copy()
    out[mask] = cv2.addWeighted(frame, 1 - alpha, color, alpha, 0)[mask]
    return out


def draw_motion_boxes(frame, boxes):
    h, w = frame.shape[:2]
    t = max(1, w // 320)
    for b in boxes:
        p0 = (int(b['x'] * w), int(b['y'] * h))
        p1 = (int((b['x'] + b['w']) * w), int((b['y'] + b['h']) * h))
        cv2.rectangle(frame, p0, p1, MOTION_COLOR, 2 * t)
        cv2.putText(frame, 'motion', (p0[0] + 3, max(12, p0[1] - 5)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45 * t, MOTION_COLOR, t, cv2.LINE_AA)


def draw_hands(frame, hands, show_box=True):
    h, w = frame.shape[:2]
    t = max(1, w // 320)
    for hand in hands:
        color = HAND_COLORS.get(hand['handedness'], (255, 0, 255))
        pts = [(int(p[0] * w), int(p[1] * h)) for p in hand['landmarks']]
        for a, b in HAND_CONNECTIONS:
            cv2.line(frame, pts[a], pts[b], color, 2 * t, cv2.LINE_AA)
        for i, p in enumerate(pts):
            cv2.circle(frame, p, (4 if i in (4, 8, 12, 16, 20) else 3) * t, JOINT_COLOR, -1, cv2.LINE_AA)
            cv2.circle(frame, p, (4 if i in (4, 8, 12, 16, 20) else 3) * t, color, t, cv2.LINE_AA)
        bx, by, bw, bh = hand['box']
        p0 = (int(bx * w) - 8, int(by * h) - 8)
        if show_box:
            cv2.rectangle(frame, p0, (int((bx + bw) * w) + 8, int((by + bh) * h) + 8), color, t)
        label = f"{hand['handedness']} {hand['gesture'].replace('_', ' ')}"
        cv2.putText(frame, label, (max(0, p0[0]), max(14, p0[1] - 6)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5 * t, color, t + 1, cv2.LINE_AA)


def draw_hud(frame, lines):
    t = max(1, frame.shape[1] // 320)
    y = 18 * t
    for line in lines:
        cv2.putText(frame, line, (8, y), cv2.FONT_HERSHEY_SIMPLEX, 0.45 * t, (0, 0, 0), 3 * t, cv2.LINE_AA)
        cv2.putText(frame, line, (8, y), cv2.FONT_HERSHEY_SIMPLEX, 0.45 * t, (255, 255, 255), t, cv2.LINE_AA)
        y += 18 * t
