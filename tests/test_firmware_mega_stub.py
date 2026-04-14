"""
Stub Tests — Arduino Mega 2560 Firmware Logic

Python re-implementations of core ArduinoMega.ino C++ logic,
used as Stubs to validate FSM behaviour, JSON parsing, brightness
control, pressure/jam detection, and RFID UID matching WITHOUT
requiring actual hardware or arduino-cli compilation.

Each section mirrors a SECTION in ArduinoMega.ino.
"""

import pytest


# ═══════════════════════════════════════════════════════════════════════════════
#  STUB: parseJsonString  (Section A — Server Command Handler)
#  Mirrors ArduinoMega.ino lines 562–573
# ═══════════════════════════════════════════════════════════════════════════════

def parse_json_string(json_str: str, key: str) -> str:
    """Python stub of parseJsonString() from ArduinoMega.ino."""
    # Try compact form: "key":"value"
    needle = f'"{key}":"'
    idx = json_str.find(needle)
    if idx == -1:
        # Try spaced form: "key": "value"
        needle = f'"{key}": "'
        idx = json_str.find(needle)
    if idx == -1:
        return ""
    start = idx + len(needle)
    end = json_str.find('"', start)
    return "" if end == -1 else json_str[start:end]


def parse_json_long(json_str: str, key: str, fallback: int = -1) -> int:
    """Python stub of parseJsonLong() from ArduinoMega.ino."""
    needle = f'"{key}":'
    idx = json_str.find(needle)
    if idx == -1:
        return fallback
    start = idx + len(needle)
    # Skip spaces
    while start < len(json_str) and json_str[start] == ' ':
        start += 1
    negative = False
    if start < len(json_str) and json_str[start] == '-':
        negative = True
        start += 1
    end = start
    while end < len(json_str) and json_str[end].isdigit():
        end += 1
    if end == start:
        return fallback
    value = int(json_str[start:end])
    return -value if negative else value


def parse_json_int_array(json_str: str, key: str, max_count: int):
    """Python stub of parseJsonIntArray() from ArduinoMega.ino."""
    if max_count <= 0:
        return []
    needle = f'"{key}":'
    idx = json_str.find(needle)
    if idx == -1:
        return []
    start = json_str.find("[", idx + len(needle))
    if start == -1:
        return []
    end = json_str.find("]", start + 1)
    if end == -1:
        return []

    values = []
    pos = start + 1
    while pos < end and len(values) < max_count:
        while pos < end and json_str[pos] in {" ", ","}:
            pos += 1
        if pos >= end:
            break

        negative = False
        if json_str[pos] == "-":
            negative = True
            pos += 1

        digit_start = pos
        while pos < end and json_str[pos].isdigit():
            pos += 1
        if digit_start == pos:
            while pos < end and json_str[pos] != ",":
                pos += 1
            continue

        value = int(json_str[digit_start:pos])
        values.append(-value if negative else value)

    return values


class TestParseJsonString:
    def test_compact_form(self):
        assert parse_json_string('{"command":"CAR_GREEN"}', "command") == "CAR_GREEN"

    def test_spaced_form(self):
        assert parse_json_string('{"command": "PED_GREEN_10"}', "command") == "PED_GREEN_10"

    def test_missing_key_returns_empty(self):
        assert parse_json_string('{"other":"value"}', "command") == ""

    def test_empty_json_returns_empty(self):
        assert parse_json_string('', "command") == ""

    def test_multiple_keys(self):
        j = '{"command":"KEEP","cars_total":5,"mode":"AUTO"}'
        assert parse_json_string(j, "command") == "KEEP"
        assert parse_json_string(j, "mode") == "AUTO"

    def test_unclosed_string_returns_empty(self):
        assert parse_json_string('{"command":"KEEP', "command") == ""

    def test_emergency_commands(self):
        for cmd in ["EMERGENCY_YELLOW", "EMERGENCY_ALL_RED", "EMERGENCY_RED", "EMERGENCY_CLEAR"]:
            j = f'{{"command":"{cmd}"}}'
            assert parse_json_string(j, "command") == cmd


class TestParseJsonLong:
    def test_simple_integer(self):
        assert parse_json_long('{"cars_total":5}', "cars_total") == 5

    def test_spaced_integer(self):
        assert parse_json_long('{"cars": 12}', "cars") == 12

    def test_negative_integer(self):
        assert parse_json_long('{"offset":-3}', "offset") == -3

    def test_missing_key_returns_fallback(self):
        assert parse_json_long('{"other":1}', "cars_total", -1) == -1

    def test_zero_value(self):
        assert parse_json_long('{"cars_total":0}', "cars_total") == 0

    def test_large_value(self):
        assert parse_json_long('{"count":99999}', "count") == 99999


