def decide_light(person_count, vehicle_count, current_light_state):
    """
    Traffic Light Decision Algorithm
    This file is hot-reloaded dynamically. No server restart required!
    """
    command = "KEEP" 

    # 🚦 Smart Traffic Logic
    if person_count > 0 and vehicle_count <= 1:
        if person_count > 3:
            if current_light_state != "PED_LONG":
                command = "PED_GREEN_20"
                current_light_state = "PED_LONG"
        else:
            if current_light_state != "PED_SHORT":
                command = "PED_GREEN_10"
                current_light_state = "PED_SHORT"

    elif vehicle_count > 2 or person_count == 0:
        if current_light_state != "CAR_GREEN":
            command = "CAR_GREEN"
            current_light_state = "CAR_GREEN"

    return command, current_light_state
