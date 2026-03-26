import time

import cv2

import smart_traffic.state as state

from ..config import CAR_TARGET_CLASSES
from ..models import car_model
from ..services.decode import decode_image
from ..state import (
    frame_condition_car,
    infer_lock,
    sys_state,
)


def process_car_data(obfuscated_bytes):
    if not sys_state["detection"]:
        return {
            "cars": sys_state["cars"],
            "persons": sys_state["persons"],
            "wheelchairs": sys_state["wheelchairs"],
            "command": "KEEP"
        }

    image = decode_image(obfuscated_bytes)

    with infer_lock:
        results = car_model.predict(
            source=image,
            imgsz=800,
            classes=CAR_TARGET_CLASSES,
            save=False,
            conf=0.25
        )

    annotated_img = results[0].plot()

    ret, buffer = cv2.imencode('.jpg', annotated_img)
    if ret:
        with frame_condition_car:
            state.latest_frame_car = buffer.tobytes()
            state.latest_frame_ts_car = time.time()
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
