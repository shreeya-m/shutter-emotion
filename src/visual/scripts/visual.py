#!/usr/bin/env python3
from tkinter import Image

import rclpy
from rclpy.node import Node
from rclpy.time import Time
from rclpy.qos import qos_profile_sensor_data
from ament_index_python.packages import get_package_share_directory
from cv_bridge import CvBridge
from sensor_msgs.msg import Image
from torchvision import models
import numpy as np
import time
from std_msgs.msg import Float32

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
            nn.Tanh()
        )

    def forward(self, x):
        return self.va_head(self.backbone(x))

class VisualNode(Node):
    """
    ROS 2 node to generate a simulated moving target
    """
    
    def __init__(self):
        super().__init__('visual')
        # Get ROS parameters
        # Robot id. All of Shutter's links and frames are named ${arm_id}_<name>,
        # so the target has to be published in ${arm_id}_base_footprint for RViz
        # and tf2 to be able to place it relative to the robot.

        default_ckpt = os.path.join(get_package_share_directory("shutter_emotion"),"models","resnet50_omg_visual_va_polarity_balanced.pth",)
        self.declare_parameter("camera_topic", "/camera/camera/color/image_raw")
        self.declare_parameter("output_topic", "/visual")
        self.declare_parameter("window_sec", 2.0)
        self.declare_parameter("publish_hz", 10.0)
        self.declare_parameter("model_path", default_ckpt)
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.bridge = CvBridge()
        self.buffer = deque()

        self.model = ResNet50OMGVisualVA(dropout=0.45).to(self.device)
        self.model.load_state_dict(torch.load(ckpt_path, map_location=self.device), strict=True)
        self.model.eval()
        cam_topic = self.get_parameter("camera_topic").value
        out_topic = self.get_parameter("output_topic").value
        self.window_sec = float(self.get_parameter("window_sec").value)
        publish_hz = float(self.get_parameter("publish_hz").value)
        ckpt_path = self.get_parameter("model_path").value

        
        # Define publishers
        self.pub_valence = self.create_publisher(Float32, '/valence', 5)
        self.pub_arousal = self.create_publisher(Float32, '/arousal', 5)
        self.last_emotion_time = time.time()
        # Create timer for publishing
        self.create_subscription(Image, '/camera/color/image_raw', self.image_callback, 5)
        
        self.timer = self.create_timer(1.0 / publish_rate, self.publish_target)
        
        self.get_logger().info(
            f'Generate target node initialized (publishing in frame {self.object.frame})')

    def image_callback(self, msg):
        #need to convert from ros image to cv2 image
        # Convert the ROS Image message to a CV2 image

        valence, arousal = self.process_image(msg)
        self.pub_valence.publish(Float32(data=valence))
        self.pub_arousal.publish(Float32(data=arousal))
        
        self.last_emotion_time = time.time()




def main(args=None):
    rclpy.init(args=args)
    node = None
    
    try:
        node = VisualNode()
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        if node is not None:
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
