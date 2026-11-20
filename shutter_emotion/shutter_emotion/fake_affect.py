#!/usr/bin/env python3
"""
Fake perception: publishes AffectScore on /affect/visual and /affect/audio, so that the
behavior controller can be tested before the real perception nodes are ready.

Parameters (can be changed while running with `ros2 param set /fake_affect <name> <value>`):
  mode       cycle: step through all 9 (valence, arousal) states, holding each for hold_sec
             fixed: hold the state given by valence and arousal
  valence    -1, 0 or 1 (fixed mode)
  arousal    -1, 0 or 1 (fixed mode)
  hold_sec   seconds per state (cycle mode)
"""

import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node

from affect_interfaces.msg import AffectScore

CYCLE = [(0, 0), (0, -1), (-1, -1), (-1, 0), (-1, 1), (0, 1), (1, -1), (1, 0), (1, 1)]
MAGNITUDE = 0.8     # published value = MAGNITUDE * state
RATE_HZ = 10.0      # publish rate


class FakeAffectNode(Node):

    def __init__(self):
        super().__init__('fake_affect')

        self.declare_parameter('mode', 'cycle')
        self.declare_parameter('valence', 0)
        self.declare_parameter('arousal', 0)
        self.declare_parameter('hold_sec', 5.0)

        self.start_time = self.now()
        self.last_state = None

        self.visual_pub = self.create_publisher(AffectScore, '/affect/visual', 10)
        self.audio_pub = self.create_publisher(AffectScore, '/affect/audio', 10)
        self.create_timer(1.0 / RATE_HZ, self.publish_affect)

    def now(self):
        """
        :return: current ROS time in seconds
        """
        return self.get_clock().now().nanoseconds / 1e9

    def current_state(self):
        """
        :return: the (valence, arousal) state to publish
        """
        if self.get_parameter('mode').value == 'fixed':
            return self.get_parameter('valence').value, self.get_parameter('arousal').value
        i = int((self.now() - self.start_time) / self.get_parameter('hold_sec').value)
        return CYCLE[i % len(CYCLE)]

    def publish_affect(self):
        """
        Publish the current state on /affect/visual and /affect/audio
        """
        valence, arousal = self.current_state()
        msg = AffectScore()
        msg.detected = True
        msg.valence = MAGNITUDE * valence
        msg.arousal = MAGNITUDE * arousal
        self.visual_pub.publish(msg)
        self.audio_pub.publish(msg)

        if (valence, arousal) != self.last_state:
            self.last_state = (valence, arousal)
            self.get_logger().info('Fake state -> (valence={:+d}, arousal={:+d})'.format(valence, arousal))


def main(args=None):
    rclpy.init(args=args)
    node = FakeAffectNode()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
