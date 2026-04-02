import logic

import smart_traffic.models as models
import smart_traffic.state as state
from smart_traffic.config import STREAM_ONLINE_TTL_SEC, XOR_KEY
from smart_traffic.services.control import apply_person_control_logic as _apply_person_control_logic
from smart_traffic.services.decode import decode_image as _decode_image
from smart_traffic.services.detect_car import process_car_data
from smart_traffic.services.detect_person import process_legacy_detect_all, process_person_data

car_model = models.car_model
person_model = models.person_model

frame_condition = state.frame_condition
frame_condition_person = state.frame_condition_person
frame_condition_car = state.frame_condition_car
infer_lock = state.infer_lock
sys_state = state.sys_state

is_person_stream_online = state.is_person_stream_online
is_car_stream_online = state.is_car_stream_online


def process_traffic_data(obfuscated_bytes):
    return process_person_data(obfuscated_bytes)


def get_state():
    return {
        "cars": sys_state["cars"],
        "persons": sys_state["persons"],
        "wheelchairs": sys_state["wheelchairs"],
        "command": sys_state["command"]
    }


def __getattr__(name):
    if hasattr(state, name):
        return getattr(state, name)
    raise AttributeError(f"module 'core' has no attribute '{name}'")
