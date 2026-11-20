#!/usr/bin/env python3
from tkinter import Image

import rclpy
from rclpy.node import Node
from rclpy.time import Time
import numpy as np
import time
from std_msgs.msg import Float32

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

        x_value = self.get_parameter('x_value').get_parameter_value().double_value
        radius = self.get_parameter('radius').get_parameter_value().double_value
        publish_rate = self.get_parameter('publish_rate').get_parameter_value().integer_value
        arm_id = self.get_parameter('arm_id').get_parameter_value().string_value

        # Create the simulated object
        self.object = SimulatedObject(arm_id=arm_id)
        
        self.object.x = x_value
        self.object.radius = radius
        self.object.frame = arm_id + "_base_footprint"
        self.timestamp_buffer = None
        
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
