# trained_models.py
# Updated for CNN classifier (crowd level) + GNN spike predictor (LSTM)

import os
import cv2
import numpy as np
import tensorflow as tf
import torch
import torch.nn as nn
from collections import deque
from datetime import datetime

# ============================================
# CNN CLASSIFIER (4-class: critical, high, medium, low)
# ============================================

class CrowdClassifier:
    """
    CNN model trained on your own dataset (critical, high, medium, low folders).
    Returns crowd level and estimated people count.
    """
    def __init__(self, model_path='models/crowd_classifier.h5'):
        self.model_path = model_path
        self.model = None
        self.class_names = ['critical', 'high', 'medium', 'low']  # order must match training
        self.people_estimate = {
            'low': 60,
            'medium': 200,
            'high': 450,
            'critical': 1200
        }
        self.load_model()

    def load_model(self):
        try:
            if os.path.exists(self.model_path):
                self.model = tf.keras.models.load_model(self.model_path, compile=False)
                print("✅ CNN classifier loaded")
            else:
                print(f"⚠️ CNN classifier not found at {self.model_path}")
                self.model = None
        except Exception as e:
            print(f"❌ Error loading CNN classifier: {e}")
            self.model = None

    def predict(self, image):
        """
        Args:
            image: numpy array (BGR) or path to image file
        Returns:
            level (str), people (int), confidence (float)
        """
        if self.model is None:
            return "medium", 200, 0.5   # fallback

        if isinstance(image, str):
            img = cv2.imread(image)
        else:
            img = image.copy()
        if img is None:
            return "medium", 200, 0.0

        img = cv2.resize(img, (224, 224))
        img = img.astype(np.float32) / 255.0
        img = np.expand_dims(img, axis=0)

        pred = self.model.predict(img, verbose=0)[0]
        idx = np.argmax(pred)
        level = self.class_names[idx]
        people = self.people_estimate.get(level, 100)
        confidence = float(pred[idx])
        return level, people, confidence

    def analyze_frame(self, frame):
        level, people, conf = self.predict(frame)
        return {
            'crowd_level': level,
            'estimated_people': people,
            'confidence': conf,
            'timestamp': datetime.now().isoformat()
        }


# ============================================
# GNN SPIKE PREDICTOR (LSTM for crowd spike)
# ============================================

class CrowdSpikeLSTM(nn.Module):
    def __init__(self, input_size=1, hidden_size=32, num_layers=2):
        super().__init__()
        self.lstm = nn.LSTM(input_size, hidden_size, num_layers, batch_first=True)
        self.fc = nn.Linear(hidden_size, 1)
        self.sigmoid = nn.Sigmoid()

    def forward(self, x):
        out, _ = self.lstm(x)
        last = out[:, -1, :]
        return self.sigmoid(self.fc(last)).squeeze()


class CrowdSpikePredictor:
    """
    GNN (LSTM) model that predicts probability of a crowd spike
    based on the last 10 crowd level values.
    """
    def __init__(self, model_path='models/crowd_spike_gnn.pth', history_len=10):
        self.model_path = model_path
        self.model = None
        self.history_len = history_len
        self.history = deque(maxlen=history_len)   # stores numeric levels
        self.load_model()

    def load_model(self):
        try:
            if os.path.exists(self.model_path):
                self.model = CrowdSpikeLSTM()
                self.model.load_state_dict(torch.load(self.model_path, map_location='cpu'))
                self.model.eval()
                print("✅ GNN spike predictor loaded")
            else:
                print(f"⚠️ GNN spike predictor not found at {self.model_path}")
                self.model = None
        except Exception as e:
            print(f"❌ Error loading GNN spike predictor: {e}")
            self.model = None

    def add_level(self, level_str):
        """Add a new crowd level (string) to the history buffer."""
        level_map = {'low': 0, 'medium': 1, 'high': 2, 'critical': 3}
        num = level_map.get(level_str.lower(), 1)
        self.history.append(num)

    def predict_spike(self):
        """
        Returns spike probability (0..1). Requires at least `history_len` samples.
        """
        if self.model is None or len(self.history) < self.history_len:
            return 0.0
        seq = torch.tensor(list(self.history), dtype=torch.float32).view(1, self.history_len, 1)
        with torch.no_grad():
            prob = self.model(seq).item()
        return prob

    def reset(self):
        self.history.clear()


# ============================================
# MAIN INTEGRATION CLASS (combines both)
# ============================================

class RailwayAIIntegration:
    """Unified interface for the Flask app"""
    def __init__(self):
        self.classifier = CrowdClassifier()
        self.spike_predictor = CrowdSpikePredictor()
        print("✅ Railway AI Integration ready (CNN classifier + GNN spike predictor)")

    def process_camera_frame(self, frame):
        """Process a camera frame, update spike predictor, return full analysis."""
        level, people, conf = self.classifier.predict(frame)
        self.spike_predictor.add_level(level)
        spike_prob = self.spike_predictor.predict_spike()

        # Determine color and alert
        if spike_prob > 0.7 or level in ['high', 'critical']:
            color = 'red'
            alert = True
        elif spike_prob > 0.4 or level == 'medium':
            color = 'yellow'
            alert = False
        else:
            color = 'green'
            alert = False

        return {
            'crowd_level': level,
            'estimated_people': people,
            'confidence': conf,
            'spike_probability': spike_prob,
            'signal': color,
            'alert': alert,
            'timestamp': datetime.now().isoformat()
        }

    def reset_spike_history(self):
        self.spike_predictor.reset()


# ============================================
# TEST CODE (optional)
# ============================================

if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("TESTING RAILWAY AI INTEGRATION")
    print("=" * 60)

    ai = RailwayAIIntegration()

    # Test with a dummy image (or use a real file)
    dummy = np.zeros((224, 224, 3), dtype=np.uint8)
    result = ai.process_camera_frame(dummy)
    for k, v in result.items():
        print(f"  {k}: {v}")

    print("\n✅ Integration test complete")