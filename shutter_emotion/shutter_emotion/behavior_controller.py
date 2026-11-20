#!/usr/bin/env python3
"""
Behavior controller: Shutter responds to the human's affect with one of 9 scripted behaviors.
For the milestone, Shutter mirrors the human's affect.

Subscribes: /affect/visual, /affect/audio, /joint_states
Publishes:  /joint_group_controller/commands
"""

import math

import numpy as np
import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from controller_manager_msgs.srv import ListControllers, SwitchController
from sensor_msgs.msg import JointState
from std_msgs.msg import Float64MultiArray

from affect_interfaces.msg import AffectScore

RATE_HZ = 20.0      # control loop rate
DEADBAND = 0.33     # |x| < DEADBAND -> 0, otherwise sign(x)
W_AUDIO = 0.75      # weight of audio vs visual when both detect someone
W_VISUAL = 0.25

# Shutter's joints, from the URDF (shutter_description/urdf/third_party/widowx-nogripper.v.2.0.urdf.xacro)
#   joint_1: base yaw        (+ turns left)
#   joint_2: shoulder pitch  (+ leans forward)
#   joint_3: elbow pitch     (+ raises the forearm)
#   joint_4: head pitch      (+ looks up)
JOINT_NAMES = ['joint_1', 'joint_2', 'joint_3', 'joint_4']
VELOCITY_LIMITS = np.array([0.785, 1.571, 1.571, 1.571])  # rad/s
MAX_STEP = 0.9 * VELOCITY_LIMITS / RATE_HZ                # max rad change per tick -> no jerks

# ───────── 9 SCRIPTED RESPONSES ─────────
# valence -> base POSTURE, arousal -> MOTION (size and speed of the movement)
#                       joint_1 joint_2 joint_3 joint_4
POSTURE = {-1: np.array([-0.7, -0.7, -1.0, -0.8]),    # slumped, head down (gaze ~63° below level), shyly turn away
            0: np.array([0.0, -1.0, -0.8, -0.2]),    # neutral, level gaze
            1: np.array([0.0, -0.25, 0.8, -0.8])}    # upright, head up (gaze ~14° above level)

#           (amplitude rad, frequency Hz)
MOTION = {-1: (0.08, 0.12),     # nearly still, slow "breathing"
           0: (0.20, 0.25),     # gentle idle sway
           1: (0.35, 0.60)}     # energetic bobbing

# How much each joint moves (amplitude * MOTION_MASK = per-joint amplitude): base sway, elbow bob, head nod
MOTION_MASK = np.array([0.5, 0.0, 0.4, 0.6])

# (1, 1) dance: joint positions to visit, one per beat, looped
DANCE_BEAT_SEC = 1.7
DANCE_KEYFRAMES = np.array([
    #  joint_1 joint_2 joint_3 joint_4
    [0.0, -0.25, 0.8, -0.8],      # stretch up tall
    [-0.7, -0.7, -0.7, 0.6],      # face right, squat
    [0.0, -0.25, 0.8, -0.8],      # stretch up tall
    [0.7, -0.7, -0.7, 0.6],      # face left, squat
])


def response(valence, arousal, t):
    """
    Joint positions for one of the 9 scripted behaviors
    :param valence: -1, 0 or 1 (chooses the posture)
    :param arousal: -1, 0 or 1 (chooses the motion)
    :param t: seconds since this behavior started
    :return: joint positions (rad) for joint_1 to joint_4
    """
    if (valence, arousal) == (1, 1):
        return dance(t)  # special case: happy + excited
    amplitude, frequency = MOTION[arousal]
    return POSTURE[valence] + amplitude * math.sin(2 * math.pi * frequency * t) * MOTION_MASK


def dance(t):
    """
    Short looping dance: moves from one keyframe to the next on every beat
    :param t: seconds since the dance started
    :return: joint positions (rad) for joint_1 to joint_4
    """
    beat = t / DANCE_BEAT_SEC
    i = int(beat) % len(DANCE_KEYFRAMES)
    start = DANCE_KEYFRAMES[i]
    end = DANCE_KEYFRAMES[(i + 1) % len(DANCE_KEYFRAMES)]
    # ease in and out (0 -> 1), so the robot slows down at every keyframe
    progress = 0.5 - 0.5 * math.cos(math.pi * (beat % 1.0))
    return start + (end - start) * progress


def discretize(x):
    """
    :param x: continuous affect value in [-1, 1]
    :return: -1, 0 or 1
    """
    if abs(x) < DEADBAND:
        return 0
    return 1 if x > 0 else -1


