import pandas as pd
import os
import re
import numpy as np
import warnings
import pathlib
from enum import Enum

class Emotion(Enum):
    HAPPY = 1
    ANGRY = 2
    SAD = 3
    FEAR = 4
    SURPRISE = 5
    NEUTRAL = 6
    FRUSTRATION = 7
    EXCITEMENT = 8

EMOTION_ABBREV_MAP = {
    "hap": "HAPPY",
    "ang": "ANGRY",
    "sad": "SAD",
    "fea": "FEAR",
    "sur": "SURPRISE",
    "neu": "NEUTRAL",
    "fru": "FRUSTRATION",
    "exc": "EXCITEMENT"
}


def make_csv(directory_path: str, output_csv: str):
    print(f"Creating CSV from directory: {directory_path}")
    if not os.path.exists(directory_path):
        warnings.warn(f"Directory not found: {directory_path}")
        return
    
    root = pathlib.Path(directory_path)
    prefix = "Session"
    
    data_files = []
    for subfolder in root.iterdir():
        if subfolder.is_dir() and subfolder.name.startswith(prefix):
            session = subfolder.name.split(prefix, 1)[1]
            
            types = ["dialog", "sentences"]
            for t in types:
                for wave_file in subfolder.glob(f"{t}/wav/*.wav"):
                    utterance_id = wave_file.stem
                    emo_eval_file = subfolder / f"{t}/EmoEvaluation/{utterance_id}.txt"
                                        
                    data_files.append([str(session), str(utterance_id), str(wave_file), str(emo_eval_file)])
                    
    data = []
    columns = ["session", "utterance_id", "emotion", "valence", "arousal", "dominance", "start_time", "end_time", "wave_file", "emo_eval_file"]
    for row in data_files:
        session, utterance_id, wave_file, emo_eval_file = row
        
        with open(emo_eval_file, "r") as f:
            lines = f.readlines()
        if not lines:
            continue
        
        for line in lines:
            if line.startswith("[" ):
                # % [START_TIME - END_TIME] TURN_NAME EMOTION [V, A, D]
                match = re.match(r"\[(\d+\.\d+) - (\d+\.\d+)\]\s+(\S+)\s+(\S+)\s+\[([\d\.\-]+), ([\d\.\-]+), ([\d\.\-]+)\]", line)
                if match:
                    start_time, end_time, turn_name, emotion, valence, arousal, dominance = match.groups()
                    
                    if emotion == "xxx":
                        print(f"Skipping xxx in for emo file {emo_eval_file}, turn: {turn_name}")
                        continue
                    emotion_name = EMOTION_ABBREV_MAP.get(emotion)
                    if emotion_name is None:
                        print(f"Unknown emotion abbreviation: {emotion} in file: {emo_eval_file}")
                        continue
                    emotion = Emotion[emotion_name].value
                    
                    # normalize v, a, d from 1 - 5 range to 0 - 1 range
                    valence = (float(valence) - 1) / 4
                    arousal = (float(arousal) - 1) / 4
                    dominance = (float(dominance) - 1) / 4
                    
                    data.append([session, utterance_id, emotion, valence, arousal, dominance, start_time, end_time, wave_file, emo_eval_file])
            
    df = pd.DataFrame(data, columns=columns)
    df.to_csv(output_csv, index=False)
                
    
if __name__ == "__main__":
    make_csv("../data/IEMOCAP_full_release", "IEMOCAP_dataset.csv")
    print("Done! Yay!")
