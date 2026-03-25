import io
import cv2
import threading
import numpy as np
from PIL import Image
from ultralytics import YOLO
import logic  

print("Loading YOLO Engine...")
model = YOLO('person_wheelchair_personWheelchair.pt')

XOR_KEY = b"MyIoTKey2026"

latest_frame = None
frame_condition = threading.Condition()
infer_lock = threading.Lock()

sys_state = {
    "persons": 0,
    "cars": 0,
    "wheelchairs": 0,      # ✅ 新增
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

def process_traffic_data(obfuscated_bytes):
    global latest_frame

    if not sys_state["detection"]:
        return {
            "cars": sys_state["cars"],
            "persons": sys_state["persons"],
            "wheelchairs": sys_state["wheelchairs"],
            "command": "KEEP"
        }

    # 1. 解密
    input_arr = np.frombuffer(obfuscated_bytes, dtype=np.uint8)
    key_arr = np.resize(np.frombuffer(XOR_KEY, dtype=np.uint8), len(input_arr))
    decrypted_bytes = np.bitwise_xor(input_arr, key_arr).tobytes()
    image = Image.open(io.BytesIO(decrypted_bytes))

    with infer_lock:
        results = model.predict(source=image, imgsz=640, save=False, conf=0.25)

    # 串流畫面（顯示三類標註）
    annotated_img = results[0].plot()

    ret, buffer = cv2.imencode('.jpg', annotated_img)
    if ret:
        with frame_condition:
            latest_frame = buffer.tobytes()
            frame_condition.notify_all()

    # 計數
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

    if sys_state["mode"] == "AUTO":
        # cars 由另一個攝像頭流程維護；此流程只提供行人/輪椅資訊
        cmd, new_state = logic.decide_light(p_count, sys_state["cars"], w_count, sys_state["light_state"])
        sys_state["command"] = cmd
        sys_state["light_state"] = new_state
    else:
        if sys_state["manual_override"]:
            sys_state["command"] = sys_state["manual_override"]
            sys_state["light_state"] = "MANUAL_OVERRIDE"
            sys_state["manual_override"] = None
        else:
            sys_state["command"] = "KEEP"

    return {
        "cars": sys_state["cars"],
        "persons": sys_state["persons"],
        "wheelchairs": sys_state["wheelchairs"],
        "command": sys_state["command"]
    }
