"""Hand tracking node (MediaPipe Hand Landmarker).

Sub:  <input_topic>              sensor_msgs/CompressedImage
Pub:  /cv/hands/detections       vision_msgs/Detection2DArray  (class_id = "Left"/"Right", pixel coords)
      /cv/hands/landmarks        std_msgs/String  JSON: {stamp, width, height, hands: [{handedness, score,
                                                   box, fingers, gesture, landmarks[21][x,y,z]}]}
"""
import json

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import CompressedImage
from std_msgs.msg import String
from vision_msgs.msg import Detection2D, Detection2DArray, ObjectHypothesisWithPose

from .hands import DEFAULT_MODEL_PATH, HandTracker
from .ros_utils import FRAME_QOS, decode_image, stamp_seconds


class HandNode(Node):
    def __init__(self):
        super().__init__('hand_node')
        self.declare_parameter('input_topic', '/cv/image/compressed')
        self.declare_parameter('model_path', DEFAULT_MODEL_PATH)
        self.declare_parameter('max_hands', 2)
        self.declare_parameter('min_detection_confidence', 0.5)
        self.declare_parameter('min_tracking_confidence', 0.5)
        p = lambda n: self.get_parameter(n).value  # noqa: E731

        self.get_logger().info('Loading MediaPipe hand landmarker (downloads the model on first run)...')
        self.tracker = HandTracker(model_path=p('model_path'), max_hands=p('max_hands'),
                                   min_detection=p('min_detection_confidence'),
                                   min_tracking=p('min_tracking_confidence'))

        self.pub_det = self.create_publisher(Detection2DArray, '/cv/hands/detections', 10)
        self.pub_json = self.create_publisher(String, '/cv/hands/landmarks', 10)
        self.create_subscription(CompressedImage, p('input_topic'), self.on_image, FRAME_QOS)
        self.get_logger().info(f"Hand tracking listening on {p('input_topic')}")

    def on_image(self, msg):
        frame = decode_image(msg)
        if frame is None:
            return
        h, w = frame.shape[:2]
        hands = self.tracker.process(frame)

        out = Detection2DArray()
        out.header = msg.header
        for i, hand in enumerate(hands):
            bx, by, bw, bh = hand.box
            d = Detection2D()
            d.header = msg.header
            d.id = f'hand_{i}'
            d.bbox.center.position.x = (bx + bw / 2) * w
            d.bbox.center.position.y = (by + bh / 2) * h
            d.bbox.size_x = bw * w
            d.bbox.size_y = bh * h
            hyp = ObjectHypothesisWithPose()
            hyp.hypothesis.class_id = hand.handedness
            hyp.hypothesis.score = float(hand.score)
            d.results.append(hyp)
            out.detections.append(d)
        self.pub_det.publish(out)

        self.pub_json.publish(String(data=json.dumps({
            'stamp': stamp_seconds(msg.header),
            'frame_id': msg.header.frame_id,
            'width': w,
            'height': h,
            'hands': [hand.to_dict() for hand in hands],
        }, separators=(',', ':'))))

    def destroy_node(self):
        self.tracker.close()
        super().destroy_node()


def main():
    rclpy.init()
    node = HandNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
