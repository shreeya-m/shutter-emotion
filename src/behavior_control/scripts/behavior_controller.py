#!/usr/bin/env python3

"""
Given affect scores from visual and audio nodes, compute an affect (that is predicted to 
be perceived as "emotionally attuned") and produce a response.

BUT for the milestone, Shutter will merely mirror the human's affect.

Subscribes: /affect/visual, /affect/audio
Publishes: /joint_group_controller/commands, /human_affect
Policy: mirror human affect (for now)
"""

# -------CONFIG--------
RATE_HZ = 20
