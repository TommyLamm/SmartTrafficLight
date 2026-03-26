import time

import cv2

import smart_traffic.state as state

from ..models import person_model
from ..services.control import apply_person_control_logic
from ..services.decode import decode_image
from ..state import frame_condition_person, infer_lock, sys_state


def class_name(names, cls_id):
    cls_id = int(cls_id)
    if isinstance(names, dict):
        return str(names.get(cls_id, cls_id))
    if isinstance(names, (list, tuple)) and 0 <= cls_id < len(names):
        return str(names[cls_id])
    return str(cls_id)


def normalize_label(label):
    return "".join(ch for ch in str(label).lower() if ch.isalnum())


def process_person_data(obfuscated_bytes):
    if not sys_state["detection"]:
        return {
            "cars": sys_state["cars"],
            "persons": sys_state["persons"],
            "wheelchairs": sys_state["wheelchairs"],
            "command": "KEEP"
        }

    image = decode_image(obfuscated_bytes)

    with infer_lock:
        results = person_model.predict(source=image, imgsz=640, save=False, conf=0.25)

    annotated_img = results[0].plot()

    ret, buffer = cv2.imencode('.jpg', annotated_img)
    if ret:
        with frame_condition_person:
            state.latest_frame_person = buffer.tobytes()
            state.latest_frame = state.latest_frame_person  # Backward-compatible person stream frame
            state.latest_frame_ts_person = time.time()
            frame_condition_person.notify_all()

    p_count, w_count = 0, 0
    for r in results:
        if r.boxes is None:
            continue
        for cls_id in r.boxes.cls.cpu().numpy().astype(int):
            label = normalize_label(class_name(r.names, cls_id))
            if label == "person":
                p_count += 1
            elif label in {"peoplewheelchair", "personwheelchair", "peopleinwheelchair", "personinwheelchair"}:
                p_count += 1
                w_count += 1
            # 空輪椅（wheelchair）不計入輪椅優先

    sys_state["persons"] = p_count
    sys_state["wheelchairs"] = w_count
    apply_person_control_logic(p_count, w_count)

    return {
        "cars": sys_state["cars"],
        "persons": sys_state["persons"],
        "wheelchairs": sys_state["wheelchairs"],
        "command": sys_state["command"]
    }


def process_legacy_detect_all(obfuscated_bytes):
    return process_person_data(obfuscated_bytes)
