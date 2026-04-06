# insert_all_trains.py
import mysql.connector
import random
from datetime import datetime

# Database configuration (same as in apps.py)
db_config = {
    'host': 'localhost',
    'user': 'root',
    'password': 'your password',  # Change to your MySQL root password
    'database': 'railway_db'
}

# List of all stations (15)
INDIAN_STATIONS = [
    "Mumbai Central", "Delhi Junction", "Howrah Junction", "Chennai Central",
    "Bengaluru City", "Kolkata Sealdah", "Lucknow Junction", "Pune Junction",
    "Ahmedabad Junction", "Jaipur Junction", "Hyderabad Deccan", "Patna Junction",
    "Bhopal Junction", "Chandigarh Junction", "Guwahati Junction"
]

def generate_train_name(origin, destination, train_number):
    """Generate realistic Indian train name based on origin and destination"""
    name_templates = [
        f"{origin} {destination} Express",
        f"{origin} {destination} Superfast",
        f"{origin} {destination} Mail",
        f"{origin} Duronto",
        f"{origin} Shatabdi",
        f"{origin} Rajdhani",
        f"{origin} Jan Shatabdi",
        f"{origin} Garib Rath",
        f"{origin} Tejas",
        f"{origin} Humsafar",
        f"{origin} Antyodaya",
        f"{origin} Sampark Kranti",
        f"{origin} Intercity",
        f"{origin} AC Express",
        f"{origin} Passenger"
    ]
    # Use train number to cycle through templates
    return name_templates[train_number % len(name_templates)]

def generate_schedule():
    """Generate random scheduled time (hour:minute) with 30-min intervals"""
    hour = random.randint(0, 23)
    minute = random.choice([0, 30])
    return f"{hour:02d}:{minute:02d}"

def insert_trains():
    conn = mysql.connector.connect(**db_config)
    cursor = conn.cursor()

    # Optional: Clear existing trains (uncomment if you want fresh data)
    # cursor.execute("DELETE FROM trains")
    # print("Cleared existing trains.")

    # Get current max id to avoid conflicts
    cursor.execute("SELECT MAX(id) FROM trains")
    max_id = cursor.fetchone()[0] or 0
    next_id = max_id + 1

    total_inserted = 0
    for origin in INDIAN_STATIONS:
        # Get possible destinations (exclude origin)
        destinations = [s for s in INDIAN_STATIONS if s != origin]
        # Shuffle destinations to randomize
        random.shuffle(destinations)
        # Take first 15 (there are 14 other stations, but we need 15 trains; we'll allow repeats if needed)
        # Actually we have 14 other stations; to get 15 trains we need one duplicate destination.
        # We'll pick 15 destinations with possible repetition.
        chosen_destinations = []
        for i in range(15):
            # For first 14 use unique, the 15th repeat a random one
            if i < len(destinations):
                chosen_destinations.append(destinations[i])
            else:
                chosen_destinations.append(random.choice(destinations))
        
        for i, dest in enumerate(chosen_destinations):
            train_id = next_id
            next_id += 1
            train_name = generate_train_name(origin, dest, i)
            scheduled_time = generate_schedule()
            # Insert
            cursor.execute('''
                INSERT INTO trains (id, name, from_station, to_station, track, scheduled_time, current_delay, status, estimated_arrival)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ''', (train_id, train_name, origin, dest, "A", scheduled_time, 0, "on_time", scheduled_time))
            total_inserted += 1
    
    conn.commit()
    cursor.close()
    conn.close()
    print(f"✅ Successfully inserted {total_inserted} trains.")
    print(f"   Each of the {len(INDIAN_STATIONS)} stations now has 15 departing trains.")

if __name__ == "__main__":
    insert_trains()