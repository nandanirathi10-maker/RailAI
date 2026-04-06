# apps.py - Complete corrected version

import json
import threading
import time
import os
from datetime import datetime, timedelta
from flask import Flask, render_template, jsonify, request, session, redirect
from flask_cors import CORS
from flask_socketio import SocketIO
import paho.mqtt.client as mqtt
import hashlib
import secrets
import mysql.connector
import cv2
import torch
from models.trained_models import RailwayAIIntegration

app = Flask(__name__)
app.secret_key = secrets.token_hex(16)
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*")

# ============================================
# DATABASE CONNECTION
# ============================================
db_config = {
    'host': 'localhost',
    'user': 'root',
    'password': 'your_password',
    'database': 'railway_db'
}

def get_db_connection():
    return mysql.connector.connect(**db_config)

# ============================================
# DATABASE INITIALIZATION
# ============================================
def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()

    # Create tables if not exist (only one definition per table)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS trains (
        id INT PRIMARY KEY,
        name VARCHAR(100),
        from_station VARCHAR(100),
        to_station VARCHAR(100),
        track VARCHAR(10),
        scheduled_time TIME,
        current_delay INT DEFAULT 0,
        status VARCHAR(20),
        estimated_arrival TIME
    )
    ''')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS train_events (
        id INT AUTO_INCREMENT PRIMARY KEY,
        train_id INT,
        event_type VARCHAR(20),
        timestamp DATETIME,
        track VARCHAR(10),
        delay_minutes INT DEFAULT 0
    )
    ''')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id INT AUTO_INCREMENT PRIMARY KEY,
        username VARCHAR(50) UNIQUE NOT NULL,
        email VARCHAR(100) UNIQUE NOT NULL,
        password VARCHAR(255) NOT NULL,
        phone VARCHAR(20),
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    ''')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS tickets (
        id INT AUTO_INCREMENT PRIMARY KEY,
        ticket_id VARCHAR(50) UNIQUE NOT NULL,
        user_id INT,
        train_id INT,
        train_name VARCHAR(100),
        from_station VARCHAR(100),
        to_station VARCHAR(100),
        journey_date DATE,
        departure_time TIME,
        passenger_name VARCHAR(100),
        passenger_age INT,
        seat_number VARCHAR(10),
        fare DECIMAL(10,2),
        status VARCHAR(20) DEFAULT 'confirmed',
        booking_time DATETIME DEFAULT CURRENT_TIMESTAMP,
        block_hash VARCHAR(255)
    )
    ''')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS station_crowd_log (
        id INT AUTO_INCREMENT PRIMARY KEY,
        station_name VARCHAR(100),
        timestamp DATETIME,
        predicted_crowd INT,
        crowd_level VARCHAR(20),
        delay_impact INT,
        train_ids TEXT
    )
    ''')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS notifications (
        id INT AUTO_INCREMENT PRIMARY KEY,
        user_id INT,
        station_name VARCHAR(100),
        message TEXT,
        sent_at DATETIME,
        sent_via VARCHAR(20),
        status VARCHAR(20)
    )
    ''')

    # Add schedule_date column if not exists
    try:
        cursor.execute("ALTER TABLE trains ADD COLUMN schedule_date DATE")
        print("✅ Added schedule_date column")
    except mysql.connector.Error as err:
        if err.errno != 1060:  # duplicate column
            print(f"⚠️ Could not add schedule_date: {err}")
        else:
            print("schedule_date column already exists")

    # Set default date for existing rows
    cursor.execute("UPDATE trains SET schedule_date = CURDATE() WHERE schedule_date IS NULL")
    conn.commit()

    # Add phone/email columns if missing (for older schema)
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN phone VARCHAR(20)")
    except mysql.connector.Error as err:
        if err.errno != 1060:
            print(f"⚠️ Could not add phone column: {err}")
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN email VARCHAR(100)")
    except mysql.connector.Error as err:
        if err.errno != 1060:
            print(f"⚠️ Could not add email column: {err}")

    # Insert sample trains if table is empty
    cursor.execute("SELECT COUNT(*) FROM trains")
    if cursor.fetchone()[0] == 0:
        sample_trains = [
            (1, "Rajdhani Express", "Mumbai Central", "New Delhi", "A", "06:00", 0, "on_time", "06:00"),
            (2, "Shatabdi Express", "New Delhi", "Lucknow", "A", "07:30", 0, "on_time", "07:30"),
            (3, "Duronto Express", "Howrah", "New Delhi", "A", "08:00", 0, "on_time", "08:00"),
            (4, "Garib Rath", "Chennai", "Bengaluru", "A", "09:00", 0, "on_time", "09:00"),
            (5, "Jan Shatabdi", "Mumbai", "Pune", "A", "10:00", 0, "on_time", "10:00"),
            (6, "Tejas Express", "Delhi", "Chandigarh", "A", "11:00", 0, "on_time", "11:00"),
            (7, "Vande Bharat", "Delhi", "Varanasi", "A", "12:00", 0, "on_time", "12:00"),
            (8, "Double Decker", "Mumbai", "Ahmedabad", "A", "13:00", 0, "on_time", "13:00"),
            (9, "Humsafar Express", "Delhi", "Patna", "A", "14:00", 0, "on_time", "14:00"),
            (10, "Antyodaya Express", "Howrah", "Guwahati", "A", "15:00", 0, "on_time", "15:00"),
        ]
        for t in sample_trains:
            cursor.execute('''
                INSERT INTO trains (id, name, from_station, to_station, track, scheduled_time, current_delay, status, estimated_arrival)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ''', t)

    conn.commit()
    cursor.close()
    conn.close()
    print("✅ Database initialized")

