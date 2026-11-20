#!/usr/bin/env python3

"""
Given affect scores from visual and audio nodes, compute an affect (that is predicted to 
be perceived as "emotionally attuned") and produce a response.

BUT for the milestone, Shutter will merely mirror the human's affect.

Subscribes: /affect/visual, /affect/audio
Publishes: /joint_group_controller/commands, /human_affect
Policy: mirror human affect (for now)
"""
# ───────── CONFIG ───────── 
RATE_HZ      = 20      # control loop rate
STALE_SEC    = 1.0     # older messages are ignored
DEADBAND     = 0.33    # |x| < DEADBAND → 0, otherwise sign(x)
DEBOUNCE_SEC = 1.0     # a new state must hold this long before the robot switches
W_AUDIO, W_VISUAL = 0.75, 0.25  # how heavily to weigh audio versus visual input
CMD_TOPIC    = "/joint_group_controller/commands"
JOINT_NAMES  = ['joint_1', 'joint_2', 'joint_3', 'joint_4']  # Shutter's joints, from the URDF
JOINT_LIMITS = "TODO"  # [(lo, hi), ...] from the URDF
MAX_STEP     = "TODO"  # max rad change per tick → smooth transitions, no jerks

# ───────── 9 SCRIPTED RESPONSES ─────────
# valence → base POSTURE, arousal → MOTION (size and speed of the movement)
POSTURE = { -1: [...],   # slumped, head down
             0: [...],   # neutral
             1: [...] }  # upright, head up
MOTION  = { -1: (amp_small, freq_slow),   # nearly still, slow "breathing"
             0: (amp_mid,   freq_mid),    # gentle idle sway
             1: (amp_big,   freq_fast) }  # energetic bobbing

def response(v_R, a_R, t):                # t = seconds since this behavior started
    if (v_R, a_R) == (1, 1):
        return dance(t)                   # special case: happy + excited
    amp, freq = MOTION[a_R]
    return POSTURE[v_R] + amp * sin(2π·freq·t) * MOTION_MASK   # MASK = which joints move

def dance(t):
    # short looping keyframe sequence (head bob + base wiggle), interpolated over t
    ...


# ───────── NODE ─────────
class BehaviorController(Node):
    __init__():
        subscribe /affect/visual → on_visual
        subscribe /affect/audio  → on_audio
        create cmd_pub on CMD_TOPIC, debug_pub on /human_affect
        latest_visual = latest_audio = None    # (msg, receive_time)
        s_current = (0, 0); s_candidate = None; candidate_since = None
        behavior_start = now; q_prev = POSTURE[0]
        create timer at RATE_HZ → tick

    on_visual(msg): latest_visual = (msg, now)
    on_audio(msg):  latest_audio  = (msg, now)

    fresh(entry) -> bool:     # message exists, detected == True, younger than STALE_SEC

    fuse() -> (v, a) or None:
        if fresh(audio) and fresh(visual): weighted average with W_AUDIO / W_VISUAL
        elif fresh(visual):                visual only
        elif fresh(audio):                 audio only
        else:                              None (nobody detected)

    discretize(v, a) -> (int, int):   apply DEADBAND to each axis

    debounce(s) -> s_stable:
        if s == s_current: reset candidate
        elif s != s_candidate: s_candidate = s; candidate_since = now
        elif now - candidate_since >= DEBOUNCE_SEC:
            s_current = s; behavior_start = now      # switch behavior
        return s_current

    policy(s) -> ξ:  return s                        # MIRROR (learned policy goes here later)

    tick():
        raw = fuse()
        s   = discretize(*raw) if raw else (0, 0)
        s   = debounce(s)
        ξ   = policy(s)
        q   = response(*ξ, now - behavior_start)
        q   = step toward q from q_prev by at most MAX_STEP per joint
        q   = clamp(q, JOINT_LIMITS); q_prev = q
        publish q on cmd_pub; publish s on debug_pub

    on_shutdown(): send POSTURE[0] (return to neutral)

main(): rclpy.init → spin(BehaviorController) → shutdown