class TestParseJsonIntArray:
    def test_parses_lane_counts(self):
        assert parse_json_int_array('{"lane_counts":[1,2,3]}', "lane_counts", 3) == [1, 2, 3]

    def test_parses_with_spaces(self):
        assert parse_json_int_array('{"lane_counts": [0, 4, 2]}', "lane_counts", 3) == [0, 4, 2]

    def test_limits_max_count(self):
        assert parse_json_int_array('{"lane_counts":[1,2,3,4]}', "lane_counts", 3) == [1, 2, 3]

    def test_missing_key_returns_empty(self):
        assert parse_json_int_array('{"cars_total":7}', "lane_counts", 3) == []

    def test_negative_values_supported(self):
        assert parse_json_int_array('{"lane_counts":[-1,2,-3]}', "lane_counts", 3) == [-1, 2, -3]


# ═══════════════════════════════════════════════════════════════════════════════
#  STUB: isRecognizedEsp32Command  (Section A)
#  Mirrors ArduinoMega.ino lines 351–369
# ═══════════════════════════════════════════════════════════════════════════════

_RECOGNIZED_COMMANDS = {
    "CAR_GREEN", "EMERGENCY_YELLOW", "EMERGENCY_ALL_RED", "EMERGENCY_RED",
    "EMERGENCY_CLEAR", "LANE_STRAIGHT", "LANE_LEFT", "LANE_RIGHT",
    "LANE_LEFT_STRAIGHT", "LANE_RIGHT_STRAIGHT", "LANE_LEFT_RIGHT",
    "LANE_ALL", "LANE_CLOSED", "LANE_EMERGENCY", "KEEP",
}


def is_recognized_esp32_command(cmd: str) -> bool:
    """Python stub of isRecognizedEsp32Command()."""
    if cmd in _RECOGNIZED_COMMANDS:
        return True
    if cmd.startswith("PED_GREEN_"):
        return True
    if cmd.startswith("COUNT_"):
        return True
    return False


class TestIsRecognizedEsp32Command:
    @pytest.mark.parametrize("cmd", list(_RECOGNIZED_COMMANDS))
    def test_all_fixed_commands_recognized(self, cmd):
        assert is_recognized_esp32_command(cmd) is True

    @pytest.mark.parametrize("cmd", ["PED_GREEN_10", "PED_GREEN_60", "PED_GREEN_120"])
    def test_ped_green_variants(self, cmd):
        assert is_recognized_esp32_command(cmd) is True

    @pytest.mark.parametrize("cmd", ["COUNT_0", "COUNT_5", "COUNT_100"])
    def test_count_variants(self, cmd):
        assert is_recognized_esp32_command(cmd) is True

    @pytest.mark.parametrize("cmd", ["INVALID", "", "BLINK", "car_green", "PED_GREEN"])
    def test_unknown_commands_rejected(self, cmd):
        assert is_recognized_esp32_command(cmd) is False


# ═══════════════════════════════════════════════════════════════════════════════
#  STUB: BrightnessControl  (Section C — Illuminance Sensor)
#  Mirrors ArduinoMega.ino lines 663–674
# ═══════════════════════════════════════════════════════════════════════════════

ILLUM_UPPER = 100
ILLUM_LOWER = 40


def brightness_control(illuminance: int) -> int:
    """Python stub of BrightnessControl()."""
    if illuminance > ILLUM_UPPER:
        return 255
    elif illuminance < ILLUM_LOWER:
        return 135
    else:
        return illuminance * 2 + 55


class TestBrightnessControl:
    def test_high_illuminance_full_brightness(self):
        assert brightness_control(150) == 255
        assert brightness_control(101) == 255

    def test_low_illuminance_dim_brightness(self):
        assert brightness_control(0) == 135
        assert brightness_control(39) == 135

    def test_mid_range_linear_scaling(self):
        assert brightness_control(40) == 135   # 40*2+55 = 135 (boundary)
        assert brightness_control(70) == 195   # 70*2+55 = 195
        assert brightness_control(100) == 255  # 100*2+55 = 255 (boundary)

    def test_boundary_exact_upper(self):
        # illuminance == ILLUM_UPPER → NOT > ILLUM_UPPER → else branch
        assert brightness_control(ILLUM_UPPER) == ILLUM_UPPER * 2 + 55

    def test_boundary_exact_lower(self):
        # illuminance == ILLUM_LOWER → NOT < ILLUM_LOWER → else branch
        assert brightness_control(ILLUM_LOWER) == ILLUM_LOWER * 2 + 55