# ============================================
# MQTT TRAIN DELAY TRACKING
# ============================================
PROJECT_ID = "railway_secure_2026_xyz"
APP_EVENTS_TOPIC = f"{PROJECT_ID}/app/events"

train_delays = {}
train_events = {}

def update_train_delay_from_mqtt():
    def on_message(client, userdata, msg):
        payload = msg.payload.decode()
        try:
            data = json.loads(payload)
            train_id = data.get("train_id")
            event_type = data.get("event_type")
            timestamp = data.get("timestamp")
            if event_type == "STOP":
                train_events[train_id] = {"stop_time": timestamp}
            elif event_type == "START":
                if train_id in train_events and train_events[train_id].get("stop_time"):
                    stop_dt = datetime.fromisoformat(train_events[train_id]["stop_time"])
                    start_dt = datetime.fromisoformat(timestamp)
                    delay = int((start_dt - stop_dt).total_seconds() / 60)
                    train_delays[train_id] = delay
                    conn = get_db_connection()
                    cursor = conn.cursor()
                    cursor.execute("UPDATE trains SET current_delay = %s WHERE id = %s", (delay, train_id))
                    conn.commit()
                    cursor.close()
                    conn.close()
                    print(f"Train {train_id} delayed by {delay} minutes")
                    recompute_crowd_for_stations()
        except Exception as e:
            print(f"MQTT error: {e}")

def calculate_delay(train_id):
    """Calculate delay based on stop/start times"""
    events = train_events.get(train_id)
    if events and events.get("stop_time") and events.get("start_time"):
        stop_dt = datetime.fromisoformat(events["stop_time"])
        start_dt = datetime.fromisoformat(events["start_time"])
        delay_minutes = int((start_dt - stop_dt).total_seconds() / 60)
        events["delay"] = delay_minutes
        
        # Update database (MySQL)
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE trains SET current_delay = current_delay + %s WHERE id = %s", (delay_minutes, train_id))
        conn.commit()
        cursor.close()
        conn.close()
        
        print(f"📊 Train {train_id} delayed by {delay_minutes} minutes")
        return delay_minutes
    return 0

