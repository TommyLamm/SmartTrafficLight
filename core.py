import io
import cv2
import threading
import numpy as np
from PIL import Image
from ultralytics import YOLO
import logic  

print("Loading YOLO Engine...")
model = YOLO('yolov8n.pt')
target_classes = [0, 2, 3, 5, 7]

# ✅ 新增：載入輪椅偵測模型
print("Loading Wheelchair Detection Model...")
wheelchair_model = YOLO('wheelchair_model/weights/best.pt')  # 你的模型路徑

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

def process_traffic_data(obfuscated_bytes):
    global latest_frame

    if not sys_state["detection"]:
        return {
            "cars": sys_state["cars"],
            "persons": sys_state["persons"],
            "wheelchairs": sys_state["wheelchairs"],  # ✅ 新增
            "command": "KEEP"
        }

    # 1. 解密
    input_arr = np.frombuffer(obfuscated_bytes, dtype=np.uint8)
    key_arr = np.resize(np.frombuffer(XOR_KEY, dtype=np.uint8), len(input_arr))
    decrypted_bytes = np.bitwise_xor(input_arr, key_arr).tobytes()
    image = Image.open(io.BytesIO(decrypted_bytes))

    with infer_lock:
        # 原有車輛/行人模型
        results = model.predict(source=image, imgsz=800, classes=target_classes, save=False, conf=0.25)
        # ✅ 新增：輪椅模型（對同一張圖跑第二次推理）
        wheelchair_results = wheelchair_model.predict(source=image, imgsz=640, save=False, conf=0.45)

    # 串流畫面（疊加輪椅偵測框）
    annotated_img = results[0].plot()
    # ✅ 將輪椅偵測框也疊加到畫面上
    for r in wheelchair_results:
        for box in r.boxes:
            x1, y1, x2, y2 = map(int, box.xyxy[0])
            cv2.rectangle(annotated_img, (x1, y1), (x2, y2), (255, 165, 0), 2)
            cv2.putText(annotated_img, f"Wheelchair {float(box.conf[0]):.2f}",
                        (x1, y1 - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 165, 0), 2)

    ret, buffer = cv2.imencode('.jpg', annotated_img)
    if ret:
        with frame_condition:
            latest_frame = buffer.tobytes()
            frame_condition.notify_all()

    # 計數
    p_count, v_count, w_count = 0, 0, 0
    for r in results:
        for cls_id in r.boxes.cls.cpu().numpy():
            if cls_id == 0: p_count += 1
            else: v_count += 1

    # ✅ 輪椅計數
    for r in wheelchair_results:
        w_count += len(r.boxes)

    sys_state["persons"] = p_count
    sys_state["cars"] = v_count
    sys_state["wheelchairs"] = w_count  # ✅ 新增

    if sys_state["mode"] == "AUTO":
        # ✅ 將 w_count 傳入決策函式
        cmd, new_state = logic.decide_light(p_count, v_count, w_count, sys_state["light_state"])
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
        "wheelchairs": sys_state["wheelchairs"],  # ✅ 新增
        "command": sys_state["command"]
    }