# ═══════════════════════════════════════════════════════════════════════════════
#  STUB: Traffic Light FSM  (Sections A + E)
#  Mirrors processEsp32Command + runStateMachine
# ═══════════════════════════════════════════════════════════════════════════════

# State enum mirroring TrafficState in ArduinoMega.ino
STATE_CAR_GREEN = 0
STATE_CAR_YELLOW = 1
STATE_PED_GREEN = 2
STATE_PED_BLINK = 3
STATE_PED_RED_WAIT = 4
STATE_EMERGENCY_YELLOW = 5
STATE_EMERGENCY_ALL_RED = 6
STATE_EMERGENCY_RED_HOLD = 7

# Lane enum
LANE_STRAIGHT = 0
LANE_LEFT = 1
LANE_RIGHT = 2

_LANE_CMD_MAP = {
    "LANE_STRAIGHT": 0, "LANE_LEFT": 1, "LANE_RIGHT": 2,
    "LANE_LEFT_STRAIGHT": 3, "LANE_RIGHT_STRAIGHT": 4,
    "LANE_LEFT_RIGHT": 5, "LANE_ALL": 6, "LANE_CLOSED": 7,
    "LANE_EMERGENCY": 8,
}

_EMERGENCY_PHASE_CMDS = {"EMERGENCY_YELLOW", "EMERGENCY_ALL_RED", "EMERGENCY_RED"}


class MegaFsmStub:
    """Python stub of the Arduino Mega traffic light state machine."""

    def __init__(self):
        self.current_state = STATE_CAR_GREEN
        self.fail_safe_mode = True
        self.emergency_active = False
        self.emergency_from_server = False
        self.car_count = 0
        self.current_lane = LANE_STRAIGHT
        self.ped_green_duration = 15000
        self.last_heartbeat_received = False

    def process_command(self, cmd: str):
        """Python stub of processEsp32Command()."""
        if is_recognized_esp32_command(cmd):
            self.last_heartbeat_received = True
            if self.fail_safe_mode:
                self.fail_safe_mode = False

        if cmd == "CAR_GREEN":
            if self.current_state not in (
                STATE_CAR_GREEN, STATE_CAR_YELLOW,
                STATE_EMERGENCY_YELLOW, STATE_EMERGENCY_ALL_RED,
                STATE_EMERGENCY_RED_HOLD
            ):
                self.current_state = STATE_PED_BLINK
        elif cmd.startswith("PED_GREEN_"):
            seconds = int(cmd[10:])
            if 5 <= seconds <= 120:
                if self.current_state == STATE_CAR_GREEN and not self.emergency_active:
                    self.ped_green_duration = seconds * 1000
                    self.current_state = STATE_CAR_YELLOW
        elif cmd == "EMERGENCY_YELLOW":
            self.emergency_from_server = True
            self.emergency_active = True
            if self.current_state != STATE_EMERGENCY_YELLOW:
                self.current_state = STATE_EMERGENCY_YELLOW
        elif cmd == "EMERGENCY_ALL_RED":
            self.emergency_from_server = True
            self.emergency_active = True
            if self.current_state not in (STATE_EMERGENCY_ALL_RED, STATE_EMERGENCY_RED_HOLD):
                self.current_state = STATE_EMERGENCY_ALL_RED
        elif cmd == "EMERGENCY_RED":
            self.emergency_from_server = True
            self.emergency_active = True
            if self.current_state != STATE_EMERGENCY_RED_HOLD:
                self.current_state = STATE_EMERGENCY_RED_HOLD
        elif cmd == "EMERGENCY_CLEAR":
            self.emergency_from_server = False
            self.emergency_active = False
            self.current_state = STATE_PED_RED_WAIT
        elif cmd in _LANE_CMD_MAP:
            new_lane = _LANE_CMD_MAP[cmd]
            if new_lane != self.current_lane:
                self.current_lane = new_lane
        elif cmd.startswith("COUNT_"):
            self.car_count = int(cmd[6:])
        elif cmd == "KEEP":
            pass  # heartbeat only


