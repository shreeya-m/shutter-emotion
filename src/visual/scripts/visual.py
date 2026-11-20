#!/usr/bin/env python3
import os
from collections import deque
import cv2
import numpy as np
import torch
import torch.nn as nn
from torchvision import models
import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from cv_bridge import CvBridge
from sensor_msgs.msg import Image
from emotion_interfaces.msg import VisualScore
from facenet_pytorch import MTCNN


class ResNet50OMGVisualVA(nn.Module):
    def __init__(self, dropout=0.45):
        super().__init__()
        self.backbone = models.resnet50(weights=None)
        in_features = self.backbone.fc.in_features
        self.backbone.fc = nn.Identity()
        self.va_head = nn.Sequential(
            nn.Dropout(p=dropout),
            nn.Linear(in_features, 256),
            nn.GELU(),
            nn.Dropout(p=dropout * 0.7),
            nn.Linear(256, 2),
            nn.Tanh(),
        )

    def forward(self, x):
        return self.va_head(self.backbone(x))


def get_checkpoint_path() -> str:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.abspath(os.path.join(script_dir, "..", "model", "resnet50_omg_visual_va_polarity_balanced.pth"))


class VisualNode(Node):
    def __init__(self):
        super().__init__("visual")
        default_ckpt = get_checkpoint_path()
        self.declare_parameter("camera_topic", "/camera/camera/color/image_raw")
        self.declare_parameter("output_topic", "/affect/visual")
        self.declare_parameter("debug_topic", "/face/debug_image")
        self.declare_parameter("window_sec", 2.0)
        self.declare_parameter("publish_hz", 10.0)
        self.declare_parameter("model_path", default_ckpt)

        cam_topic = self.get_parameter("camera_topic").value
        out_topic = self.get_parameter("output_topic").value
        debug_topic = self.get_parameter("debug_topic").value
        self.window_sec = float(self.get_parameter("window_sec").value)
        publish_hz = float(self.get_parameter("publish_hz").value)
        ckpt_path = self.get_parameter("model_path").value
        print(f"checkpoint exists {os.path.exists(ckpt_path)} ({ckpt_path})")
        if not os.path.exists(ckpt_path):
            raise FileNotFoundError(f"missing: {ckpt_path}")
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.model = ResNet50OMGVisualVA(dropout=0.45).to(self.device)
        state = torch.load(ckpt_path, map_location=self.device, weights_only=True)
        self.model.load_state_dict(state, strict=True)
        self.model.eval()
        print(f"making sure model loaded on {self.device} head {tuple(state['va_head.4.weight'].shape)}")
        self.detector = MTCNN(keep_all=False, device=self.device)
    #debating keeping MTCNN

        self.bridge = CvBridge()
        self.buffer = deque()
        self.face_present = False
        self.mean = np.array([0.485, 0.456, 0.406], dtype=np.float32)
        self.std = np.array([0.229, 0.224, 0.225], dtype=np.float32)
        self.pub = self.create_publisher(VisualScore, out_topic, 10)
        self.debug_pub = self.create_publisher(Image, debug_topic, 10)
        self.sub = self.create_subscription(Image, cam_topic, self.image_callback, qos_profile_sensor_data)
        self.timer = self.create_timer(1.0 / publish_hz, self.publish_emotion)
        print(f"visual node ready from {cam_topic} to {out_topic}")
        self._got_first_frame = False
        self._pub_count = 0

    def _stamp_to_sec(self, msg: Image) -> float:
        stamp = msg.header.stamp
        if stamp.sec == 0 and stamp.nanosec == 0:
            return self.get_clock().now().nanoseconds * 1e-9
        return float(stamp.sec) + float(stamp.nanosec) * 1e-9

    def _evict_old(self, latest_sec: float):
        cutoff = latest_sec - self.window_sec
        while self.buffer and self.buffer[0][0] < cutoff:
            self.buffer.popleft()

    def find_face_box(self, frame_bgr: np.ndarray):
        h_img, w_img = frame_bgr.shape[:2]
        frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        boxes, probs = self.detector.detect(frame_rgb)
        if boxes is None or len(boxes) == 0:
            return None
        valid = [b for b, p in zip(boxes, probs) if p is not None and p >= 0.85]
        if not valid:
            return None
        areas = [(b[2] - b[0]) * (b[3] - b[1]) for b in valid]
        x1, y1, x2, y2 = valid[int(np.argmax(areas))]
        
        w, h= x2 - x1, y2 - y1 #lots of cropping
        x1 = max(0, int(x1 - 0.12 * w))
        y1 = max(0, int(y1 - 0.15 * h))
        x2 = min(w_img, int(x2 + 0.12 * w))
        y2 = min(h_img, int(y2 + 0.15 * h))
        if x2<= x1 + 20 or y2 <= y1 + 20:
            return None
        return (x1, y1, x2, y2)

    @torch.inference_mode()
    def image_callback(self, msg: Image):
        if not self._got_first_frame:
            print(f"making sure first frame received: {msg.width}x{msg.height}")
            self._got_first_frame = True
        frame_bgr = self.bridge.imgmsg_to_cv2(msg, desired_encoding="bgr8")
        box = self.find_face_box(frame_bgr)

        if box is None :# no face found, reset buffer
            self.face_present = False
            self.buffer.clear()
            return
        self.face_present = True
        x1, y1, x2, y2 = box
        crop_bgr = cv2.resize(frame_bgr[y1:y2, x1:x2], (224, 224), interpolation=cv2.INTER_LINEAR)
        rgb = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
        norm =(rgb - self.mean) / self.std
        tensor = torch.from_numpy(norm.transpose(2, 0, 1)).unsqueeze(0).to(self.device)
        va = self.model(tensor).squeeze(0).cpu().tolist()
        v = float(np.clip(va[0], -1.0, 1.0))
        a = float(np.clip(va[1], -1.0, 1.0))
        t_sec = self._stamp_to_sec(msg)
        self.buffer.append((t_sec, v, a))
        self._evict_old(t_sec)

    def publish_emotion(self):
        out = VisualScore()
        if not self.face_present or not self.buffer:
            out.face_detected = False
            out.valence = 0.0
            out.arousal = 0.0
        else:
            latest_t = self.buffer[-1][0]
            self._evict_old(latest_t)
            out.face_detected = True
            out.valence = round(float(np.clip(np.mean([x[1] for x in self.buffer]), -1.0, 1.0)), 4)
            out.arousal = round(float(np.clip(np.mean([x[2] for x in self.buffer]), -1.0, 1.0)), 4)
        self.pub.publish(out)
        self._pub_count += 1
        if self._pub_count == 1 or self._pub_count % 20 == 0:
            print(f"/affect/visual (#{self._pub_count}): face_detected={out.face_detected}, v={out.valence}, a={out.arousal}")

def main(args=None):
    rclpy.init(args=args)
    node = VisualNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()

if __name__ == "__main__":
    main()