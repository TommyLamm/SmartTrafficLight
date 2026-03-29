import threading
import time
from collections import deque

from .config import CAR_LANE_REGION_COUNT, STREAM_ONLINE_TTL_SEC, TIDAL_SAMPLE_WINDOW


latest_frame = None
latest_frame_person = None
latest_frame_car = None
latest_frame_ts_person = 0.0
latest_frame_ts_car = 0.0

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
    "last_manual_label": None,
    "detection": True,
    "lane_counts": [0] * CAR_LANE_REGION_COUNT,
    "tidal_direction": "BALANCED"
}

lane_sample_window = deque(maxlen=TIDAL_SAMPLE_WINDOW)


def is_stream_online(last_frame_ts, ttl_sec=STREAM_ONLINE_TTL_SEC):
    if last_frame_ts <= 0:
        return False
    return (time.time() - last_frame_ts) <= ttl_sec


def is_person_stream_online(ttl_sec=STREAM_ONLINE_TTL_SEC):
    return is_stream_online(latest_frame_ts_person, ttl_sec)


def is_car_stream_online(ttl_sec=STREAM_ONLINE_TTL_SEC):
    return is_stream_online(latest_frame_ts_car, ttl_sec)
