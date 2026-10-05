"""Motion detection + decaying motion heatmap. Pure OpenCV/NumPy, no ROS."""
from dataclasses import dataclass, field

import cv2
import numpy as np


@dataclass
class MotionBox:
    # Normalised (0..1) top-left corner and size, relative to the input frame.
    x: float
    y: float
    w: float
    h: float
    area: float  # fraction of the frame covered by the moving blob


@dataclass
class MotionResult:
    boxes: list = field(default_factory=list)
    level: float = 0.0  # fraction of pixels moving in this frame (0..1)
    heat: np.ndarray = None  # float32 (H, W) in 0..1 at processing resolution


class MotionDetector:
    def __init__(self, process_width=320, history=300, var_threshold=25.0,
                 min_area=0.002, heat_decay=0.93, max_boxes=12):
        self.process_width = process_width
        self.history = history
        self.var_threshold = var_threshold
        self.min_area = min_area
        self.heat_decay = heat_decay
        self.max_boxes = max_boxes
        self._kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        self._shape = None
        self._reset((0, 0))

    def _reset(self, shape):
        self._shape = shape
        self._bg = cv2.createBackgroundSubtractorMOG2(
            history=self.history, varThreshold=self.var_threshold, detectShadows=True)
        self._heat = np.zeros(shape, np.float32) if shape[0] else None

    def update(self, frame_bgr):
        h, w = frame_bgr.shape[:2]
        scale = min(1.0, self.process_width / float(w))
        small = cv2.resize(frame_bgr, (max(1, int(w * scale)), max(1, int(h * scale))),
                           interpolation=cv2.INTER_AREA) if scale < 1.0 else frame_bgr
        small = cv2.GaussianBlur(small, (5, 5), 0)
        if small.shape[:2] != self._shape:
            # New source / resolution / orientation: start the background model over.
            self._reset(small.shape[:2])

        fg = self._bg.apply(small)
        # MOG2 marks shadows as 127; keep only real foreground (255).
        _, mask = cv2.threshold(fg, 200, 255, cv2.THRESH_BINARY)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, self._kernel)
        mask = cv2.dilate(mask, self._kernel, iterations=2)

        moving = mask.astype(np.float32) / 255.0
        self._heat *= self.heat_decay
        self._heat += moving * (1.0 - self.heat_decay)
        np.clip(self._heat, 0.0, 1.0, out=self._heat)

        sh, sw = mask.shape
        total = float(sh * sw)
        boxes = []
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for c in contours:
            area = cv2.contourArea(c) / total
            if area < self.min_area:
                continue
            bx, by, bw, bh = cv2.boundingRect(c)
            boxes.append(MotionBox(bx / sw, by / sh, bw / sw, bh / sh, area))
        boxes.sort(key=lambda b: b.area, reverse=True)

        return MotionResult(boxes=boxes[:self.max_boxes],
                            level=float(np.count_nonzero(mask)) / total,
                            heat=self._heat)


def colorize_heat(heat, gain=4.0):
    """Turn a 0..1 heat map into a BGR JET image; gain makes faint trails visible."""
    scaled = np.clip(heat * gain, 0.0, 1.0)
    return cv2.applyColorMap((scaled * 255).astype(np.uint8), cv2.COLORMAP_JET)