def on_mqtt_message(client, userdata, msg):
    payload = msg.payload.decode()
    print(f"🔔 Server 4 received: {payload}")
    
    try:
        data = json.loads(payload)
        train_id = data.get("train_id")
        event_type = data.get("event_type")
        station = data.get("station")
        train_name = data.get("train_name")
        
        if not train_id or not event_type:
            print("⚠️ Missing train_id or event_type")
            return
        
        # Clean up event_type
        clean_event = event_type.lower()
        if '_at_station' in clean_event:
            clean_event = clean_event.replace('_at_station', '')
        if 'train_started' in clean_event:
            clean_event = 'started'
        elif 'train_stopped' in clean_event:
            clean_event = 'stopped'
        elif 'brakes_applied' in clean_event:
            clean_event = 'brakes applied'
        
        # Message WITHOUT station name
        message_text = f"🚆 Train {train_name} has {clean_event}."
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT id FROM users")
        all_users = cursor.fetchall()
        
        for user in all_users:
            cursor.execute('''
                INSERT INTO notifications (user_id, station_name, message, sent_at, sent_via, status)
                VALUES (%s, %s, %s, %s, %s, %s)
            ''', (user[0], station, message_text, datetime.now(), 'mqtt', 'sent'))
        
        conn.commit()
        cursor.close()
        conn.close()
        
        print(f"📢 Created {len(all_users)} notifications")
        
    except Exception as e:
        print(f"❌ Error: {e}")

def mqtt_thread_func():
    mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="App_Server_4")
    mqtt_client.on_message = on_mqtt_message
    mqtt_client.connect("broker.hivemq.com", 1883, 60)
    mqtt_client.subscribe(APP_EVENTS_TOPIC)
    mqtt_client.loop_forever()

# Start MQTT in background thread
mqtt_thread = threading.Thread(target=mqtt_thread_func, daemon=True)
mqtt_thread.start()


def app_events_mqtt_thread():
    """Separate MQTT client that listens for app events from Server 2"""
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="App_Events_Listener")
    client.on_message = on_mqtt_message
    client.connect("broker.hivemq.com", 1883, 60)
    client.subscribe(APP_EVENTS_TOPIC)
    print(f"✅ App Events listener subscribed to: {APP_EVENTS_TOPIC}")
    client.loop_forever()

# Start the app events listener thread
app_events_thread = threading.Thread(target=app_events_mqtt_thread, daemon=True)
app_events_thread.start()
print("✅ App Events MQTT listener started")

# ============================================
# RULE-BASED STATION CROWD PREDICTION (for alerts and graphs)
# ============================================
INDIAN_STATIONS = [
    "Mumbai Central", "Delhi Junction", "Howrah Junction", "Chennai Central",
    "Bengaluru City", "Kolkata Sealdah", "Lucknow Junction", "Pune Junction",
    "Ahmedabad Junction", "Jaipur Junction", "Hyderabad Deccan", "Patna Junction",
    "Bhopal Junction", "Chandigarh Junction", "Guwahati Junction"
]
station_capacity = {station: 500 for station in INDIAN_STATIONS}

def get_train_schedule():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id, name, from_station, to_station, scheduled_time, current_delay, estimated_arrival, schedule_date FROM trains")
    trains = cursor.fetchall()
    cursor.close()
    conn.close()
    for t in trains:
        raw_time = str(t['scheduled_time'])
        t['scheduled_time'] = raw_time[:5] if len(raw_time) > 5 else raw_time
        raw_est = str(t['estimated_arrival'])
        t['estimated_arrival'] = raw_est[:5] if len(raw_est) > 5 else raw_est
        # schedule_date is a date object; keep as is
    return trains

def compute_station_crowd(station_name, current_time=None):
    if current_time is None:
        current_time = datetime.now()
    trains = get_train_schedule()
    window = 30  # minutes into the future
    crowd = 0
    affected_trains = []
    for train in trains:
        if train['from_station'] != station_name and train['to_station'] != station_name:
            continue
        sched_str = train['scheduled_time']
        if ':' in sched_str and sched_str.count(':') == 2:
            sched_str = sched_str[:5]
        try:
            sched_time = datetime.strptime(sched_str, "%H:%M").time()
        except:
            continue
        # Use the train's schedule_date (or today)
        train_date = train.get('schedule_date') or current_time.date()
        sched_dt = datetime.combine(train_date, sched_time)
        delay = train['current_delay']
        actual_dt = sched_dt + timedelta(minutes=delay)
        # If the train is already late (actual_dt < current_time), treat as immediate crowd (diff = 0)
        if actual_dt < current_time:
            diff = 0
        else:
            diff = (actual_dt - current_time).total_seconds() / 60
        if diff <= window:
            crowd += 150
            affected_trains.append(train['id'])
    total_crowd = min(50 + crowd, station_capacity.get(station_name, 500))
    if total_crowd < 100:
        level = "Low"
    elif total_crowd < 250:
        level = "Medium"
    elif total_crowd < 400:
        level = "High"
    else:
        level = "Critical"
    return {
        "station": station_name,
        "predicted_crowd": total_crowd,
        "crowd_level": level,
        "affected_trains": affected_trains,
        "timestamp": current_time.isoformat()
    }

