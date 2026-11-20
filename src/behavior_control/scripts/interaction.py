#!/usr/bin/env python3

""" Given affect scores from visual and audio nodes, compute an affect (that is predicted to 
be perceived as "emotionally attuned") and produce a response. """

"""
subscribe to affect scores from /visual and /audio nodes
VisualScoreMsg {valence: float, arousal: float, category: int}
AudioScoreMsg {audio_detected: bool, valence: float, arousal: float, category: int}
"""

"""
publish to /behavior_control/affect_response
"""