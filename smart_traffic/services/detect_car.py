import time
from statistics import fmean

import cv2

import smart_traffic.state as state

from ..config import (
    CAR_LANE_REGION_COUNT,
    CAR_TARGET_CLASSES,
    TIDAL_BIAS_MARGIN,
)
from ..models import car_model
from ..services.control import tick_emergency_phase
from ..services.decode import decode_image
from ..state import (
    frame_condition_car,
    infer_lock,
    lane_sample_window,
    sys_state,
)


def _boundary_x(top_ratio, bottom_ratio, y, image_width, image_height):
    if image_width <= 0 or image_height <= 0:
        return 0.0
    y_ratio = float(y) / float(image_height)
    if y_ratio < 0.0:
        y_ratio = 0.0
    elif y_ratio > 1.0:
        y_ratio = 1.0
    x_ratio = top_ratio + (bottom_ratio - top_ratio) * y_ratio
    return x_ratio * image_width


def _bucket_lane(bottom_center_x, bottom_center_y, image_width, image_height, boundaries):
    if image_width <= 0 or image_height <= 0:
        return CAR_LANE_REGION_COUNT // 2
    boundary1_x = _boundary_x(
        boundaries["boundary1_top"],
        boundaries["boundary1_bottom"],
        bottom_center_y,
        image_width,
        image_height,
    )
    boundary2_x = _boundary_x(
        boundaries["boundary2_top"],
        boundaries["boundary2_bottom"],
        bottom_center_y,
        image_width,
        image_height,
    )
    if bottom_center_x < boundary1_x:
        return 0
    if bottom_center_x < boundary2_x:
        return 1
    return 2


def _compute_tidal_direction():
    if not lane_sample_window:
        return "BALANCED"

    left_avg = fmean(sample[0] for sample in lane_sample_window)
    right_avg = fmean(sample[-1] for sample in lane_sample_window)
    if left_avg - right_avg >= TIDAL_BIAS_MARGIN:
        return "LEFT_BIAS"
    if right_avg - left_avg >= TIDAL_BIAS_MARGIN:
        return "RIGHT_BIAS"
    return "BALANCED"


def process_car_data(obfuscated_bytes):
    tick_emergency_phase()

    if not sys_state["detection"]:
        return {
            "cars": sys_state["cars"],
            "persons": sys_state["persons"],
            "wheelchairs": sys_state["wheelchairs"],
            "command": sys_state["command"],
            "cars_total": sys_state["cars"],
            "lane_counts": sys_state["lane_counts"],
            "tidal_direction": sys_state["tidal_direction"],
            "sample_window": len(lane_sample_window)
        }

    image = decode_image(obfuscated_bytes)
    image_width, image_height = image.size
    boundaries = state.get_lane_boundaries()

    with infer_lock:
        results = car_model.predict(
            source=image,
            imgsz=800,
            classes=CAR_TARGET_CLASSES,
            save=False,
            conf=0.25,
            agnostic_nms=True
        )

    annotated_img = results[0].plot()

    ret, buffer = cv2.imencode('.jpg', annotated_img)
    if ret:
        with frame_condition_car:
            state.latest_frame_car = buffer.tobytes()
            state.latest_frame_ts_car = time.time()
            frame_condition_car.notify_all()

    v_count = 0
    lane_counts = [0] * CAR_LANE_REGION_COUNT
    for r in results:
        if r.boxes is None:
            continue
        v_count += int(len(r.boxes.cls))
        boxes = r.boxes.xyxy.cpu().numpy()
        for x1, _, x2, y2 in boxes:
            bottom_center_x = (float(x1) + float(x2)) / 2.0
            bottom_center_y = float(y2)
            lane_index = _bucket_lane(bottom_center_x, bottom_center_y, image_width, image_height, boundaries)
            lane_counts[lane_index] += 1

    sys_state["cars"] = v_count
    lane_sample_window.append(lane_counts)
    tidal_direction = _compute_tidal_direction()
    sys_state["lane_counts"] = lane_counts
    sys_state["tidal_direction"] = tidal_direction

    return {
        "cars": sys_state["cars"],
        "persons": sys_state["persons"],
        "wheelchairs": sys_state["wheelchairs"],
        "command": sys_state["command"],
        "cars_total": sys_state["cars"],
        "lane_counts": lane_counts,
        "tidal_direction": tidal_direction,
        "sample_window": len(lane_sample_window),
        "lane_boundaries": boundaries,
        "frame_size": {"width": image_width, "height": image_height}
    }
