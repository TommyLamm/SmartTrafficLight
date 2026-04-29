def decide_light(person_count, vehicle_count, wheelchair_count, current_light_state,
                 emergency_active=False, wheelchair_priority_active=True):
    """
    Traffic Light Decision Algorithm
    This file is hot-reloaded dynamically. No server restart required!
    wheelchair_count: number of wheelchair users detected (highest priority)
    """
    command = "KEEP"

    # Emergency sequence is orchestrated upstream by control.py
    if emergency_active:
        return command, current_light_state

    # Priority 1: Wheelchair users detected — adaptive green (max 60s)
    if wheelchair_priority_active and wheelchair_count > 0:
        green_sec = min(10 + wheelchair_count * 10, 60)
        command = f"PED_GREEN_{green_sec}"
        current_light_state = "PED_WHEELCHAIR"

    # Priority 2: Heavy pedestrian traffic (10+) overrides vehicles
    elif person_count >= 10:
        if current_light_state != "PED_LONG":
            command = "PED_GREEN_20"
            current_light_state = "PED_LONG"

    # Priority 3: Moderate pedestrians with low vehicle count
    elif person_count > 3 and vehicle_count <= 1:
        if current_light_state != "PED_LONG":
            command = "PED_GREEN_20"
            current_light_state = "PED_LONG"

    # Priority 4: Few pedestrians present
    elif person_count > 0 and vehicle_count <= 1:
        if current_light_state != "PED_SHORT":
            command = "PED_GREEN_10"
            current_light_state = "PED_SHORT"

    # Priority 5: Vehicle-dominant traffic
    elif vehicle_count > 2 or person_count == 0:
        if current_light_state != "CAR_GREEN":
            command = "CAR_GREEN"
            current_light_state = "CAR_GREEN"

    return command, current_light_state

