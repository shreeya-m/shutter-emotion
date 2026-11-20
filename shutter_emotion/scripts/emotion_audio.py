#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from rclpy.time import Time
import numpy as np

from affect_interfaces.msg import AudioScore

import tf2_geometry_msgs
from tf2_ros import TransformException
from tf2_ros.buffer import Buffer
from tf2_ros.transform_listener import TransformListener
from tf2_ros import TransformBroadcaster

from rclpy.executors import MultiThreadedExecutor

class EmotionAudio(Node):

    def __init__(self):
        super().__init__('emotion_audio')

        self.audio_pub = self.create_publisher(AudioScore, "/emotion_audio", 10)
        
        # subscribe to microphone
        # self.create_subscription(Target, 'target', self.target_callback, 5)

        self.tf_buffer = Buffer()
        self.tf_listener = TransformListener(self.tf_buffer, self)

        self.audio_buffer = Buffer()


    # def listener_callback(self, msg):
        
        




def main():
    rclpy.init()
    node = EmotionAudio()
    executor = MultiThreadedExecutor()
    executor.add_node(node)
    executor.spin()
    node.destroy_node()
    rclpy.shutdown()

if __name__ == '__main__':
    main()