import time

import smart_traffic.state as state

from smart_traffic.services import control


def test_trigger_emergency_sets_yellow_phase():
    state.sys_state["emergency_priority_active"] = True

    control.trigger_emergency_vehicle()

    assert state.sys_state["emergency_phase"] == "YELLOW_WARNING"
    assert state.sys_state["command"] == "EMERGENCY_YELLOW"
    assert state.sys_state["light_state"] == "EMERGENCY_YELLOW"
    assert state.sys_state["emergency_phase_until"] > 0.0


def test_tick_emergency_phase_progresses_through_all_stages():
    state.sys_state["emergency_phase"] = "YELLOW_WARNING"
    state.sys_state["emergency_phase_until"] = 0.0
    state.sys_state["command"] = "EMERGENCY_YELLOW"
    state.sys_state["light_state"] = "EMERGENCY_YELLOW"

    assert control.tick_emergency_phase() is True
    assert state.sys_state["emergency_phase"] == "ALL_RED_CLEAR"
    assert state.sys_state["command"] == "EMERGENCY_ALL_RED"

    state.sys_state["emergency_phase_until"] = 0.0
    assert control.tick_emergency_phase() is True
    assert state.sys_state["emergency_phase"] == "EMERGENCY_RED"
    assert state.sys_state["command"] == "EMERGENCY_RED"

    state.sys_state["emergency_phase_until"] = time.time() - 1.0
    assert control.tick_emergency_phase() is False
    assert state.sys_state["emergency_phase"] is None
    assert state.sys_state["command"] == "KEEP"


def test_clear_emergency_resets_emergency_command_to_keep():
    state.sys_state["emergency_phase"] = "EMERGENCY_RED"
    state.sys_state["emergency_phase_until"] = 999999.0
    state.sys_state["command"] = "EMERGENCY_RED"
    state.sys_state["light_state"] = "EMERGENCY_RED"

    control.clear_emergency()

    assert state.sys_state["emergency_phase"] is None
    assert state.sys_state["emergency_phase_until"] == 0.0
    assert state.sys_state["command"] == "KEEP"
    assert state.sys_state["light_state"] == "UNKNOWN"


def test_manual_mode_applies_manual_override_once():
    state.sys_state["mode"] = "MANUAL"
    state.sys_state["manual_override"] = "CAR_GREEN"
    state.sys_state["command"] = "KEEP"
    state.sys_state["light_state"] = "UNKNOWN"

    control.apply_person_control_logic(person_count=0, wheelchair_count=0)

    assert state.sys_state["command"] == "CAR_GREEN"
    assert state.sys_state["light_state"] == "MANUAL_OVERRIDE"
    assert state.sys_state["manual_override"] is None


def test_trigger_emergency_does_nothing_when_priority_disabled():
    """emergency_priority_active=False → trigger_emergency_vehicle is a no-op."""
    state.sys_state["emergency_priority_active"] = False
    state.sys_state["command"] = "KEEP"
    state.sys_state["emergency_phase"] = None

    control.trigger_emergency_vehicle()

    assert state.sys_state["command"] == "KEEP"
    assert state.sys_state["emergency_phase"] is None


def test_auto_mode_applies_logic_decide_light():
    """AUTO mode → apply_person_control_logic calls logic.decide_light."""
    state.sys_state["mode"] = "AUTO"
    state.sys_state["command"] = "KEEP"
    state.sys_state["light_state"] = "CAR_GREEN"
    state.sys_state["cars"] = 0
    state.sys_state["wheelchair_priority_active"] = True
    state.sys_state["emergency_phase"] = None

    control.apply_person_control_logic(person_count=5, wheelchair_count=0)

    # With 5 persons, 0 cars → should trigger PED_GREEN_20 (heavy pedestrians)
    assert state.sys_state["command"] == "PED_GREEN_20"
    assert state.sys_state["light_state"] == "PED_LONG"


def test_manual_mode_no_override_sends_keep():
    """MANUAL mode with no override queued → command stays KEEP."""
    state.sys_state["mode"] = "MANUAL"
    state.sys_state["manual_override"] = None
    state.sys_state["command"] = "SOMETHING_OLD"
    state.sys_state["emergency_phase"] = None

    control.apply_person_control_logic(person_count=5, wheelchair_count=0)

    assert state.sys_state["command"] == "KEEP"

