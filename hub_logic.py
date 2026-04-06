import paho.mqtt.client as mqtt
import json
import mysql.connector
import time
import threading
from datetime import datetime
import requests

# Database config
db_config = {
    'host': 'localhost',
    'user': 'root',
    'password': 'your_password_here',
    'database': 'railway_db'
}

def get_db_connection():
    return mysql.connector.connect(**db_config)

# Ask for station name on startup
station_name = input("Enter station name (e.g., Mumbai Central): ").strip()
if not station_name:
    print("No station entered. Exiting.")
    exit()

# Verify station exists in database
conn = get_db_connection()
cursor = conn.cursor()
cursor.execute("SELECT COUNT(*) FROM trains WHERE from_station = %s OR to_station = %s", (station_name, station_name))
if cursor.fetchone()[0] == 0:
    print(f"No trains found for station '{station_name}'. Exiting.")
    exit()
cursor.close()
conn.close()
print(f"Monitoring station: {station_name}")

PROJECT_ID = "railway_secure_2026_xyz"
TRACK_IN = f"{PROJECT_ID}/track/status"
TRAIN_OUT = f"{PROJECT_ID}/hub/to_train"
TRAIN_IN = f"{PROJECT_ID}/train/to_hub"
IDENTITY_TOPIC = f"{PROJECT_ID}/train/identity"

registered_train = None

def send_http_notification(event_type, train_id, train_name, station):
    """Send HTTP notification to Server 4"""
    app_msg = {
        'train_id': train_id,
        'train_name': train_name,
        'event_type': event_type,
        'station': station,
        'timestamp': datetime.now().isoformat()
    }
    try:
        response = requests.post(
            'http://localhost:5001/api/app-notification',
            json=app_msg,
            timeout=2
        )
        print(f"📱 HTTP notification sent to Server 4. Status: {response.status_code}")
        if response.status_code == 200:
            print(f"✅ Notification delivered")
        else:
            print(f"⚠️ Server 4 returned: {response.text}")
    except requests.exceptions.ConnectionError:
        print(f"❌ Cannot connect to Server 4. Make sure Flask app is running on port 5001")
    except Exception as e:
        print(f"❌ HTTP error: {e}")

def on_message(client, userdata, msg):
    global registered_train
    payload = msg.payload.decode()
    print(f"📨 Received on {msg.topic}: {payload}")

    # 1. Handle Train Registration
    if msg.topic == IDENTITY_TOPIC:
        try:
            train_id, train_name = payload.split('|')
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM trains WHERE id = %s AND (from_station = %s OR to_station = %s)", 
                          (train_id, station_name, station_name))
            exists = cursor.fetchone() is not None
            cursor.close()
            conn.close()
            if exists:
                registered_train = {'id': train_id, 'name': train_name}
                print(f"✅ Train {train_name} (ID {train_id}) registered")
                client.publish(TRAIN_OUT, f"REGISTERED|{train_id}")
            else:
                print(f"❌ Train {train_id} not found for this station")
                client.publish(TRAIN_OUT, f"REJECTED|{train_id}")
        except Exception as e:
            print(f"Identity error: {e}")

    # 2. Handle Track Status (from Server 1)
    elif msg.topic == TRACK_IN:
        if not registered_train:
            print("No registered train, ignoring track status")
            return
        
        print(f"📡 Track status: {payload}")
        
        if "OBSTACLE" in payload:
            client.publish(TRAIN_OUT, "OBSTACLE_DETECTED")
            print(f"🚨 Forwarded OBSTACLE_DETECTED to train")
        elif "CLEAR" in payload:
            client.publish(TRAIN_OUT, "TRACK_CLEAR")
            print(f"✅ Forwarded TRACK_CLEAR to train")

    # 3. Handle Train Feedback (from Server 3) - SEND HTTP TO SERVER 4
    elif msg.topic == TRAIN_IN:
        print(f"🚄 Train feedback: {payload}")
        try:
            if '|' in payload:
                parts = payload.split('|')
                if len(parts) >= 2:
                    event_type = parts[0]
                    train_id = parts[1]
                    
                    if registered_train and train_id == registered_train['id']:
                        # Send HTTP notification to Server 4
                        send_http_notification(event_type, train_id, registered_train['name'], station_name)
        except Exception as e:
            print(f"Error processing train feedback: {e}")

# MQTT Client Setup
client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="Central_Hub_99")
client.on_message = on_message
client.connect("broker.hivemq.com", 1883, 60)
client.subscribe([(TRACK_IN, 0), (IDENTITY_TOPIC, 0), (TRAIN_IN, 0)])
client.loop_start()

print(f"✅ Server 2 Hub started")
print("Waiting for train registration...")

try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    client.disconnect()