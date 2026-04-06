# populate_trains.py
import mysql.connector
from datetime import datetime, timedelta
import random

# Database connection (same as apps.py)
db_config = {
    'host': 'localhost',
    'user': 'root',
    'password': 'your_password',  # Change to your MySQL root password
    'database': 'railway_db'
}

# List of Indian stations (15 stations)
INDIAN_STATIONS = [
    "Mumbai Central", "Delhi Junction", "Howrah Junction", "Chennai Central",
    "Bengaluru City", "Kolkata Sealdah", "Lucknow Junction", "Pune Junction",
    "Ahmedabad Junction", "Jaipur Junction", "Hyderabad Deccan", "Patna Junction",
    "Bhopal Junction", "Chandigarh Junction", "Guwahati Junction"
]

def generate_train_schedule():
    """Generate 15 trains per station for tomorrow"""
    conn = mysql.connector.connect(**db_config)
    cursor = conn.cursor()
    
    # Clear existing trains
    cursor.execute("DELETE FROM trains")
    
    train_id = 1
    tomorrow = datetime.now().date() + timedelta(days=1)
    
    # For each station as origin, create 15 trains to random destinations
    for origin in INDIAN_STATIONS:
        # Choose random destinations (excluding the origin itself)
        destinations = [s for s in INDIAN_STATIONS if s != origin]
        for i in range(15):
            destination = random.choice(destinations)
            # Random scheduled time between 00:00 and 23:30 (30 min intervals)
            hour = random.randint(0, 23)
            minute = random.choice([0, 30])
            scheduled_time = f"{hour:02d}:{minute:02d}"
            
            # Train name
            train_name = f"Train {train_id:03d}"
            
            # Insert
            cursor.execute('''
                INSERT INTO trains (id, name, from_station, to_station, track, scheduled_time, current_delay, status, estimated_arrival)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ''', (train_id, train_name, origin, destination, "A", scheduled_time, 0, "on_time", scheduled_time))
            
            train_id += 1
    
    conn.commit()
    cursor.close()
    conn.close()
    print(f"✅ Inserted {train_id-1} trains for tomorrow ({tomorrow})")
    print(f"   Each of the {len(INDIAN_STATIONS)} stations has 15 departing trains.")

if __name__ == "__main__":
    generate_train_schedule()