class TestMegaFsm:
    def test_car_green_command_from_ped_green_triggers_blink(self):
        fsm = MegaFsmStub()
        fsm.current_state = STATE_PED_GREEN
        fsm.process_command("CAR_GREEN")
        assert fsm.current_state == STATE_PED_BLINK

    def test_car_green_ignored_when_already_car_green(self):
        fsm = MegaFsmStub()
        fsm.current_state = STATE_CAR_GREEN
        fsm.process_command("CAR_GREEN")
        assert fsm.current_state == STATE_CAR_GREEN

    def test_car_green_blocked_during_emergency(self):
        fsm = MegaFsmStub()
        fsm.current_state = STATE_EMERGENCY_RED_HOLD
        fsm.process_command("CAR_GREEN")
        assert fsm.current_state == STATE_EMERGENCY_RED_HOLD

    def test_ped_green_from_car_green(self):
        fsm = MegaFsmStub()
        fsm.current_state = STATE_CAR_GREEN
        fsm.process_command("PED_GREEN_15")
        assert fsm.current_state == STATE_CAR_YELLOW
        assert fsm.ped_green_duration == 15000

    def test_ped_green_invalid_duration_rejected(self):
        fsm = MegaFsmStub()
        fsm.current_state = STATE_CAR_GREEN
        original = fsm.ped_green_duration
        fsm.process_command("PED_GREEN_3")  # too short (< 5)
        assert fsm.current_state == STATE_CAR_GREEN
        assert fsm.ped_green_duration == original

    def test_ped_green_blocked_during_emergency(self):
        fsm = MegaFsmStub()
        fsm.current_state = STATE_CAR_GREEN
        fsm.emergency_active = True
        fsm.process_command("PED_GREEN_20")
        assert fsm.current_state == STATE_CAR_GREEN

    def test_emergency_sequence_yellow_to_all_red_to_hold(self):
        fsm = MegaFsmStub()
        fsm.process_command("EMERGENCY_YELLOW")
        assert fsm.current_state == STATE_EMERGENCY_YELLOW
        assert fsm.emergency_active is True

        fsm.process_command("EMERGENCY_ALL_RED")
        assert fsm.current_state == STATE_EMERGENCY_ALL_RED

        fsm.process_command("EMERGENCY_RED")
        assert fsm.current_state == STATE_EMERGENCY_RED_HOLD

    def test_emergency_clear_resets_to_ped_red_wait(self):
        fsm = MegaFsmStub()
        fsm.emergency_active = True
        fsm.emergency_from_server = True
        fsm.current_state = STATE_EMERGENCY_RED_HOLD

        fsm.process_command("EMERGENCY_CLEAR")
        assert fsm.current_state == STATE_PED_RED_WAIT
        assert fsm.emergency_active is False
        assert fsm.emergency_from_server is False

    def test_lane_command_changes_lane(self):
        fsm = MegaFsmStub()
        assert fsm.current_lane == LANE_STRAIGHT
        fsm.process_command("LANE_LEFT")
        assert fsm.current_lane == _LANE_CMD_MAP["LANE_LEFT"]

    def test_lane_same_value_no_change(self):
        fsm = MegaFsmStub()
        fsm.current_lane = LANE_STRAIGHT
        fsm.process_command("LANE_STRAIGHT")
        assert fsm.current_lane == LANE_STRAIGHT

    def test_count_command_updates_car_count(self):
        fsm = MegaFsmStub()
        fsm.process_command("COUNT_12")
        assert fsm.car_count == 12

    def test_keep_resets_failsafe(self):
        fsm = MegaFsmStub()
        assert fsm.fail_safe_mode is True
        fsm.process_command("KEEP")
        assert fsm.fail_safe_mode is False

    def test_unrecognized_command_does_not_clear_failsafe(self):
        fsm = MegaFsmStub()
        assert fsm.fail_safe_mode is True
        fsm.process_command("BLINK_FAST")
        assert fsm.fail_safe_mode is True


# ═══════════════════════════════════════════════════════════════════════════════
#  STUB: Pressure Sensor / Jam Detection  (Section B)
#  Mirrors ArduinoMega.ino lines 606–656
# ═══════════════════════════════════════════════════════════════════════════════

PRESSURE_THRESHOLD = 60
JAM_DURATION_THRESHOLD = 60_000_000  # µs
CAR_COUNT_JAM_THRESHOLD = 10