@app.route('/api/ai/crowded-trains')
def crowded_trains():
    threshold = request.args.get('threshold', 250, type=int)
    predictions = []
    for station in INDIAN_STATIONS:
        pred = compute_station_crowd(station)
        if pred['predicted_crowd'] > threshold:
            predictions.append({
                'station': station,
                'predicted_crowd': pred['predicted_crowd'],
                'crowd_level': pred['crowd_level'],
                'recommendation': 'High crowd expected' if pred['crowd_level'] == 'High' else 'Critical crowd, avoid'
            })
    return jsonify(predictions)

def store_crowd_predictions():
    conn = get_db_connection()
    cursor = conn.cursor()
    for station in INDIAN_STATIONS:
        pred = compute_station_crowd(station)
        cursor.execute('''
            INSERT INTO station_crowd_log (station_name, timestamp, predicted_crowd, crowd_level, delay_impact, train_ids)
            VALUES (%s, %s, %s, %s, %s, %s)
        ''', (station, datetime.now(), pred['predicted_crowd'], pred['crowd_level'],
              len(pred['affected_trains']), ','.join(map(str, pred['affected_trains']))))
    conn.commit()
    cursor.close()
    conn.close()

# Add a dictionary to store last alert level per station
last_alert_level = {}

def send_crowd_alerts(station, prediction):
    global last_alert_level
    current_level = prediction['crowd_level']
    affected_train_ids = prediction['affected_trains']
    
    # Only send alert if crowd level is High or Critical AND it's a new level (or escalated)
    if current_level not in ['High', 'Critical']:
        return
    
    last_level = last_alert_level.get(station)
    if last_level == current_level:
        # Already alerted for this level, skip to avoid spam
        return
    last_alert_level[station] = current_level
    
    if not affected_train_ids:
        return
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    placeholders = ','.join(['%s'] * len(affected_train_ids))
    cursor.execute(f'''
        SELECT DISTINCT u.id, u.username, u.phone, u.email
        FROM tickets t
        JOIN users u ON t.user_id = u.id
        WHERE t.train_id IN ({placeholders})
          AND t.from_station = %s
          AND DATE(t.journey_date) = CURDATE()
    ''', affected_train_ids + [station])
    users = cursor.fetchall()
    cursor.close()
    conn.close()
    
    if not users:
        return
    
    message = f"🚨 Crowd Alert at {station}: {current_level} level with {prediction['predicted_crowd']} passengers. Your train(s) may be delayed."
    
    for user in users:
        conn2 = get_db_connection()
        cursor2 = conn2.cursor()
        if user.get('email'):
            cursor2.execute('''
                INSERT INTO notifications (user_id, station_name, message, sent_at, sent_via, status)
                VALUES (%s, %s, %s, %s, %s, %s)
            ''', (user['id'], station, message, datetime.now(), 'email', 'sent'))
        if user.get('phone'):
            cursor2.execute('''
                INSERT INTO notifications (user_id, station_name, message, sent_at, sent_via, status)
                VALUES (%s, %s, %s, %s, %s, %s)
            ''', (user['id'], station, message, datetime.now(), 'sms', 'sent'))
        conn2.commit()
        cursor2.close()
        conn2.close()
    print(f"Alerts sent to {len(users)} users for {station} ({current_level})")

