# shutter_emotion: milestone (affect mirroring in RViz)

Shutter mirrors a human's affect with 9 pre scripted behaviors. For now the human's
affect comes from `fake_affect`.

```
fake_affect ─► /affect/visual, /affect/audio ─► behavior_controller
                                                       │
                                                       ▼
                          /joint_group_controller/commands (std_msgs/Float64MultiArray, joint_1..4)
                                                       │
         mock ros2_control ─► joint_state_broadcaster ─► /joint_states ─► robot_state_publisher ─► /tf ─► RViz
```

How `behavior_controller` turns input into motion:

- **Fusion:** if both channels report `detected=true`, the audio and visual scores are averaged with weights 0.75 and 0.25. If only one does, that channel is used. If neither does, the state is (0,0).
- **Discretizing:** each of valence and arousal becomes -1, 0 or 1. Values with |x| < 0.33 count as 0.
- **Behavior:** the robot plays the behavior for that state (valence sets the posture, arousal sets the motion):

| | arousal -1 (still, slow breathing) | arousal 0 (gentle sway) | arousal +1 (energetic bobbing) |
|---|---|---|---|
| **valence +1** (upright, head up) | (1,-1) | (1,0) | **(1,1) looping dance** |
| **valence 0** (neutral) | (0,-1) | (0,0) | (0,1) |
| **valence -1** (slumped, head down) | (-1,-1) | (-1,0) | (-1,1) |

Each joint moves at most 90% of its URDF velocity limit, so transitions have no jumps.
Control starts once the `joint_group_controller` is active, from the measured `/joint_states`.
The settings and the 9 behaviors are constants at the top of `shutter_emotion/behavior_controller.py`.

## Build

```bash
cd ~/ros2_ws
source /opt/ros/jazzy/setup.bash
colcon build --packages-select affect_interfaces shutter_emotion
source install/setup.bash
```

## Launch

```bash
ros2 launch shutter_emotion milestone.launch.py
```

Don't run this alongside another Shutter bringup (such as the MuJoCo sim) on the same
`ROS_DOMAIN_ID`. Both start a `/controller_manager`, so stop the other one or
`export ROS_DOMAIN_ID=<n>` first.

This starts Shutter's mock bringup (`shutter_control.launch.py hardware:=mock`),
RViz, `fake_affect` and `behavior_controller`. `fake_affect` cycles through all 9
states, holding each for 5 s, in this order:
(0,0) (0,-1) (-1,-1) (-1,0) (-1,1) (0,1) (1,-1) (1,0) (1,1).

Launch arguments:
- `rviz:=false` runs without RViz.
- `fake_affect:=false` is for when the real perception nodes are publishing.

## Change the fake state (while running)

```bash
ros2 param set /fake_affect mode fixed        # hold one state...
ros2 param set /fake_affect valence 1         # ...choose it (-1, 0, 1)
ros2 param set /fake_affect arousal 1
ros2 param set /fake_affect hold_sec 3.0      # cycle speed
ros2 param set /fake_affect mode cycle        # back to cycling
```

## Record a rosbag for the report

Source the workspace first, so the bag can find `affect_interfaces/msg/AffectScore`:

```bash
source ~/ros2_ws/install/setup.bash
ros2 bag record -o milestone_bag \
  /affect/visual /affect/audio /joint_group_controller/commands /joint_states
```