class BehaviorControllerNode(Node):
    """
    Turns the human's affect into joint commands for Shutter
    """

    def __init__(self):
        super().__init__('behavior_controller')

        self.visual = None              # latest visual AffectScore
        self.audio = None               # latest audio AffectScore
        self.joint_positions = None     # latest measured joint positions
        self.q = None                   # latest commanded joint positions
        self.state = None               # (valence, arousal) the robot is responding to
        self.behavior_start = None      # time when the current behavior started

        self.cmd_pub = self.create_publisher(Float64MultiArray, '/joint_group_controller/commands', 10)
        self.create_subscription(AffectScore, '/affect/visual', self.visual_callback, 10)
        self.create_subscription(AffectScore, '/affect/audio', self.audio_callback, 10)
        self.create_subscription(JointState, '/joint_states', self.joint_state_callback, 10)

    def now(self):
        """
        :return: current ROS time in seconds
        """
        return self.get_clock().now().nanoseconds / 1e9

    def visual_callback(self, msg):
        self.visual = msg

    def audio_callback(self, msg):
        self.audio = msg

    def joint_state_callback(self, msg):
        positions = dict(zip(msg.name, msg.position))
        if all(name in positions for name in JOINT_NAMES):
            self.joint_positions = np.array([positions[name] for name in JOINT_NAMES])

    def start(self):
        """
        Switch to the joint_group_controller, wait for the arm's position, then start the control loop
        """
        self.activate_joint_group_controller()
        self.joint_positions = None  # wait for a /joint_states message sent after the switch
        while rclpy.ok() and self.joint_positions is None:
            self.get_logger().info('Waiting for /joint_states...', throttle_duration_sec=5.0)
            rclpy.spin_once(self, timeout_sec=0.5)

        # Start from where the arm actually is, so that the first command does not jump
        self.q = self.joint_positions.copy()
        self.create_timer(1.0 / RATE_HZ, self.control_loop)
        self.get_logger().info('Behavior controller started')

    def activate_joint_group_controller(self):
        """
        Switch from the follow_trajectory_controller (active after Shutter's bringup) to the
        joint_group_controller, which accepts a stream of joint positions
        """
        list_client = self.create_client(ListControllers, '/controller_manager/list_controllers')
        switch_client = self.create_client(SwitchController, '/controller_manager/switch_controller')
        list_client.wait_for_service()
        switch_client.wait_for_service()

        while rclpy.ok():
            future = list_client.call_async(ListControllers.Request())
            rclpy.spin_until_future_complete(self, future)
            states = {c.name: c.state for c in future.result().controller}

            if states.get('joint_group_controller') == 'active':
                return

            # Switch once Shutter's bringup has finished spawning both controllers
            if states.get('joint_group_controller') == 'inactive' and \
                    states.get('follow_trajectory_controller') == 'active':
                request = SwitchController.Request()
                request.activate_controllers = ['joint_group_controller']
                request.deactivate_controllers = ['follow_trajectory_controller']
                request.strictness = SwitchController.Request.STRICT
                future = switch_client.call_async(request)
                rclpy.spin_until_future_complete(self, future)
                if future.result().ok:
                    self.get_logger().info('Switched to the joint_group_controller')
                    return

            self.get_logger().info('Waiting for the controllers...', throttle_duration_sec=5.0)
            rclpy.spin_once(self, timeout_sec=0.5)

    def control_loop(self):
        """
        Main loop: affect scores -> state -> behavior -> joint command
        """
        valence, arousal = self.fuse()
        state = (discretize(valence), discretize(arousal))
        if state != self.state:
            self.state = state
            self.behavior_start = self.now()  # start the new behavior from t = 0
            self.get_logger().info('Behavior -> (valence={:+d}, arousal={:+d})'.format(*state))

        # Mirror the human: the robot plays the behavior for the human's own state
        q_target = response(*state, self.now() - self.behavior_start)
        self.q = self.q + np.clip(q_target - self.q, -MAX_STEP, MAX_STEP)
        self.cmd_pub.publish(Float64MultiArray(data=self.q.tolist()))

    def fuse(self):
        """
        Combine visual and audio affect scores
        (neutral if no one detected)
        """
        visual = self.visual if self.visual and self.visual.detected else None
        audio = self.audio if self.audio and self.audio.detected else None
        if visual and audio:
            total = W_AUDIO + W_VISUAL
            return ((W_AUDIO * audio.valence + W_VISUAL * visual.valence) / total,
                    (W_AUDIO * audio.arousal + W_VISUAL * visual.arousal) / total)
        if visual or audio:
            msg = visual or audio
            return msg.valence, msg.arousal
        return 0.0, 0.0


def main(args=None):
    rclpy.init(args=args)
    node = BehaviorControllerNode()
    try:
        node.start()
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
