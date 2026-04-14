import smart_traffic.state as state

from smart_traffic.web import routes_detect, routes_ui


def test_stats_contract_contains_expected_fields(app_client):
    state.sys_state["cars"] = 4
    state.sys_state["persons"] = 2
    state.sys_state["wheelchairs"] = 1
    state.sys_state["command"] = "KEEP"
    state.sys_state["lane_counts"] = [1, 2, 1]
    state.sys_state["tidal_direction"] = "BALANCED"
    state.sys_state["plates"] = [{"text": "ABC123"}]

    resp = app_client.get("/stats")
    data = resp.get_json()

    assert resp.status_code == 200
    assert data["cars"] == 4
    assert data["cars_total"] == 4
    assert data["persons"] == 2
    assert data["wheelchairs"] == 1
    assert data["command"] == "KEEP"
    assert data["lane_counts"] == [1, 2, 1]
    assert data["tidal_direction"] == "BALANCED"
    assert isinstance(data["sample_window"], int)
    assert data["sample_window"] >= 0
    assert "stream_car_online" in data
    assert "stream_person_online" in data
    assert "stream_plate_online" in data
    assert "plates" not in data
    assert data["plates_count"] == 1


def test_detect_routes_reject_empty_payload(app_client):
    assert app_client.post("/detect_car", data=b"").status_code == 400
    assert app_client.post("/detect_person", data=b"").status_code == 400
    assert app_client.post("/detect_plate", data=b"").status_code == 400
    assert app_client.post("/capture_violation", data=b"").status_code == 400


def test_detect_routes_accept_stubbed_payload(app_client, monkeypatch, sample_obfuscated_jpeg):
    monkeypatch.setattr(
        routes_detect,
        "process_car_data",
        lambda _data: {"cars": 3, "persons": 0, "wheelchairs": 0, "command": "CAR_GREEN"},
    )
    monkeypatch.setattr(
        routes_detect,
        "process_person_data",
        lambda _data: {"cars": 3, "persons": 1, "wheelchairs": 0, "command": "PED_GREEN_10"},
    )
    monkeypatch.setattr(
        routes_detect,
        "process_plate_data",
        lambda _data: {"plates_this_frame": [], "total_plates": 0, "command": "KEEP"},
    )
    monkeypatch.setattr(
        routes_detect,
        "process_violation_data",
        lambda _data: {"success": True, "total_violations": 1},
    )

    car_resp = app_client.post(
        "/detect_car",
        data=sample_obfuscated_jpeg,
        content_type="application/octet-stream",
    )
    person_resp = app_client.post(
        "/detect_person",
        data=sample_obfuscated_jpeg,
        content_type="application/octet-stream",
    )
    plate_resp = app_client.post(
        "/detect_plate",
        data=sample_obfuscated_jpeg,
        content_type="application/octet-stream",
    )
    violation_resp = app_client.post(
        "/capture_violation",
        data=sample_obfuscated_jpeg,
        content_type="application/octet-stream",
    )

    assert car_resp.status_code == 200
    assert car_resp.get_json()["command"] == "CAR_GREEN"
    assert person_resp.status_code == 200
    assert person_resp.get_json()["command"] == "PED_GREEN_10"
    assert plate_resp.status_code == 200
    assert "plates_this_frame" in plate_resp.get_json()
    assert violation_resp.status_code == 200
    assert violation_resp.get_json()["success"] is True


def test_emergency_routes_and_clear_behavior(app_client):
    trigger = app_client.post("/trigger_emergency", json={})
    assert trigger.status_code == 200
    assert trigger.get_json()["success"] is True

    after_trigger = app_client.get("/stats").get_json()
    assert after_trigger["command"] in {"EMERGENCY_YELLOW", "EMERGENCY_ALL_RED", "EMERGENCY_RED"}

    clear = app_client.post("/clear_emergency", json={})
    assert clear.status_code == 200
    assert clear.get_json()["success"] is True

    after_clear = app_client.get("/stats").get_json()
    assert after_clear["command"] == "KEEP"


def test_lane_boundaries_validation(app_client):
    bad = app_client.post(
        "/lane_boundaries",
        json={
            "boundary1_top": 0.7,
            "boundary1_bottom": 0.3,
            "boundary2_top": 0.6,   # invalid: boundary1_top >= boundary2_top
            "boundary2_bottom": 0.7,
        },
    )
    assert bad.status_code == 400
    assert bad.get_json()["success"] is False


def test_manual_override_route_sets_command_in_manual_mode(app_client):
    set_mode = app_client.post("/set_mode", json={"mode": "MANUAL"})
    assert set_mode.status_code == 200
    assert state.sys_state["mode"] == "MANUAL"

    override = app_client.post("/manual_override", json={"command": "CAR_GREEN"})
    assert override.status_code == 200
    assert override.get_json()["success"] is True
    assert state.sys_state["manual_override"] == "CAR_GREEN"


def test_index_uses_configured_editor_url(app_client, monkeypatch):
    monkeypatch.setattr(routes_ui, "EDITOR_URL", "https://example.com/editor")
    resp = app_client.get("/")
    html = resp.get_data(as_text=True)

    assert resp.status_code == 200
    assert 'id="editor-frame"' in html
    assert 'data-src="https://example.com/editor"' in html