def recompute_crowd_for_stations():
    for station in INDIAN_STATIONS:
        pred = compute_station_crowd(station)
        if pred['crowd_level'] in ['High', 'Critical']:
            send_crowd_alerts(station, pred)
    store_crowd_predictions()

# ============================================
# AI INTEGRATION (CNN classifier + GNN spike predictor)
# ============================================
ai_integration = RailwayAIIntegration()

@app.route('/api/camera/status')
def camera_status():
    cap = cv2.VideoCapture(0)
    ret, frame = cap.read()
    cap.release()
    if not ret:
        return jsonify({'error': 'Camera not available'}), 500
    result = ai_integration.process_camera_frame(frame)
    return jsonify(result)

# ============================================
# FLASK ROUTES
# ============================================

@app.route('/')
def index():
    return redirect('/select_city')

@app.route('/select_city')
def select_city():
    return render_template('select_city.html')

@app.route('/dashboard')
def dashboard():
    city = request.args.get('city') or session.get('city')
    if not city:
        return redirect('/select_city')
    session['city'] = city
    return render_template('dashboard.html', city=city)

@app.route('/cnn')
def cnn_page():
    return render_template('cnn.html')

@app.route('/gnn')
def gnn_page():
    return render_template('gnn.html')

@app.route('/login')
def login_page():
    return render_template('login.html')

@app.route('/register')
def register_page():
    return render_template('register.html')

@app.route('/book')
def book_page():
    return render_template('book_ticket.html')

# ========== API ROUTES ==========

@app.route('/api/register', methods=['POST'])
def register():
    data = request.json
    username = data.get('username')
    email = data.get('email')
    password = data.get('password')
    phone = data.get('phone')
    if not all([username, email, password]):
        return jsonify({'error': 'Missing fields'}), 400
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        hashed = hashlib.sha256(password.encode()).hexdigest()
        cursor.execute("INSERT INTO users (username, email, password, phone) VALUES (%s, %s, %s, %s)",
                       (username, email, hashed, phone))
        conn.commit()
        user_id = cursor.lastrowid
        return jsonify({'success': True, 'user_id': user_id, 'username': username})
    except mysql.connector.IntegrityError:
        return jsonify({'error': 'Username or email exists'}), 400
    finally:
        cursor.close()
        conn.close()

@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    username = data.get('username')
    password = data.get('password')
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    hashed = hashlib.sha256(password.encode()).hexdigest()
    cursor.execute("SELECT id, username, email FROM users WHERE username=%s AND password=%s", (username, hashed))
    user = cursor.fetchone()
    cursor.close()
    conn.close()
    if user:
        return jsonify({'success': True, 'user_id': user['id'], 'username': user['username'], 'email': user['email']})
    return jsonify({'error': 'Invalid credentials'}), 401

@app.route('/api/stations')
def get_stations():
    return jsonify(INDIAN_STATIONS)

@app.route('/api/trains')
def get_all_trains():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id, name, from_station, to_station, scheduled_time, current_delay, status, estimated_arrival FROM trains")
    trains = cursor.fetchall()
    cursor.close()
    conn.close()
    for t in trains:
        t['scheduled_time'] = str(t['scheduled_time'])
        t['estimated_arrival'] = str(t['estimated_arrival'])
    return jsonify(trains)

@app.route('/api/trains/by_station/<station>')
def get_trains_by_station(station):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute('''
        SELECT id, name, from_station, to_station, scheduled_time, current_delay, status, estimated_arrival, schedule_date
        FROM trains
        WHERE from_station = %s OR to_station = %s
    ''', (station, station))
    trains = cursor.fetchall()
    cursor.close()
    conn.close()
    for t in trains:
        t['scheduled_time'] = str(t['scheduled_time'])[:5]
        t['estimated_arrival'] = str(t['estimated_arrival'])[:5]
        t['schedule_date'] = str(t['schedule_date']) if t['schedule_date'] else None
    return jsonify(trains)

