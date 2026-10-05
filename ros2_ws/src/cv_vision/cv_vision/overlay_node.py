"""Overlay node: draws the latest motion/hand results onto each frame for the apps to display.

Sub:  <input_topic>                     sensor_msgs/CompressedImage
      /cv/motion/detections             vision_msgs/Detection2DArray
      /cv/motion/heatmap/compressed     sensor_msgs/CompressedImage
      /cv/hands/landmarks               std_msgs/String (JSON)
      /cv/overlay_config                std_msgs/String JSON {"boxes": bool, "skeleton": bool, "heatmap": bool}
Pub:  /cv/annotated/compressed          sensor_msgs/CompressedImage
      /cv/stats                         std_msgs/String JSON {fps, motion_level, motion_regions, hands, overlay}
"""
import json
import time

import cv2
import numpy as np
import rclpy
from rcl_interfaces.msg import SetParametersResult
from rclpy.node import Node
from sensor_msgs.msg import CompressedImage
from std_msgs.msg import Float32, String
from vision_msgs.msg import Detection2DArray

from .drawing import blend_heatmap, draw_hands, draw_hud, draw_motion_boxes
from .ros_utils import FRAME_QOS, decode_image, encode_image

TOGGLES = ('boxes', 'skeleton', 'heatmap')


class OverlayNode(Node):
    def __init__(self):
        super().__init__('overlay_node')
        self.declare_parameter('input_topic', '/cv/image/compressed')
        self.declare_parameter('jpeg_quality', 70)
        self.declare_parameter('max_width', 960)
        self.declare_parameter('stale_after', 1.0)
        self.declare_parameter('show_hud', True)
        for t in TOGGLES:
            self.declare_parameter(f'show_{t}', True)
        self.add_on_set_parameters_callback(self._on_params)
        p = lambda n: self.get_parameter(n).value  # noqa: E731

        self.show = {t: bool(p(f'show_{t}')) for t in TOGGLES}
        self.motion = (0.0, [])   # (received_at, detections); each result is (monotonic time, data)
        self.heat = (0.0, None)
        self.hands = (0.0, [])
        self.level = 0.0
        self.frame_times = []

        self.pub_img = self.create_publisher(CompressedImage, '/cv/annotated/compressed', FRAME_QOS)
        self.pub_stats = self.create_publisher(String, '/cv/stats', 10)
        self.create_subscription(CompressedImage, p('input_topic'), self.on_image, FRAME_QOS)
        self.create_subscription(Detection2DArray, '/cv/motion/detections', self.on_motion, 10)
        self.create_subscription(CompressedImage, '/cv/motion/heatmap/compressed', self.on_heat, FRAME_QOS)
        self.create_subscription(Float32, '/cv/motion/level', self.on_level, 10)
        self.create_subscription(String, '/cv/hands/landmarks', self.on_hands, 10)
        self.create_subscription(String, '/cv/overlay_config', self.on_config, 10)

    # --- inputs -----------------------------------------------------------
    def _on_params(self, params):
        for prm in params:
            name = prm.name.removeprefix('show_')
            if name in TOGGLES:
                self.show[name] = bool(prm.value)
        return SetParametersResult(successful=True)

    def on_config(self, msg):
        try:
            cfg = json.loads(msg.data)
        except ValueError:
            self.get_logger().warning(f'Ignoring bad overlay config: {msg.data!r}')
            return
        for t in TOGGLES:
            if t in cfg:
                self.show[t] = bool(cfg[t])

    def on_motion(self, msg):
        self.motion = (time.monotonic(), msg.detections)

    def on_heat(self, msg):
        img = decode_image(msg)
        if img is not None:
            self.heat = (time.monotonic(), img[:, :, 0].astype(np.float32) / 255.0)

    def on_level(self, msg):
        self.level = msg.data

    def on_hands(self, msg):
        try:
            self.hands = (time.monotonic(), json.loads(msg.data).get('hands', []))
        except ValueError:
            pass

    # --- output -----------------------------------------------------------
    def _fresh(self, received_at):
        return time.monotonic() - received_at < self.get_parameter('stale_after').value

    def on_image(self, msg):
        frame = decode_image(msg)
        if frame is None:
            return
        now = time.monotonic()
        self.frame_times = [t for t in self.frame_times if now - t < 2.0] + [now]
        fps = (len(self.frame_times) - 1) / max(1e-3, self.frame_times[-1] - self.frame_times[0])

        h, w = frame.shape[:2]
        max_w = self.get_parameter('max_width').value
        if w > max_w:
            frame = cv2.resize(frame, (max_w, int(h * max_w / w)), interpolation=cv2.INTER_AREA)
        fh, fw = frame.shape[:2]
        # Detections are in source-pixel coords; normalise with the source size (w, h).

        motion_boxes = []
        if self._fresh(self.motion[0]):
            for d in self.motion[1]:
                bw, bh = d.bbox.size_x / w, d.bbox.size_y / h
                motion_boxes.append({'x': d.bbox.center.position.x / w - bw / 2,
                                     'y': d.bbox.center.position.y / h - bh / 2, 'w': bw, 'h': bh})
        hands = self.hands[1] if self._fresh(self.hands[0]) else []

        if self.show['heatmap'] and self.heat[1] is not None and self._fresh(self.heat[0]):
            frame = blend_heatmap(frame, self.heat[1])
        if self.show['boxes']:
            draw_motion_boxes(frame, motion_boxes)
        if self.show['skeleton']:
            draw_hands(frame, hands, show_box=self.show['boxes'])
        if self.get_parameter('show_hud').value:
            draw_hud(frame, [f'{fps:4.1f} fps  motion {self.level * 100:4.1f}%  hands {len(hands)}'])

        out = encode_image(frame, msg.header, self.get_parameter('jpeg_quality').value)
        if out:
            self.pub_img.publish(out)
        self.pub_stats.publish(String(data=json.dumps({
            'fps': round(fps, 1),
            'width': fw,
            'height': fh,
            'motion_level': round(self.level, 4),
            'motion_regions': len(motion_boxes),
            'hands': [{'handedness': hd['handedness'], 'gesture': hd['gesture'], 'fingers': len(hd['fingers'])}
                      for hd in hands],
            'overlay': self.show,
            'source': msg.header.frame_id,
        }, separators=(',', ':'))))


def main():
    rclpy.init()
    node = OverlayNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
