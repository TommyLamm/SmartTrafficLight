import io
import cv2
import threading
import numpy as np
from PIL import Image
from ultralytics import YOLO
import logic  

print("Loading YOLO Engine...")
model = YOLO('yolov8n.pt')
target_classes =[0, 2, 3, 5, 7] # 0:person, 2:car, 3:motorcycle, 5:bus, 7:truck
XOR_KEY = b"MyIoTKey2026"

latest_frame = None
frame_condition = threading.Condition()
infer_lock = threading.Lock()

# Central System State
sys_state = {
    "persons": 0,
    "cars": 0,
    "command": "KEEP",
    "light_state": "UNKNOWN",
    "mode": "AUTO",          # Can be 'AUTO' or 'MANUAL'
    "manual_override": None, # Holds one-time commands like 'CAR_GREEN'
    "detection": True        # Detection on/off toggle
}

def process_traffic_data(obfuscated_bytes):
    global latest_frame

    # Detection disabled — return immediately without running YOLO
    if not sys_state["detection"]:
        return {
            "cars": sys_state["cars"],
            "persons": sys_state["persons"],
            "command": "KEEP"
        }

    # 1. Decrypt
    input_arr = np.frombuffer(obfuscated_bytes, dtype=np.uint8)
    key_arr = np.resize(np.frombuffer(XOR_KEY, dtype=np.uint8), len(input_arr))
    decrypted_bytes = np.bitwise_xor(input_arr, key_arr).tobytes()
    image = Image.open(io.BytesIO(decrypted_bytes))

    # 2. YOLO Inference
    with infer_lock:
        results = model.predict(source=image, imgsz=800, classes=target_classes, save=False, conf=0.25)

    # 3. Stream Buffer
    annotated_img = results[0].plot()
    ret, buffer = cv2.imencode('.jpg', annotated_img)
    if ret:
        with frame_condition:
            latest_frame = buffer.tobytes()
            frame_condition.notify_all()

    # 4. Counting
    p_count = 0
    v_count = 0
    for r in results:
        detected_classes = r.boxes.cls.cpu().numpy()
        for cls_id in detected_classes:
            if cls_id == 0: p_count += 1
            else: v_count += 1

    sys_state["persons"] = p_count
    sys_state["cars"] = v_count

    # 5. Determine Command based on Mode
    if sys_state["mode"] == "AUTO":
        cmd, new_state = logic.decide_light(p_count, v_count, sys_state["light_state"])
        sys_state["command"] = cmd
        sys_state["light_state"] = new_state
    else:
        # MANUAL MODE overrides the logic
        if sys_state["manual_override"]:
            sys_state["command"] = sys_state["manual_override"]
            sys_state["light_state"] = "MANUAL_OVERRIDE"
            sys_state["manual_override"] = None # Reset after firing once
        else:
            sys_state["command"] = "KEEP" # Send heartbeat

    return {
        "cars": sys_state["cars"],
        "persons": sys_state["persons"],
        "command": sys_state["command"]
    }