@app.route('/api/tickets/book', methods=['POST'])
def book_ticket():
    data = request.json
    user_id = data.get('user_id')
    train_id = data.get('train_id')
    from_station = data.get('from_station')
    to_station = data.get('to_station')
    journey_date = data.get('journey_date')
    passenger_name = data.get('passenger_name')
    passenger_age = data.get('passenger_age')
    fare = data.get('fare', 100)
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT name, scheduled_time FROM trains WHERE id = %s", (train_id,))
    train = cursor.fetchone()
    if not train:
        return jsonify({'error': 'Train not found'}), 404
    ticket_id = f"TKT-{secrets.token_hex(4).upper()}"
    block_hash = hashlib.sha256(f"{ticket_id}{train_id}{datetime.now()}".encode()).hexdigest()
    cursor.execute('''
        INSERT INTO tickets (ticket_id, user_id, train_id, train_name, from_station, to_station, 
                             journey_date, departure_time, passenger_name, passenger_age, fare, block_hash)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    ''', (ticket_id, user_id, train_id, train['name'], from_station, to_station,
          journey_date, train['scheduled_time'], passenger_name, passenger_age, fare, block_hash))
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({'success': True, 'ticket_id': ticket_id, 'train_name': train['name'],
                    'departure_time': str(train['scheduled_time']), 'block_hash': block_hash})

