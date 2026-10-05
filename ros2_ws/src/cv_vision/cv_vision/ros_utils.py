"""Small helpers shared by the ROS nodes."""
import cv2
import numpy as np
from rclpy.qos import HistoryPolicy, QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import CompressedImage

# Latest-frame-only: if a node falls behind, old frames are dropped instead of queueing up latency.
FRAME_QOS = QoSProfile(reliability=ReliabilityPolicy.BEST_EFFORT,
                       history=HistoryPolicy.KEEP_LAST, depth=1)


def decode_image(msg):
    buf = np.frombuffer(bytes(msg.data), dtype=np.uint8)
    return cv2.imdecode(buf, cv2.IMREAD_COLOR)


def encode_image(img, header, quality=70):
    ok, buf = cv2.imencode('.jpg', img, [int(cv2.IMWRITE_JPEG_QUALITY), int(quality)])
    if not ok:
        return None
    msg = CompressedImage()
    msg.header = header
    msg.format = 'jpeg'
    msg.data = buf.tobytes()
    return msg


def stamp_seconds(header):
    return header.stamp.sec + header.stamp.nanosec * 1e-9
