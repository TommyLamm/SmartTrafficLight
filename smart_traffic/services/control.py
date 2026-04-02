import time

import logic

from ..state import sys_state

# ── Emergency phase durations ─────────────────────────────────────────────
# Phase 1: YELLOW_WARNING — all signals show amber so pedestrians and drivers
#          know something is about to change. Duration: 3 seconds.
# Phase 2: ALL_RED_CLEAR  — every direction is red, giving anyone already in
#          the crossing a safe 5 seconds to finish clearing.
# Phase 3: EMERGENCY_RED  — sustained all-red until the RFID trigger is reset.
_EMERGENCY_YELLOW_DURATION = 3.0   # seconds
_EMERGENCY_ALL_RED_DURATION = 5.0  # seconds


def trigger_emergency_vehicle():
    """
    Call this when the RFID reader detects an emergency vehicle.
    Starts the 3-phase safety sequence if the feature is enabled.
    Has no effect if emergency_priority_active is False.
    """
    if not sys_state["emergency_priority_active"]:
        return
    now = time.time()
    sys_state["emergency_phase"] = "YELLOW_WARNING"
    sys_state["emergency_phase_until"] = now + _EMERGENCY_YELLOW_DURATION
    sys_state["command"] = "YELLOW_ALL"
    sys_state["light_state"] = "EMERGENCY_YELLOW"
    print("[emergency] Phase 1/3 — YELLOW_WARNING started")


def _tick_emergency_phase():
    """
    Advance the emergency state machine one tick.
    Returns True if emergency is still active (caller should skip normal logic).
    Returns False if no emergency is active.
    """
    phase = sys_state["emergency_phase"]
    if phase is None:
        return False

    now = time.time()
    if now < sys_state["emergency_phase_until"]:
        # Still in current phase — hold the current command
        return True

    # Current phase has elapsed — advance to next
    if phase == "YELLOW_WARNING":
        sys_state["emergency_phase"] = "ALL_RED_CLEAR"
        sys_state["emergency_phase_until"] = now + _EMERGENCY_ALL_RED_DURATION
        sys_state["command"] = "ALL_RED"
        sys_state["light_state"] = "EMERGENCY_ALL_RED"
        print("[emergency] Phase 2/3 — ALL_RED_CLEAR started")
        return True

    if phase == "ALL_RED_CLEAR":
        sys_state["emergency_phase"] = "EMERGENCY_RED"
        sys_state["emergency_phase_until"] = 0.0  # hold indefinitely
        sys_state["command"] = "EMERGENCY_RED"
        sys_state["light_state"] = "EMERGENCY_RED"
        print("[emergency] Phase 3/3 — EMERGENCY_RED holding")
        return True

    if phase == "EMERGENCY_RED":
        # Holding — keep command until manually cleared
        sys_state["command"] = "EMERGENCY_RED"
        return True

    return False


def clear_emergency():
    """Reset emergency state machine so normal AUTO logic resumes."""
    sys_state["emergency_phase"] = None
    sys_state["emergency_phase_until"] = 0.0
    sys_state["light_state"] = "UNKNOWN"
    sys_state["command"] = "KEEP"
    print("[emergency] Cleared — resuming normal operation")


def apply_person_control_logic(person_count, wheelchair_count):
    if sys_state["mode"] == "AUTO":
        # Emergency state machine takes highest priority
        if _tick_emergency_phase():
            return  # hold current emergency command, skip normal logic

        cmd, new_state = logic.decide_light(
            person_count,
            sys_state["cars"],
            wheelchair_count,
            sys_state["light_state"],
            emergency_active=sys_state["emergency_priority_active"],
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