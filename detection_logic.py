import cv2
import time
import paho.mqtt.client as mqtt
from ultralytics import YOLO

PROJECT_ID = "railway_secure_2026_xyz"
TRACK_TOPIC = f"{PROJECT_ID}/track/status"

# FIX: Update to VERSION2 and add callback functions
def on_connect(client, userdata, flags, reason_code, properties=None):
    if reason_code == 0:
        print("✅ Connected to MQTT broker successfully")
    else:
        print(f"❌ Failed to connect with code: {reason_code}")

def on_publish(client, userdata, mid, reason_code=None, properties=None):
    # Optional: Uncomment to see publish confirmations
    # print(f"📤 Message published with ID: {mid}")
    pass

# Create client with VERSION2
client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="Trackside_Sensor_01")
client.on_connect = on_connect
client.on_publish = on_publish

# Connect to broker
client.connect("broker.hivemq.com", 1883, 60)
client.loop_start()

model = YOLO("yolov8n.pt")

# Replace with your mobile camera IP
# Format: "http://<phone_ip>:<port>/video" for IP Webcam
# Example: "http://192.168.1.100:8080/video"
MOBILE_CAMERA_URL = "http://192.168.122.124:8080/video"  # CHANGE THIS

cap = cv2.VideoCapture(MOBILE_CAMERA_URL)

# Check if camera opened successfully
if not cap.isOpened():
    print(f"❌ Could not open mobile camera at {MOBILE_CAMERA_URL}")
    print("   Make sure:")
    print("   1. Your phone and computer are on the same WiFi")
    print("   2. IP Webcam app is running on your phone")
    print("   3. You've entered the correct IP address")
    exit()

track_is_blocked = False
detection_start_time = None
clearance_start_time = None

print(f"📷 Server 1: Monitoring Track A via Mobile Camera (3s Detect / 120s Clear)")

while cap.isOpened():
    success, frame = cap.read()
    if not success:
        print("⚠️ Frame read failed. Retrying...")
        time.sleep(1)
        continue

    results = model(frame, conf=0.3, verbose=False)
    boxes = results[0].boxes
    obstacle_classes = [0, 67]  # 0=person, 67=cell phone (common on tracks)
    found_obstacle = any(int(box.cls[0]) in obstacle_classes for box in boxes)

    if found_obstacle:
        clearance_start_time = None
        if not track_is_blocked:
            if detection_start_time is None:
                detection_start_time = time.time()
            elapsed = time.time() - detection_start_time
            if elapsed >= 3:
                print("🚨 OBSTACLE CONFIRMED (3s). Alerting Hub...")
                client.publish(TRACK_TOPIC, "OBSTACLE|A")
                track_is_blocked = True
            else:
                cv2.putText(frame, f"CONFIRMING: {int(3-elapsed)}s", (50,50), 0, 0.8, (0,165,255), 2)
    else:
        detection_start_time = None
        if track_is_blocked:
            if clearance_start_time is None:
                clearance_start_time = time.time()
            elapsed = time.time() - clearance_start_time
            remaining = 120 - elapsed
            if remaining <= 0:
                print("✅ TRACK CLEAR (120s). Alerting Hub...")
                client.publish(TRACK_TOPIC, "CLEAR|A")
                track_is_blocked = False
            else:
                cv2.putText(frame, f"CLEARANCE: {int(remaining)}s", (50,50), 0, 0.8, (0,255,0), 2)

    cv2.imshow("SERVER 1: TRACKSIDE AI - Mobile Camera", frame)
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()
client.loop_stop()
client.disconnect()