class PressureSensorStub:
    """Python stub of readPressureSensor + detect_jam logic."""

    def __init__(self):
        self.pressure_on = False
        self.pressure_start_us = 0
        self.pressure_duration = 0
        self.jam = False
        self.cooling_period = False
        self.red_light_violation = False
        self.car_count = 0
        self.current_state = STATE_CAR_GREEN

    def _is_red(self) -> bool:
        return self.current_state in (STATE_PED_GREEN, STATE_PED_BLINK, STATE_PED_RED_WAIT)

    def _detect_jam(self):
        if (self.pressure_duration > JAM_DURATION_THRESHOLD
                and self.car_count > CAR_COUNT_JAM_THRESHOLD):
            self.jam = True
            self.cooling_period = True
        elif not self.cooling_period:
            self.jam = False

    def read_pressure(self, pressure: int, current_us: int):
        """Simulate one readPressureSensor() tick."""
        if pressure > PRESSURE_THRESHOLD:
            if not self.pressure_on:
                self.pressure_on = True
                self.pressure_start_us = current_us
                if self._is_red():
                    self.red_light_violation = True
            else:
                self.pressure_duration = current_us - self.pressure_start_us
                self._detect_jam()
        else:
            if self.pressure_on:
                self.pressure_duration = current_us - self.pressure_start_us
                self.pressure_on = False
                self._detect_jam()


class TestPressureSensor:
    def test_no_pressure_no_event(self):
        s = PressureSensorStub()
        s.read_pressure(0, 1000)
        assert s.pressure_on is False
        assert s.red_light_violation is False
        assert s.jam is False

    def test_pressure_above_threshold_activates(self):
        s = PressureSensorStub()
        s.read_pressure(70, 1000)
        assert s.pressure_on is True

    def test_red_light_violation_on_red_state(self):
        s = PressureSensorStub()
        s.current_state = STATE_PED_GREEN  # car light is RED
        s.read_pressure(70, 1000)
        assert s.red_light_violation is True

    def test_no_violation_on_green_state(self):
        s = PressureSensorStub()
        s.current_state = STATE_CAR_GREEN  # car light is GREEN
        s.read_pressure(70, 1000)
        assert s.red_light_violation is False

    def test_jam_detected_when_duration_and_count_exceed(self):
        s = PressureSensorStub()
        s.car_count = 15  # > CAR_COUNT_JAM_THRESHOLD

        # First tick: pressure on
        s.read_pressure(70, 0)
        assert s.jam is False

        # Second tick: 61 seconds later (in µs), still pressed
        s.read_pressure(70, 61_000_000)
        assert s.jam is True
        assert s.cooling_period is True

    def test_no_jam_when_car_count_below_threshold(self):
        s = PressureSensorStub()
        s.car_count = 5  # below threshold

        s.read_pressure(70, 0)
        s.read_pressure(70, 61_000_000)
        assert s.jam is False

    def test_pressure_release_calculates_duration(self):
        s = PressureSensorStub()
        s.read_pressure(70, 1000)
        assert s.pressure_on is True
        s.read_pressure(0, 5000)
        assert s.pressure_on is False
        assert s.pressure_duration == 4000


# ═══════════════════════════════════════════════════════════════════════════════
#  STUB: RFID UID Matching  (Section D)
#  Mirrors ArduinoMega.ino lines 683–737
# ═══════════════════════════════════════════════════════════════════════════════

EMERGENCY_UIDS = [
    [0xCC, 0x0E, 0x40, 0x18],
    [0xBA, 0x9C, 0xA9, 0x1A],
]


def check_rfid_uid(uid: list[int]) -> bool:
    """Python stub of checkRFID UID matching."""
    for known in EMERGENCY_UIDS:
        if len(uid) >= 4 and uid[:4] == known:
            return True
    return False


class TestRfidUid:
    def test_known_uid_1_matches(self):
        assert check_rfid_uid([0xCC, 0x0E, 0x40, 0x18]) is True

    def test_known_uid_2_matches(self):
        assert check_rfid_uid([0xBA, 0x9C, 0xA9, 0x1A]) is True

    def test_unknown_uid_does_not_match(self):
        assert check_rfid_uid([0xDE, 0xAD, 0xBE, 0xEF]) is False

    def test_partial_uid_does_not_match(self):
        assert check_rfid_uid([0xCC, 0x0E]) is False

    def test_empty_uid_does_not_match(self):
        assert check_rfid_uid([]) is False

    def test_all_zeros_does_not_match(self):
        assert check_rfid_uid([0x00, 0x00, 0x00, 0x00]) is False
