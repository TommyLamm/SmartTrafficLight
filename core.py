import io
import cv2
import threading
import time
import numpy as np
from PIL import Image
from ultralytics import YOLO
import logic  

print("Loading Car Detection Model...")
car_model = YOLO('yolov8n.pt')
car_target_classes = [2, 3, 5, 7]

print("Loading Person/Wheelchair Detection Model...")
person_model = YOLO('person_wheelchair_personWheelchair.pt')

XOR_KEY = b"MyIoTKey2026"

latest_frame = None
latest_frame_person = None
latest_frame_car = None
latest_frame_ts_person = 0.0
latest_frame_ts_car = 0.0

STREAM_ONLINE_TTL_SEC = 5.0

frame_condition = threading.Condition()  # Backward-compatible alias for person stream
frame_condition_person = frame_condition
frame_condition_car = threading.Condition()
infer_lock = threading.Lock()

sys_state = {
    "persons": 0,
    "cars": 0,
    "wheelchairs": 0,
    "command": "KEEP",
    "light_state": "UNKNOWN",
    "mode": "AUTO",
    "manual_override": None,
    "detection": True
}

def _class_name(names, cls_id):
    cls_id = int(cls_id)
    if isinstance(names, dict):
        return str(names.get(cls_id, cls_id))
    if isinstance(names, (list, tuple)) and 0 <= cls_id < len(names):
        return str(names[cls_id])
    return str(cls_id)

def _normalize_label(label):
    return "".join(ch for ch in str(label).lower() if ch.isalnum())

def _decode_image(obfuscated_bytes):
    input_arr = np.frombuffer(obfuscated_bytes, dtype=np.uint8)
    key_arr = np.resize(np.frombuffer(XOR_KEY, dtype=np.uint8), len(input_arr))
    decrypted_bytes = np.bitwise_xor(input_arr, key_arr).tobytes()
    return Image.open(io.BytesIO(decrypted_bytes))

def _is_stream_online(last_frame_ts, ttl_sec=STREAM_ONLINE_TTL_SEC):
    if last_frame_ts <= 0:
        return False
    return (time.time() - last_frame_ts) <= ttl_sec

def is_person_stream_online(ttl_sec=STREAM_ONLINE_TTL_SEC):
    return _is_stream_online(latest_frame_ts_person, ttl_sec)

def is_car_stream_online(ttl_sec=STREAM_ONLINE_TTL_SEC):
    return _is_stream_online(latest_frame_ts_car, ttl_sec)

def _apply_person_control_logic(person_count, wheelchair_count):
    if sys_state["mode"] == "AUTO":
        cmd, new_state = logic.decide_light(
            person_count,
            sys_state["cars"],
            wheelchair_count,
            sys_state["light_state"]
        )
        sys_state["command"] = cmd
        sys_state["light_state"] = new_state
    else:
        if sys_state["manual_override"]:
            sys_state["command"] = sys_state["manual_override"]
            sys_state["light_state"] = "MANUAL_OVERRIDE"
            sys_state["manual_override"] = None
        else:
            sys_state["command"] = "KEEP"

def process_car_data(obfuscated_bytes):
    global latest_frame_car, latest_frame_ts_car

    if not sys_state["detection"]:
        return {
            "cars": sys_state["cars"],
            "persons": sys_state["persons"],
            "wheelchairs": sys_state["wheelchairs"],
            "command": "KEEP"
        }

    image = _decode_image(obfuscated_bytes)

    with infer_lock:
        results = car_model.predict(
            source=image,
            imgsz=800,
            classes=car_target_classes,
            save=False,
            conf=0.25
        )

    annotated_img = results[0].plot()

    ret, buffer = cv2.imencode('.jpg', annotated_img)
    if ret:
        with frame_condition_car:
            latest_frame_car = buffer.tobytes()
            latest_frame_ts_car = time.time()
            frame_condition_car.notify_all()

    v_count = 0
    for r in results:
        if r.boxes is None:
            continue
        v_count += int(len(r.boxes.cls))

    sys_state["cars"] = v_count

    return {
        "cars": sys_state["cars"],
        "persons": sys_state["persons"],
        "wheelchairs": sys_state["wheelchairs"],
        "command": "KEEP"
    }

def process_person_data(obfuscated_bytes):
    global latest_frame, latest_frame_person, latest_frame_ts_person

    if not sys_state["detection"]:
        return {
            "cars": sys_state["cars"],
            "persons": sys_state["persons"],
            "wheelchairs": sys_state["wheelchairs"],
            "command": "KEEP"
        }

    image = _decode_image(obfuscated_bytes)

    with infer_lock:
        results = person_model.predict(source=image, imgsz=640, save=False, conf=0.25)

    annotated_img = results[0].plot()

    ret, buffer = cv2.imencode('.jpg', annotated_img)
    if ret:
        with frame_condition_person:
            latest_frame_person = buffer.tobytes()
            latest_frame = latest_frame_person  # Backward-compatible person stream frame
            latest_frame_ts_person = time.time()
            frame_condition_person.notify_all()

    p_count, w_count = 0, 0
    for r in results:
        if r.boxes is None:
            continue
        for cls_id in r.boxes.cls.cpu().numpy().astype(int):
            label = _normalize_label(_class_name(r.names, cls_id))
            if label == "person":
                p_count += 1
            elif label in {"peoplewheelchair", "personwheelchair", "peopleinwheelchair", "personinwheelchair"}:
                p_count += 1
                w_count += 1
            # 空輪椅（wheelchair）不計入輪椅優先

    sys_state["persons"] = p_count
    sys_state["wheelchairs"] = w_count
    _apply_person_control_logic(p_count, w_count)

    return {
        "cars": sys_state["cars"],
        "persons": sys_state["persons"],
        "wheelchairs": sys_state["wheelchairs"],
        "command": sys_state["command"]
    }

def process_traffic_data(obfuscated_bytes):
    # Backward-compatible alias: legacy endpoint now maps to person/wheelchair flow.
    return process_person_data(obfuscated_bytes)

def process_legacy_detect_all(obfuscated_bytes):
    return process_person_data(obfuscated_bytes)

def get_state():
    return {
        "cars": sys_state["cars"],
        "persons": sys_state["persons"],
        "wheelchairs": sys_state["wheelchairs"],
        "command": sys_state["command"]
    }
