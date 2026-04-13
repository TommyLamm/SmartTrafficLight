import logic


def test_emergency_active_keeps_current_state():
    cmd, state = logic.decide_light(
        person_count=5,
        vehicle_count=0,
        wheelchair_count=1,
        current_light_state="PED_LONG",
        emergency_active=True,
    )
    assert cmd == "KEEP"
    assert state == "PED_LONG"


def test_wheelchair_priority_scales_and_caps():
    cmd, state = logic.decide_light(
        person_count=1,
        vehicle_count=0,
        wheelchair_count=10,
        current_light_state="CAR_GREEN",
        wheelchair_priority_active=True,
    )
    assert cmd == "PED_GREEN_60"
    assert state == "PED_WHEELCHAIR"


def test_heavy_pedestrians_trigger_long_green():
    cmd, state = logic.decide_light(
        person_count=4,
        vehicle_count=1,
        wheelchair_count=0,
        current_light_state="CAR_GREEN",
    )
    assert cmd == "PED_GREEN_20"
    assert state == "PED_LONG"


def test_regular_pedestrians_trigger_short_green():
    cmd, state = logic.decide_light(
        person_count=2,
        vehicle_count=1,
        wheelchair_count=0,
        current_light_state="CAR_GREEN",
    )
    assert cmd == "PED_GREEN_10"
    assert state == "PED_SHORT"


def test_vehicle_dominant_prefers_car_green():
    cmd, state = logic.decide_light(
        person_count=0,
        vehicle_count=4,
        wheelchair_count=0,
        current_light_state="PED_SHORT",
    )
    assert cmd == "CAR_GREEN"
    assert state == "CAR_GREEN"


def test_idle_no_people_no_vehicles_keeps_state():
    """Zero people + zero vehicles + already CAR_GREEN → no state change."""
    cmd, state = logic.decide_light(
        person_count=0,
        vehicle_count=0,
        wheelchair_count=0,
        current_light_state="CAR_GREEN",
    )
    assert cmd == "KEEP"
    assert state == "CAR_GREEN"


def test_reenter_ped_long_keeps_command():
    """Already in PED_LONG with heavy pedestrians → KEEP (no duplicate command)."""
    cmd, state = logic.decide_light(
        person_count=5,
        vehicle_count=0,
        wheelchair_count=0,
        current_light_state="PED_LONG",
    )
    assert cmd == "KEEP"
    assert state == "PED_LONG"


def test_reenter_ped_short_keeps_command():
    """Already in PED_SHORT with some pedestrians → KEEP."""
    cmd, state = logic.decide_light(
        person_count=2,
        vehicle_count=0,
        wheelchair_count=0,
        current_light_state="PED_SHORT",
    )
    assert cmd == "KEEP"
    assert state == "PED_SHORT"


def test_wheelchair_priority_disabled_ignores_wheelchair():
    """wheelchair_priority_active=False → wheelchair doesn't trigger priority."""
    cmd, state = logic.decide_light(
        person_count=1,
        vehicle_count=0,
        wheelchair_count=5,
        current_light_state="CAR_GREEN",
        wheelchair_priority_active=False,
    )
    # Should fall through to regular pedestrian logic, not wheelchair priority
    assert cmd != "PED_GREEN_60"
    assert state != "PED_WHEELCHAIR"


def test_wheelchair_blocked_by_high_vehicle_count():
    """Wheelchair present but vehicle_count > 1 → wheelchair priority skipped."""
    cmd, state = logic.decide_light(
        person_count=1,
        vehicle_count=3,
        wheelchair_count=2,
        current_light_state="CAR_GREEN",
        wheelchair_priority_active=True,
    )
    # vehicle_count > 1 blocks wheelchair priority; falls to priority 4 (vehicle dominant)
    assert state != "PED_WHEELCHAIR"

