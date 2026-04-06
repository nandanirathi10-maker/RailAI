import numpy as np
import random
from datetime import datetime

class CrowdPredictor:
    def __init__(self):
        # Simulated CNN model for crowd detection
        # In production, you'd load actual TensorFlow/PyTorch models
        self.passenger_database = self.init_passenger_database()
        
    def init_passenger_database(self):
        """Simulated passenger database with booking data"""
        return {
            "Express 101": {"base_passengers": 200, "peak_hours": ["08:00", "09:00", "17:00", "18:00"]},
            "Local 205": {"base_passengers": 80, "peak_hours": ["08:30", "09:30", "17:30", "18:30"]},
            "Superfast 307": {"base_passengers": 150, "peak_hours": ["09:00", "10:00", "16:00", "17:00"]},
            "Freight 88": {"base_passengers": 50, "peak_hours": ["10:00", "11:00", "14:00", "15:00"]},
            "Intercity 12": {"base_passengers": 120, "peak_hours": ["09:30", "10:30", "18:00", "19:00"]}
        }
    
    def predict_crowd(self, train_id, timestamp):
        """Predict crowd density based on delay and time"""
        train_info = self.passenger_database.get(train_id, {"base_passengers": 100, "peak_hours": []})
        base_crowd = train_info["base_passengers"]
        
        # Convert timestamp to time string
        if isinstance(timestamp, str):
            time_str = datetime.fromisoformat(timestamp).strftime("%H:%M")
        else:
            time_str = datetime.now().strftime("%H:%M")
        
        # Check if in peak hours
        is_peak = time_str in train_info["peak_hours"]
        peak_multiplier = 1.5 if is_peak else 1.0
        
        # Simulate GNN influence from other trains (random for demo)
        other_trains_factor = random.uniform(0.8, 1.3)
        
        predicted_crowd = int(base_crowd * peak_multiplier * other_trains_factor)
        
        # Determine density level
        if predicted_crowd < 80:
            density_level = "Low"
        elif predicted_crowd < 150:
            density_level = "Medium"
        else:
            density_level = "High"
        
        return {
            "train_id": train_id,
            "predicted_crowd": predicted_crowd,
            "density_level": density_level,
            "base_crowd": base_crowd,
            "is_peak_hour": is_peak,
            "recommendation": "Consider waiting for next train" if density_level == "High" else "Normal boarding"
        }
    
    def predict(self, train_id, station):
        """Public method to get prediction"""
        return self.predict_crowd(train_id, datetime.now().isoformat())