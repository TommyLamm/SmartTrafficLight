import time

import logic

from ..state import sys_state

_EMERGENCY_YELLOW_DURATION = 3.0
_EMERGENCY_ALL_RED_DURATION = 5.0
_EMERGENCY_HOLD_DURATION = 15.0


def trigger_emergency_vehicle():
    if not sys_state["emergency_priority_active"]:
        return
    now = time.time()
    sys_state["emergency_phase"] = "YELLOW_WARNING"
    sys_state["emergency_phase_until"] = now + _EMERGENCY_YELLOW_DURATION
    sys_state["command"] = "EMERGENCY_YELLOW"
    sys_state["light_state"] = "EMERGENCY_YELLOW"


def clear_emergency():
    sys_state["emergency_phase"] = None
    sys_state["emergency_phase_until"] = 0.0
    if sys_state["light_state"] in {"EMERGENCY_YELLOW", "EMERGENCY_ALL_RED", "EMERGENCY_RED"}:
        sys_state["light_state"] = "UNKNOWN"
    if sys_state["command"] in {"EMERGENCY_YELLOW", "EMERGENCY_ALL_RED", "EMERGENCY_RED"}:
        sys_state["command"] = "KEEP"


def tick_emergency_phase():
    phase = sys_state["emergency_phase"]
    if phase is None:
        return False

    now = time.time()
    phase_until = float(sys_state.get("emergency_phase_until", 0.0) or 0.0)
    if phase_until > 0.0 and now < phase_until:
        return True

    if phase == "YELLOW_WARNING":
        sys_state["emergency_phase"] = "ALL_RED_CLEAR"
        sys_state["emergency_phase_until"] = now + _EMERGENCY_ALL_RED_DURATION
        sys_state["command"] = "EMERGENCY_ALL_RED"
        sys_state["light_state"] = "EMERGENCY_ALL_RED"
        return True

    if phase == "ALL_RED_CLEAR":
        sys_state["emergency_phase"] = "EMERGENCY_RED"
        sys_state["emergency_phase_until"] = now + _EMERGENCY_HOLD_DURATION
        sys_state["command"] = "EMERGENCY_RED"
        sys_state["light_state"] = "EMERGENCY_RED"
        return True

    if phase == "EMERGENCY_RED":
        if phase_until > 0.0 and now >= phase_until:
            clear_emergency()
            return False
        sys_state["command"] = "EMERGENCY_RED"
        sys_state["light_state"] = "EMERGENCY_RED"
        return True

    clear_emergency()
    return False


def apply_person_control_logic(person_count, wheelchair_count):
    emergency_active = tick_emergency_phase()
    if emergency_active:
        return

    if sys_state["mode"] == "AUTO":
        cmd, new_state = logic.decide_light(
            person_count,
            sys_state["cars"],
            wheelchair_count,
            sys_state["light_state"],
            emergency_active=emergency_active,
            wheelchair_priority_active=sys_state["wheelchair_priority_active"],
        )
        sys_state["command"] = cmd
        sys_state["light_state"] = new_state
    else:
        if sys_state["manual_override"]:
            cmd = sys_state["manual_override"]
            sys_state["command"] = cmd
            sys_state["light_state"] = "MANUAL_OVERRIDE"

            if cmd == "CAR_GREEN":
                sys_state["last_manual_label"] = "Car Green"
            elif cmd == "PED_GREEN_20":
                sys_state["last_manual_label"] = "Ped Green (20s)"
            else:
                sys_state["last_manual_label"] = cmd

            sys_state["manual_override"] = None
        else:
            sys_state["command"] = "KEEP"
