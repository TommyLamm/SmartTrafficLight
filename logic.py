def decide_light(person_count, vehicle_count, wheelchair_count, current_light_state):
    """
    Traffic Light Decision Algorithm
    This file is hot-reloaded dynamically. No server restart required!
    wheelchair_count: 輪椅使用者數量（優先權最高）
    """
    command = "KEEP"

    # ✅ 優先級 1：偵測到輪椅使用者，給予最長過街時間
    if wheelchair_count > 0 and vehicle_count <= 1:
        if current_light_state != "PED_WHEELCHAIR":
            command = "PED_GREEN_30"
            current_light_state = "PED_WHEELCHAIR"

    # 優先級 2：大量行人
    elif person_count > 3 and vehicle_count <= 1:
        if current_light_state != "PED_LONG":
            command = "PED_GREEN_20"
            current_light_state = "PED_LONG"

    # 優先級 3：一般行人
    elif person_count > 0 and vehicle_count <= 1:
        if current_light_state != "PED_SHORT":
            command = "PED_GREEN_10"
            current_light_state = "PED_SHORT"

    # 優先級 4：車流為主
    elif vehicle_count > 2 or person_count == 0:
        if current_light_state != "CAR_GREEN":
            command = "CAR_GREEN"
            current_light_state = "CAR_GREEN"

    return command, current_light_state
