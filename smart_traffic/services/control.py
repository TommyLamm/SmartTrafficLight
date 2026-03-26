import logic

from ..state import sys_state


def apply_person_control_logic(person_count, wheelchair_count):
    if sys_state["mode"] == "AUTO":
        cmd, new_state = logic.decide_light(
            person_count,
            sys_state["cars"],
            wheelchair_count,
            sys_state["light_state"]
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
