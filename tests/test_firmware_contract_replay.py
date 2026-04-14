import time

import smart_traffic.state as state

from smart_traffic.services import control


_EMERGENCY_PHASE_COMMANDS = {"EMERGENCY_YELLOW", "EMERGENCY_ALL_RED", "EMERGENCY_RED"}


def _mega_wifi_translation(server_commands):
    outputs = []
    emergency_active = False
    for cmd in server_commands:
        if emergency_active and cmd not in _EMERGENCY_PHASE_COMMANDS:
            outputs.append("EMERGENCY_CLEAR")
            emergency_active = False

        outputs.append(cmd)

        if cmd in _EMERGENCY_PHASE_COMMANDS:
            emergency_active = True
        elif cmd == "EMERGENCY_CLEAR":
            emergency_active = False
    return outputs


def test_server_emergency_sequence_requires_clear_translation():
    state.sys_state["emergency_priority_active"] = True
    control.trigger_emergency_vehicle()

    commands = [state.sys_state["command"]]
    state.sys_state["emergency_phase_until"] = time.time() - 1.0
    control.tick_emergency_phase()
    commands.append(state.sys_state["command"])

    state.sys_state["emergency_phase_until"] = 0.0
    control.tick_emergency_phase()
    commands.append(state.sys_state["command"])

    state.sys_state["emergency_phase_until"] = time.time() - 1.0
    control.tick_emergency_phase()
    commands.append(state.sys_state["command"])

    assert commands[:3] == ["EMERGENCY_YELLOW", "EMERGENCY_ALL_RED", "EMERGENCY_RED"]
    assert commands[-1] == "KEEP"

    translated = _mega_wifi_translation(commands)
    assert "EMERGENCY_CLEAR" in translated
    assert translated[-2:] == ["EMERGENCY_CLEAR", "KEEP"]


def test_stats_contract_exposes_cars_and_cars_total_for_mega_carcount(app_client):
    state.sys_state["cars"] = 11

    payload = app_client.get("/stats").get_json()

    assert payload["cars"] == 11
    assert payload["cars_total"] == 11

