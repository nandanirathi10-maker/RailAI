# insert_sample_crowd_logs_all_stations.py
import mysql.connector
from datetime import datetime, timedelta

db_config = {
    'host': 'localhost',
    'user': 'root',
    'password': 'your_password',  # Change to your MySQL root password
    'database': 'railway_db'
}

# List of all Indian stations (must match your INDIAN_STATIONS list)
stations = [
    "Mumbai Central", "Delhi Junction", "Howrah Junction", "Chennai Central",
    "Bengaluru City", "Kolkata Sealdah", "Lucknow Junction", "Pune Junction",
    "Ahmedabad Junction", "Jaipur Junction", "Hyderabad Deccan", "Patna Junction",
    "Bhopal Junction", "Chandigarh Junction", "Guwahati Junction"
]

# Pattern of crowd levels and corresponding predicted counts (same for all stations)
levels = ['Low', 'Low', 'Low', 'Medium', 'Medium', 'Medium', 'High', 'High', 'High', 
          'Critical', 'Critical', 'High', 'High', 'Medium', 'Medium', 'Low', 'Low', 'Low', 'Medium', 'High']
predicted_crowds = [50, 60, 80, 120, 150, 180, 220, 260, 300, 420, 400, 350, 300, 250, 200, 150, 100, 80, 120, 220]

conn = mysql.connector.connect(**db_config)
cursor = conn.cursor()
now = datetime.now()

for station in stations:
    # Clear old logs for this station (optional)
    cursor.execute("DELETE FROM station_crowd_log WHERE station_name = %s", (station,))
    
    # Insert 20 records, each 5 minutes apart, going backwards in time
    for i, (level, crowd) in enumerate(zip(levels, predicted_crowds)):
        # Shift each station's timestamps slightly so they don't all look identical
        timestamp = now - timedelta(minutes=(20 - i) * 5 + stations.index(station) % 3)
        cursor.execute('''
            INSERT INTO station_crowd_log (station_name, timestamp, predicted_crowd, crowd_level, delay_impact, train_ids)
            VALUES (%s, %s, %s, %s, %s, %s)
        ''', (station, timestamp, crowd, level, 0, ''))
    
    print(f"✅ Inserted 20 sample crowd logs for {station}")

conn.commit()
cursor.close()
conn.close()
print("🎉 All stations populated with sample crowd logs.")