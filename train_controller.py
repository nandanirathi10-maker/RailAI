import paho.mqtt.client as mqtt
import time
import threading

PROJECT_ID = "railway_secure_2026_xyz"
HUB_IN = f"{PROJECT_ID}/hub/to_train"
HUB_OUT = f"{PROJECT_ID}/train/to_hub"
IDENTITY_TOPIC = f"{PROJECT_ID}/train/identity"

# Train identity – must match database
TRAIN_ID = input("Enter Train ID: ").strip()
TRAIN_NAME = input("Enter Train Name: ").strip()

print(f"🚆 Train Controller for {TRAIN_NAME} (ID {TRAIN_ID})")

train_speed = 0
driver_responded = False
current_mode = "STARTUP"
registered = False

def auto_brake_timer():
    global train_speed, current_mode, driver_responded
    time.sleep(10)
    if not driver_responded and train_speed > 0:
        print("\n🛑 [AUTO-BRAKE] No response. Stopping Train!")
        train_speed = 0
        current_mode = "STOPPED"
        client.publish(HUB_OUT, f"BRAKES_APPLIED_AUTO|{TRAIN_ID}")

def on_message(client, userdata, msg):
    global current_mode, driver_responded, registered
    payload = msg.payload.decode()
    print(f"📨 Received: {payload}")

    if msg.topic == HUB_IN:
        if payload.startswith("REGISTERED|"):
            _, tid = payload.split('|')
            if tid == TRAIN_ID:
                registered = True
                print("✅ Registered with hub")
        elif "OBSTACLE_DETECTED" in payload and registered:
            print("\n🚨 HUB ALERT: Obstacle! Brakes Required.")
            current_mode = "WAITING_FOR_BRAKE"
            driver_responded = False
            threading.Thread(target=auto_brake_timer, daemon=True).start()
        elif "TRACK_CLEAR" in payload and registered:
            print("\n✅ HUB ALERT: Track is Clear. Manual Resume Required.")
            current_mode = "WAITING_FOR_RESUME"

client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"Train_Controller_{TRAIN_ID}")
client.on_message = on_message
client.connect("broker.hivemq.com", 1883, 60)
client.subscribe(HUB_IN)
client.loop_start()

# Send identity
client.publish(IDENTITY_TOPIC, f"{TRAIN_ID}|{TRAIN_NAME}")
print("Sent registration request...")

try:
    while True:
        if current_mode == "STARTUP" and registered:
            cmd = input(f"👉 {TRAIN_NAME} at station. Press '0' to start: ")
            if cmd == '0':
                train_speed = 100
                current_mode = "RUNNING"
                client.publish(HUB_OUT, f"TRAIN_STARTED_AT_STATION|{TRAIN_ID}")
                print(f"🚀 {TRAIN_NAME} moving at 100 km/h")

        elif current_mode == "WAITING_FOR_BRAKE":
            cmd = input(f"👉 {TRAIN_NAME} EMERGENCY: Press '1' to BRAKE: ")
            if cmd == '1':
                train_speed = 0
                driver_responded = True
                current_mode = "STOPPED"
                client.publish(HUB_OUT, f"BRAKES_APPLIED_BY_DRIVER|{TRAIN_ID}")
                print("🛑 Stopped.")

        elif current_mode == "WAITING_FOR_RESUME":
            cmd = input(f"👉 {TRAIN_NAME} CLEAR: Press '0' to RESUME: ")
            if cmd == '0':
                train_speed = 100
                current_mode = "RUNNING"
                client.publish(HUB_OUT, f"TRAIN_RESUMED_BY_DRIVER|{TRAIN_ID}")
                print(f"🚀 {TRAIN_NAME} resuming at 100 km/h")

        time.sleep(0.1)

except KeyboardInterrupt:
    client.disconnect()