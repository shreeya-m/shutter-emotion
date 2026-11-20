#!/usr/bin/env python3
import torch
import torch.nn as nn
import torch.nn.functional as F
import torchaudio

import rclpy
from rclpy.node import Node
from rclpy.time import Time
import numpy as np
from threading import Lock

from affect_interfaces.msg import AudioScore

from tf2_ros.buffer import Buffer
from rclpy.executors import MultiThreadedExecutor

import sounddevice as sd


class AudioCNN(nn.Module):
    def __init__(self):
        super().__init__()

        self.conv1 = nn.Conv2d(1, 16, 3, padding=1)
        self.conv2 = nn.Conv2d(16, 32, 3, padding=1)
        self.conv3 = nn.Conv2d(32, 64, 3, padding=1)

        self.batch_norm1 = nn.BatchNorm2d(16)
        self.batch_norm2 = nn.BatchNorm2d(32)
        self.batch_norm3 = nn.BatchNorm2d(64)

        self.pool = nn.MaxPool2d(2, 2)
        self.adaptive_pool = nn.AdaptiveAvgPool2d((4, 3))

        self.classifier = nn.Sequential(
            nn.Linear(64 * 4 * 3, 128),
            nn.ReLU(),
            nn.Dropout(0.3),
            nn.Linear(128, 64),
            nn.ReLU(),
            nn.Linear(64, 4)
        )

        self.regressor = nn.Sequential(
            nn.Linear(64 * 4 * 3, 128),
            nn.ReLU(),
            nn.Dropout(0.3),
            nn.Linear(128, 64),
            nn.ReLU()
        )

        self.valence_head = nn.Linear(64, 1)
        self.arousal_head = nn.Linear(64, 1)

    def forward(self, x):
        x = self.pool(F.relu(self.batch_norm1(self.conv1(x))))
        x = self.pool(F.relu(self.batch_norm2(self.conv2(x))))
        x = self.pool(F.relu(self.batch_norm3(self.conv3(x))))
        
        x = self.adaptive_pool(x)
        x = torch.flatten(x, 1)

        emotion = self.classifier(x)

        regression_features = self.regressor(x)
        valence = self.valence_head(regression_features)
        arousal = self.arousal_head(regression_features)

        return emotion, valence, arousal


class AudioNode(Node):

    def __init__(self):
        super().__init__('audio_node')

        self.audio_pub = self.create_publisher(AudioScore, "/emotion_audio", 10)
        
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.model = AudioCNN().to(self.device)
        self.model.load_state_dict(torch.load("**/model/audio_cnn.pth", map_location=self.device))
        self.model.eval()  

        self.sample_rate = 16000
        self.buffer_seconds = 5
        self.buffer_size = self.sample_rate * self.buffer_seconds
        self.audio_buffer = np.zeros(self.buffer_size, dtype=np.float32)
        self.buffer_lock = Lock()

        self.mel_transform = torchaudio.transforms.MelSpectrogram(
            sample_rate=self.sample_rate,
            n_mels=128,
            n_fft=1024,
            hop_length=256
        )
        self.mel_spectrogram = None
        
        self.valence = 0
        self.arousal = 0
        
        self.stream = sd.InputStream(
            samplerate=self.sample_rate,
            channels=1,
            callback=self.audio_callback
        )
        self.stream.start()
        
        self.timer = self.create_timer(0.5, self.update_emotion)
        
        
    def audio_callback(self, indata, frames, time, status):
        if status:
            self.get_logger().warn(str(status))
        new_audio = indata[:, 0]
        with self.buffer_lock:
            size = min(len(new_audio), self.buffer_size)
            self.audio_buffer = np.roll(self.audio_buffer, -size)
            self.audio_buffer[-size:] = new_audio[-size:]
            
    def update_emotion(self):
        self.update_spectrogram()
        self.predict_emotion()
        self.publish_emotion()

    def update_spectrogram(self):
        with self.buffer_lock:
            with torch.no_grad():
                self.mel_spectrogram = self.mel_transform(torch.tensor(self.audio_buffer).unsqueeze(0))
            
    def predict_emotion(self):
        if self.mel_spectrogram is None:
            return None, None, None

        with torch.no_grad():
            self.mel_spectrogram = self.mel_spectrogram.unsqueeze(0).to(self.device)
            emotion, valence, arousal = self.model(self.mel_spectrogram)
            self.valence = valence.item()
            self.arousal = arousal.item()
            return emotion, valence, arousal
        
    def publish_emotion(self):
            msg = AudioScore()
            msg.valence = self.valence
            msg.arousal = self.arousal
            self.audio_pub.publish(msg)
        


def main():
    rclpy.init()
    node = AudioNode()
    executor = MultiThreadedExecutor()
    executor.add_node(node)
    try:
        executor.spin()
    except KeyboardInterrupt:
        pass
    finally:
        executor.shutdown()
        node.destroy_node()
    rclpy.shutdown()

if __name__ == '__main__':
    main()