@app.route('/api/tickets/<int:user_id>')
def get_user_tickets(user_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute('''
        SELECT ticket_id, train_name, from_station, to_station, journey_date, 
               departure_time, passenger_name, status, fare 
        FROM tickets WHERE user_id = %s ORDER BY booking_time DESC
    ''', (user_id,))
    tickets = cursor.fetchall()
    cursor.close()
    conn.close()
    for t in tickets:
        t['departure_time'] = str(t['departure_time'])
        t['journey_date'] = str(t['journey_date'])
    return jsonify(tickets)

@app.route('/api/notifications/<int:user_id>')
def get_notifications(user_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute('''
        SELECT id, station_name, message, sent_at, sent_via, status
        FROM notifications 
        WHERE user_id = %s 
        ORDER BY sent_at DESC 
        LIMIT 50
    ''', (user_id,))
    notifs = cursor.fetchall()
    cursor.close()
    conn.close()
    return jsonify(notifs)

# ============================================
# BACKGROUND TASKS
# ============================================

def periodic_crowd_update():
    while True:
        try:
            time.sleep(300)
            recompute_crowd_for_stations()
        except Exception as e:
            print(f"Periodic crowd update error: {e}")

threading.Thread(target=periodic_crowd_update, daemon=True).start()

# ========== CNN & GNN PREDICTION ENDPOINTS (for the separate pages) ==========
@app.route('/api/predict/cnn', methods=['POST'])
def predict_cnn():
    data = request.json
    station = data.get('station')
    if not station:
        return jsonify({'error': 'Station required'}), 400
    result = compute_station_crowd(station)
    result['model'] = 'CNN (rule‑based)'
    return jsonify(result)

@app.route('/api/predict/gnn', methods=['POST'])
def predict_gnn():
    data = request.json
    station = data.get('station')
    if not station:
        return jsonify({'error': 'Station required'}), 400
    result = compute_station_crowd(station)
    result['model'] = 'GNN (rule‑based)'
    return jsonify(result)


@app.route('/api/gnn/spike-history/<station>')
def gnn_spike_history(station):
    try:
        hours = request.args.get('hours', 24, type=int)
        since = datetime.now() - timedelta(hours=hours)
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute('''
            SELECT timestamp, predicted_crowd
            FROM station_crowd_log
            WHERE station_name = %s AND timestamp > %s
            ORDER BY timestamp
        ''', (station, since))
        rows = cursor.fetchall()
        cursor.close()
        conn.close()

        if len(rows) < 10:
            return jsonify({'timestamps': [], 'probabilities': [], 'message': f'Only {len(rows)} records.'})

        timestamps = [row['timestamp'].isoformat() for row in rows]
        crowds = [row['predicted_crowd'] for row in rows]

        # Compute spike probability for each point using a sliding window of 10
        spike_probs = []
        for i in range(9, len(crowds)):
            window = crowds[i-9:i+1]
            avg_prev = sum(window[:9]) / 9
            current = window[-1]
            if avg_prev > 0:
                ratio = current / avg_prev
                prob = min(1.0, max(0.0, (ratio - 1.0) / 2.0))
            else:
                prob = 0.0
            spike_probs.append(prob)

        return jsonify({
            'timestamps': timestamps[9:],
            'probabilities': spike_probs
        })
    except Exception as e:
        return jsonify({'error': str(e), 'timestamps': [], 'probabilities': []}), 500

@app.route('/api/gnn/current-spike/<station>')
def gnn_current_spike(station):
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute('''
            SELECT timestamp, predicted_crowd, crowd_level
            FROM station_crowd_log
            WHERE station_name = %s
            ORDER BY timestamp DESC
            LIMIT 10
        ''', (station,))
        rows = cursor.fetchall()
        cursor.close()
        conn.close()

        if len(rows) < 10:
            return jsonify({'spike_probability': 0, 'message': f'Only {len(rows)} records, need 10.'})

        rows.reverse()  # oldest first
        crowd_counts = [row['predicted_crowd'] for row in rows]
        levels = [row['crowd_level'] for row in rows]

        # Calculate spike probability based on crowd count increase
        avg_prev = sum(crowd_counts[:9]) / 9
        current = crowd_counts[-1]
        if avg_prev > 0:
            ratio = current / avg_prev
            # Ratio 1.0 -> 0%, 2.0 -> 50%, 3.0 -> 100%
            prob = min(1.0, max(0.0, (ratio - 1.0) / 2.0))
        else:
            prob = 0.0

        return jsonify({
            'spike_probability': prob,
            'timestamp': datetime.now().isoformat(),
            'latest_crowd': current,
            'latest_level': levels[-1]
        })
    except Exception as e:
        return jsonify({'error': str(e), 'spike_probability': 0}), 500
    
@app.route('/api/app-notification', methods=['POST'])
def receive_app_notification():
    try:
        data = request.json
        print(f"📨 HTTP Notification received: {data}")
        
        train_id = data.get('train_id')
        event_type = data.get('event_type')
        station = data.get('station')  # Still needed for filtering in dashboard
        train_name = data.get('train_name')
        
        if not train_id or not event_type:
            return jsonify({'error': 'Missing fields'}), 400
        
        # Clean up event_type - remove any extra suffixes
        clean_event = event_type.lower()
        if '_at_station' in clean_event:
            clean_event = clean_event.replace('_at_station', '')
        if 'train_started' in clean_event:
            clean_event = 'started'
        elif 'train_stopped' in clean_event:
            clean_event = 'stopped'
        elif 'brakes_applied' in clean_event:
            clean_event = 'brakes applied'
        
        # Create notification message WITHOUT station name
        message_text = f"🚆 Train {train_name} has {clean_event}."
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get all users
        cursor.execute("SELECT id FROM users")
        all_users = cursor.fetchall()
        
        for user in all_users:
            cursor.execute('''
                INSERT INTO notifications (user_id, station_name, message, sent_at, sent_via, status)
                VALUES (%s, %s, %s, %s, %s, %s)
            ''', (user[0], station, message_text, datetime.now(), 'http', 'sent'))
        
        conn.commit()
        cursor.close()
        conn.close()
        
        print(f"✅ Inserted {len(all_users)} notifications")
        return jsonify({'success': True, 'notifications_created': len(all_users)})
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return jsonify({'error': str(e)}), 500
    
@app.route('/api/chatbot', methods=['POST'])
def chatbot():
    data = request.json
    user_message = data.get('message', '').lower()
    user_city = data.get('city', '')
    
    # Get train data for the user's city
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    # Train schedule query
    cursor.execute('''
        SELECT name, from_station, to_station, scheduled_time, current_delay, status
        FROM trains 
        WHERE from_station = %s OR to_station = %s
        LIMIT 10
    ''', (user_city, user_city))
    trains = cursor.fetchall()
    
    # Crowd prediction for the city
    crowd_pred = compute_station_crowd(user_city)
    
    cursor.close()
    conn.close()
    
    reply = ""
    
    # Intent detection and response
    if any(word in user_message for word in ['train', 'schedule', 'timing', 'time']):
        if trains:
            reply = f"📅 **Train Schedule for {user_city}:**\n"
            for train in trains[:5]:
                delay_status = f" (Delayed by {train['current_delay']} min)" if train['current_delay'] > 0 else ""
                reply += f"• {train['name']}: {train['from_station']} → {train['to_station']} at {train['scheduled_time']}{delay_status}\n"
            if len(trains) > 5:
                reply += f"\n*Showing 5 of {len(trains)} trains. Check the schedule table for more.*"
        else:
            reply = f"No trains found for {user_city}."
    
    elif any(word in user_message for word in ['delay', 'delayed', 'late']):
        delayed_trains = [t for t in trains if t['current_delay'] > 0]
        if delayed_trains:
            reply = f"⏰ **Delayed Trains in {user_city}:**\n"
            for train in delayed_trains:
                reply += f"• {train['name']}: Delayed by {train['current_delay']} minutes\n"
        else:
            reply = f"✅ No trains are currently delayed in {user_city}."
    
    elif any(word in user_message for word in ['crowd', 'crowded', 'busy', 'density']):
        reply = f"👥 **Crowd Prediction for {user_city}:**\n"
        reply += f"• Predicted Crowd: {crowd_pred['predicted_crowd']} passengers\n"
        reply += f"• Level: **{crowd_pred['crowd_level']}**\n"
        if crowd_pred['crowd_level'] in ['High', 'Critical']:
            reply += f"• ⚠️ {crowd_pred['crowd_level']} crowd expected. Please plan accordingly."
        else:
            reply += f"• Normal crowd expected."
    
    elif any(word in user_message for word in ['book', 'ticket', 'booking']):
        reply = f"🎫 **Booking Information:**\n"
        reply += f"To book a ticket, please visit the **Book Ticket** page using the navigation button above.\n"
        reply += f"Select your train, enter passenger details, and confirm your booking."
    
    elif any(word in user_message for word in ['hello', 'hi', 'hey', 'namaste']):
        reply = f"👋 Hello! Welcome to RailAI Assistant. How can I help you today?\n\nYou can ask me about:\n• Train schedules\n• Delays\n• Crowd predictions\n• Ticket booking"
    
    elif any(word in user_message for word in ['help', 'what can you do', 'features']):
        reply = f"🤖 **I can help you with:**\n"
        reply += f"• 📅 Check train schedules at your station\n"
        reply += f"• ⏰ Get real-time delay information\n"
        reply += f"• 👥 Predict crowd density at stations\n"
        reply += f"• 🎫 Guide you through ticket booking\n"
        reply += f"• ❓ Answer general railway questions"
    
    else:
        reply = f"I understand you're asking about '{user_message}'. Could you please rephrase?\n\nI can help with train schedules, delays, crowd predictions, and ticket booking."
    
    return jsonify({'reply': reply})

@app.route('/api/cnn/predict-image', methods=['POST'])
def cnn_predict_image():
    """Predict crowd density from uploaded image using trained CNN model"""
    if 'image' not in request.files:
        return jsonify({'error': 'No image provided'}), 400
    
    file = request.files['image']
    temp_path = f"temp_{int(time.time())}.jpg"
    file.save(temp_path)
    
    try:
        # Use the CNN classifier from ai_integration
        level, people, confidence = ai_integration.classifier.predict(temp_path)
        
        # Map level to display
        if level == 'low':
            recommendation = "Normal boarding expected"
        elif level == 'medium':
            recommendation = "Moderate crowds, arrive 15 minutes early"
        elif level == 'high':
            recommendation = "Heavy crowds, expect delays"
        else:
            recommendation = "Extremely crowded, avoid if possible"
        
        result = {
            'crowd_level': level.capitalize(),
            'predicted_crowd': people,
            'confidence': confidence,
            'recommendation': recommendation,
            'timestamp': datetime.now().isoformat()
        }
        return jsonify(result)
        
    except Exception as e:
        print(f"Error in CNN image prediction: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)
# ============================================
# START APPLICATION
# ============================================

if __name__ == '__main__':
    init_db()
    socketio.run(app, host='0.0.0.0', port=5001, debug=True)