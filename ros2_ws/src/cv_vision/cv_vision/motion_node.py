"""Motion detection node.

Sub:  <input_topic>                      sensor_msgs/CompressedImage
Pub:  /cv/motion/detections              vision_msgs/Detection2DArray  (pixel coords)
      /cv/motion/heatmap/compressed      sensor_msgs/CompressedImage   (grayscale intensity, 255 = hot)
      /cv/motion/level                   std_msgs/Float32              (0..1 fraction moving)
"""
import numpy as np
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import CompressedImage
from std_msgs.msg import Float32
from vision_msgs.msg import Detection2D, Detection2DArray, ObjectHypothesisWithPose

from .motion import MotionDetector
from .ros_utils import FRAME_QOS, decode_image, encode_image

# Heat values are small (a decayed average), so boost them before quantising to 8 bits.
HEAT_GAIN = 4.0


class MotionNode(Node):
    def __init__(self):
        super().__init__('motion_node')
        self.declare_parameter('input_topic', '/cv/image/compressed')
        self.declare_parameter('process_width', 320)
        self.declare_parameter('var_threshold', 25.0)
        self.declare_parameter('min_area', 0.002)
        self.declare_parameter('heat_decay', 0.93)
        self.declare_parameter('heatmap_every_n', 2)
        p = lambda n: self.get_parameter(n).value  # noqa: E731

        self.detector = MotionDetector(process_width=p('process_width'), var_threshold=p('var_threshold'),
                                       min_area=p('min_area'), heat_decay=p('heat_decay'))
        self.heatmap_every_n = max(1, int(p('heatmap_every_n')))
        self.count = 0

        self.pub_det = self.create_publisher(Detection2DArray, '/cv/motion/detections', 10)
        self.pub_heat = self.create_publisher(CompressedImage, '/cv/motion/heatmap/compressed', FRAME_QOS)
        self.pub_level = self.create_publisher(Float32, '/cv/motion/level', 10)
        self.create_subscription(CompressedImage, p('input_topic'), self.on_image, FRAME_QOS)
        self.get_logger().info(f"Motion detection listening on {p('input_topic')}")

    def on_image(self, msg):
        frame = decode_image(msg)
        if frame is None:
            return
        h, w = frame.shape[:2]
        result = self.detector.update(frame)

        out = Detection2DArray()
        out.header = msg.header
        for i, b in enumerate(result.boxes):
            d = Detection2D()
            d.header = msg.header
            d.id = f'motion_{i}'
            d.bbox.center.position.x = (b.x + b.w / 2) * w
            d.bbox.center.position.y = (b.y + b.h / 2) * h
            d.bbox.size_x = b.w * w
            d.bbox.size_y = b.h * h
            hyp = ObjectHypothesisWithPose()
            hyp.hypothesis.class_id = 'motion'
            hyp.hypothesis.score = float(min(1.0, b.area * 20))
            d.results.append(hyp)
            out.detections.append(d)
        self.pub_det.publish(out)
        self.pub_level.publish(Float32(data=result.level))

        self.count += 1
        if self.count % self.heatmap_every_n == 0 and self.pub_heat.get_subscription_count() > 0:
            gray = (np.clip(result.heat * HEAT_GAIN, 0.0, 1.0) * 255).astype(np.uint8)
            heat_msg = encode_image(gray, msg.header, quality=80)
            if heat_msg:
                self.pub_heat.publish(heat_msg)


def main():
    rclpy.init()
    node = MotionNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
