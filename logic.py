def decide_light(person_count, vehicle_count, wheelchair_count, current_light_state,
                 emergency_active=False, wheelchair_priority_active=True):
    """
    Traffic Light Decision Algorithm
    This file is hot-reloaded dynamically. No server restart required!

    Args:
        person_count: Number of pedestrians detected
        vehicle_count: Number of vehicles detected
        wheelchair_count: Number of wheelchair users detected
        current_light_state: Current traffic light state string
        emergency_active: Feature flag — emergency vehicle priority enabled
        wheelchair_priority_active: Feature flag — adaptive wheelchair green time enabled

    Wheelchair green time formula:
        green_sec = clamp(10 + wheelchair_count * 10, min=10, max=60)
        e.g. 1 user → 20s, 2 users → 30s, 5 users → 60s (max)
    """
    command = "KEEP"

    # Priority 0: Emergency is handled upstream in control.py (phased state machine).
    # Nothing to compute here — the flag is passed for future logic extensions.

    # Priority 1: Wheelchair users — adaptive green time
    if wheelchair_priority_active and wheelchair_count > 0 and vehicle_count <= 1:
    	green_sec = min(10 + wheelchair_count * 10, 60)
    	command = f"PED_GREEN_{green_sec}"
    	current_light_state = "PED_WHEELCHAIR"

    # Priority 2: Heavy pedestrian traffic
    elif person_count > 3 and vehicle_count <= 1:
        if current_light_state != "PED_LONG":
            command = "PED_GREEN_20"
            current_light_state = "PED_LONG"

    # Priority 3: Normal pedestrian traffic
    elif person_count > 0 and vehicle_count <= 1:
        if current_light_state != "PED_SHORT":
            command = "PED_GREEN_10"
            current_light_state = "PED_SHORT"

    # Priority 4: Vehicle-dominant
    elif vehicle_count > 2 or person_count == 0:
        if current_light_state != "CAR_GREEN":
            command = "CAR_GREEN"
            current_light_state = "CAR_GREEN"

    return command, current_light_state