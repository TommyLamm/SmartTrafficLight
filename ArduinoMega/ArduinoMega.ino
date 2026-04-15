// ============================================================
//  Arduino Mega 2560 — Unified Traffic Control System
//  WiFi architecture (ESP8266 AT module on Serial2)
// ------------------------------------------------------------
//  WIRING:
//    ESP8266 TX    ──> Mega RX2 (pin 17)
//    ESP8266 RX    ──> Mega TX2 (pin 16)
//    ESP8266 CH_PD ──> Mega 3.3V  (MUST pull high)
//    ESP8266 Vcc   ──> Mega 3.3V
//    ESP8266 GND   ──> Mega GND
//
//  Serial Ports
//    Serial  (USB)    — Debug monitor
//    Serial2 (16/17)  — ESP8266 AT firmware (WiFiEsp library)
//    Serial1 (18/19)  — Unused / free for future sensors
//
//  Traffic LEDs  — Pins 22-27 (R/Y/G for Car #1 + Pedestrian)
//                  Pins 28-30 (R/Y/G for Car #2 showcase — mirrors Car #1)
//  OLED (I2C)    — SDA=20, SCL=21
//  Illuminance   — A1 (local brightness control)
//
//  NOTE:
//    Pressure + RFID sensing is handled locally on this Mega.
//    ESP32 cameras are standalone (no GPIO connections to Mega).
// ============================================================

// ───────────────────── FEATURE FLAGS ────────────────────────
// 1 = enabled, 0 = disabled
#ifndef ENABLE_RFID
#define ENABLE_RFID 1
#endif

#ifndef ENABLE_OLED
#define ENABLE_OLED 1
#endif

#ifndef ENABLE_PRESSURE_SENSOR
#define ENABLE_PRESSURE_SENSOR 1
#endif

#ifndef ENFORCE_RFID_UID_GATE
#define ENFORCE_RFID_UID_GATE 1
#endif

#if ENABLE_RFID
  #include <SPI.h>
  #include <MFRC522.h>
#endif

#if ENABLE_OLED
  #include <Wire.h>
  #include <Adafruit_GFX.h>
  #include <Adafruit_SSD1306.h>
#endif

// ── WiFi (ESP8266 AT via Serial2) ────────────────────────────
// Library: "WiFiEsp" by bportaluri (Arduino Library Manager)
#include "WiFiEsp.h"

// !! CHANGE BEFORE FLASHING !!
static const char WIFI_SSID[]   = "YOUR_SSID";
static const char WIFI_PASS[]   = "YOUR_PASSWORD";
static const char SERVER_HOST[] = "stl.gyke.net";  // server hostname or IP
// Optional fallback endpoint (typically fixed backend IP). Leave empty to disable.
static const char SERVER_FALLBACK_HOST[] = "";
static const int  SERVER_PORT   = 80;               // HTTP port for domain endpoint
static const char STATS_PATH[]  = "/stats";        // GET endpoint

// Poll interval must be < FAILSAFE_TIMEOUT (5000 ms)
#define POLL_INTERVAL_MS  2000UL
#define WIFI_RECONNECT_INTERVAL_MS 10000UL
#define WIFI_HTTP_TIMEOUT_MS 3000UL
#define WIFI_DIAG_INTERVAL_MS 2000UL

WiFiEspClient wifiClient;
unsigned long lastPollMs = 0;
unsigned long nextWifiReconnectMs = 0;
unsigned long lastWifiDiagMs = 0;
int lastWifiStatus = WL_IDLE_STATUS;

// ─────────────────────────── PIN MAP ────────────────────────
// Car #1 — main light (camera-controlled)
#define CAR_RED_PIN     22
#define CAR_GREEN_PIN   23
#define CAR_YELLOW_PIN  24   // was BLUE — now wired to Yellow LED

// Pedestrian light
#define PED_RED_PIN     25
#define PED_GREEN_PIN   26
#define PED_YELLOW_PIN  27   // was BLUE — now wired to Yellow LED

// Car #2 — showcase light (mirrors Car #1, no camera)
#define CAR2_RED_PIN    28
#define CAR2_GREEN_PIN  29
#define CAR2_YELLOW_PIN 30

// Legacy sensor pins (disabled by default; kept for optional local fallback)
#define RFID_SS_PIN     53
#define RFID_RST_PIN    49
#define PRESSURE_PIN    A0
#define ILLUMINANCE_PIN A1

// ─────────────────────────── CONSTANTS ──────────────────────
// Pressure sensor (legacy local path, disabled by default)
#define PRESSURE_THRESHOLD         60       // ADC counts
#define JAM_DURATION_THRESHOLD     60000000UL  // 60 s in µs
#define COOLING_PERIOD_DURATION   300000000UL  // 300 s in µs
#define CAR_COUNT_JAM_THRESHOLD    10       // vehicles on road

// Illuminance thresholds for Mega ADC (0-1023)
#define ILLUM_UPPER  700
#define ILLUM_LOWER  260
#define MIN_BRIGHTNESS 110
#define SOFTWARE_PWM_PERIOD_US 3000UL

// Timing (ms)
#define FAILSAFE_TIMEOUT   5000UL   // lose server heartbeat → failsafe
#define EMERGENCY_DURATION 15000UL  // emergency hold duration
#define EMERGENCY_YELLOW_DUR 3000UL
#define EMERGENCY_ALL_RED_DUR 5000UL
#define YELLOW_DURATION     3000UL
#define PED_BLINK_DURATION  4000UL
#define PED_RED_WAIT_DUR    2000UL
#define FAILSAFE_CAR_GREEN 30000UL  // car green time when no AI signal
#define SERVER_LANE_BUCKETS 3

// ─────────────────────────── RFID UIDs ──────────────────────
// Replace these with your real 4-byte emergency tag UIDs.
#define EMERGENCY_UID_1_B0 0xCC
#define EMERGENCY_UID_1_B1 0x0E
#define EMERGENCY_UID_1_B2 0x40
#define EMERGENCY_UID_1_B3 0x18

// Dummy values to bypass the CAFE BABE error for the second card
#define EMERGENCY_UID_2_B0 0xBA
#define EMERGENCY_UID_2_B1 0x9C
#define EMERGENCY_UID_2_B2 0xA9
#define EMERGENCY_UID_2_B3 0x1A

#if ENABLE_RFID && ENFORCE_RFID_UID_GATE
#if ((EMERGENCY_UID_1_B0 == 0xDE) && (EMERGENCY_UID_1_B1 == 0xAD) && (EMERGENCY_UID_1_B2 == 0xBE) && (EMERGENCY_UID_1_B3 == 0xEF)) || \
    ((EMERGENCY_UID_2_B0 == 0xCA) && (EMERGENCY_UID_2_B1 == 0xFE) && (EMERGENCY_UID_2_B2 == 0xBA) && (EMERGENCY_UID_2_B3 == 0xBE))
#error "RFID UID gate: replace placeholder EMERGENCY_UID_
#endif
#endif

const byte EMERGENCY_UIDS[][4] = {
  { EMERGENCY_UID_1_B0, EMERGENCY_UID_1_B1, EMERGENCY_UID_1_B2, EMERGENCY_UID_1_B3 },
  { EMERGENCY_UID_2_B0, EMERGENCY_UID_2_B1, EMERGENCY_UID_2_B2, EMERGENCY_UID_2_B3 }
};
const int NUM_EMERGENCY_TAGS = sizeof(EMERGENCY_UIDS) / sizeof(EMERGENCY_UIDS[0]);

// ─────────────────────────── OBJECTS ────────────────────────
#if ENABLE_RFID
MFRC522 rfid(RFID_SS_PIN, RFID_RST_PIN);
#endif

#if ENABLE_OLED
#define SCREEN_W 128
#define SCREEN_H  64
Adafruit_SSD1306 display(SCREEN_W, SCREEN_H, &Wire, -1);
#endif

// ─────────────────────────── ENUMS ──────────────────────────
enum TrafficState {
  STATE_CAR_GREEN,
  STATE_CAR_YELLOW,
  STATE_PED_GREEN,
  STATE_PED_BLINK,
  STATE_PED_RED_WAIT,
  STATE_EMERGENCY_YELLOW,
  STATE_EMERGENCY_ALL_RED,
  STATE_EMERGENCY_RED_HOLD
};

// Tidal-lane modes (commanded by ESP32 via [LANE_xxx] packets)
enum TidalLane {
  LANE_STRAIGHT,
  LANE_LEFT,
  LANE_RIGHT,
  LANE_LEFT_STRAIGHT,
  LANE_RIGHT_STRAIGHT,
  LANE_LEFT_RIGHT,
  LANE_ALL,
  LANE_CLOSED,
  LANE_EMERGENCY
};

// ─────────────────────── STATE VARIABLES ────────────────────
// --- Traffic light FSM ---
TrafficState currentState   = STATE_CAR_GREEN;
unsigned long stateStartTime = 0;
unsigned long pedGreenDuration = 15000;

// --- Heartbeat / failsafe ---
unsigned long lastHeartbeatTime = 0;
bool failSafeMode = true;

// --- RFID emergency ---
bool emergencyActive = false;
bool emergencyFromServer = false;  // true only for server-driven emergency sequence
unsigned long emergencyStartTime = 0;
bool emergencyPriorityEnabled = true;

// --- Pressure sensor ---
bool     pressureOn        = false;
unsigned long pressureStartUs  = 0;
unsigned long pressureDuration = 0;
bool     jam               = false;
bool     coolingPeriod     = false;
unsigned long lastJamTimeUs    = 0;

// Whether a red-light violation was detected this vehicle pass
bool redLightViolation = false;
bool forceCarGreenWithYellow = false;

// Car count: updated from /stats ("cars" or "cars_total")
int carCount = 0;
// Extra /stats analytics (aligned with ESP32 /detect_car response fields)
int serverLaneCounts[SERVER_LANE_BUCKETS] = {0, 0, 0};
String serverTidalDirection = "UNKNOWN";
int serverSampleWindow = 0;
String serverControlMode = "AUTO";

// --- Illuminance / LED brightness ---
int illuminance = 0;
int  brightness = 255;  // 0-255 PWM level for light output

// --- Tidal lane ---
TidalLane currentLane = LANE_STRAIGHT;

// --- Logging ---
unsigned long lastLogTime = 0;

// ============================================================
//  SETUP
// ============================================================
void setup() {
  Serial.begin(115200);    // USB debug

  // ── ESP8266 WiFi init (AT firmware via Serial2) ──────────
  Serial2.begin(115200);   // ESP8266 TX→RX2(17), RX←TX2(16)
  WiFi.init(&Serial2);
  if (WiFi.status() == WL_NO_SHIELD) {
    Serial.println(F("[WiFi] ESP8266 not found! Check wiring/baud."));
    // Continue in failsafe rather than halting permanently
  } else {
    Serial.print(F("[WiFi] Connecting to "));
    Serial.println(WIFI_SSID);
    int wifiAttempts = 0;
    while (WiFi.status() != WL_CONNECTED && wifiAttempts < 5) {
      WiFi.begin(WIFI_SSID, WIFI_PASS);
      delay(5000);
      wifiAttempts++;
      Serial.print(F("."));
    }
    if (WiFi.status() == WL_CONNECTED) {
      Serial.print(F("\n[WiFi] Connected! IP: "));
      Serial.println(WiFi.localIP());
    } else {
      Serial.println(F("\n[WiFi] Failed to connect — running in failsafe."));
    }
  }

  // Traffic LED pins — Car #1
  pinMode(CAR_RED_PIN,    OUTPUT);
  pinMode(CAR_GREEN_PIN,  OUTPUT);
  pinMode(CAR_YELLOW_PIN, OUTPUT);
  // Pedestrian
  pinMode(PED_RED_PIN,    OUTPUT);
  pinMode(PED_GREEN_PIN,  OUTPUT);
  pinMode(PED_YELLOW_PIN, OUTPUT);
  // Car #2 — showcase (mirrors Car #1)
  pinMode(CAR2_RED_PIN,    OUTPUT);
  pinMode(CAR2_GREEN_PIN,  OUTPUT);
  pinMode(CAR2_YELLOW_PIN, OUTPUT);

  // RFID
#if ENABLE_RFID
  SPI.begin();
  rfid.PCD_Init();
  Serial.println("[RFID] Legacy local RFID path enabled.");
#else
  Serial.println("[RFID] Disabled (ENABLE_RFID=0).");
#endif

  // OLED
#if ENABLE_OLED
  if (!display.begin(SSD1306_SWITCHCAPVCC, 0x3C)) {
    Serial.println("[OLED] ERROR: display not found at 0x3C");
  } else {
    display.clearDisplay();
    display.display();
    Serial.println("[OLED] Display initialised.");
  }
#else
  Serial.println("[OLED] Disabled (ENABLE_OLED=0).");
#endif

  switchState(STATE_CAR_GREEN);
  Serial.println("=== STL Mega Integrated System Started ===");
  Serial.println("    Inputs: ESP8266 /stats command | local RFID/Pressure | Illuminance A1");
}

// ============================================================
//  LOOP
// ============================================================
void loop() {
  BrightnessControl();

  // ── 1. POLL SERVER VIA ESP8266 WiFi ─────────────────────
  pollServer();

  // ── 2. CHECK HEARTBEAT / FAILSAFE ───────────────────────
  if (!failSafeMode && (millis() - lastHeartbeatTime > FAILSAFE_TIMEOUT)) {
    Serial.println("!! [WARNING] WiFi / server lost — entering Failsafe !!");
    failSafeMode = true;
    forceCarGreenWithYellow = false;

    bool inPedestrianPhase =
        currentState == STATE_PED_GREEN
        || currentState == STATE_PED_BLINK
        || currentState == STATE_PED_RED_WAIT;
    bool inEmergencyPhase =
        currentState == STATE_EMERGENCY_YELLOW
        || currentState == STATE_EMERGENCY_ALL_RED
        || currentState == STATE_EMERGENCY_RED_HOLD;

    // On failsafe entry, ensure pedestrian/red phases transition through yellow first.
    if (inPedestrianPhase && !inEmergencyPhase) {
      switchState(STATE_CAR_YELLOW);
    }
  }

  // ── 3. OPTIONAL LOCAL SENSORS (disabled by default) ─────
#if ENABLE_PRESSURE_SENSOR
  readPressureSensor();
#endif

#if ENABLE_RFID
  checkRFID();
#endif

  // ── 4. TRAFFIC LIGHT STATE MACHINE ──────────────────────
  runStateMachine();

  // ── 5. UPDATE OLED TIDAL LANE DISPLAY ───────────────────
  // Refresh only when needed (flag set by command handler)
  // updateOLED() is called from handleSerial1() on lane change

  // ── 6. HANDLE RED-LIGHT VIOLATION (legacy local path) ───
#if ENABLE_PRESSURE_SENSOR
  if (redLightViolation) {
    triggerViolationAlert();
    redLightViolation = false;
  }

  // ── 7. CANCEL VIOLATION FLAG ONCE LIGHT TURNS GREEN ─────
  bool carGreen = (currentState == STATE_CAR_GREEN);
  if (carGreen) {
    redLightViolation = false; // clear stale flag when light is green
  }
#endif

  // ── 8. PERIODIC STATUS LOG ──────────────────────────────
  unsigned long now = millis();
  if (now - lastLogTime >= 1000) {
    lastLogTime = now;
    printSystemStatus(now - stateStartTime);
  }
}

// ============================================================
//  SECTION A — SERVER COMMAND HANDLER
//  Source: HTTP GET /stats → "command" field (via ESP8266 WiFi)
//  Commands:
//    CAR_GREEN         — push traffic to car-green cycle
//    PED_GREEN_<sec>   — pedestrian crossing duration (seconds)
//    LANE_STRAIGHT / LEFT / RIGHT / LEFT_STRAIGHT /
//    LANE_RIGHT_STRAIGHT / LEFT_RIGHT / ALL / CLOSED
//    COUNT_xx          — update vehicle count (xx = number)
//    KEEP              — heartbeat only
// ============================================================
bool isRecognizedEsp32Command(const String& cmd) {
  return cmd == "CAR_GREEN"
      || cmd.startsWith("PED_GREEN_")
      || cmd == "EMERGENCY_YELLOW"
      || cmd == "EMERGENCY_ALL_RED"
      || cmd == "EMERGENCY_RED"
      || cmd == "EMERGENCY_CLEAR"
      || cmd == "LANE_STRAIGHT"
      || cmd == "LANE_LEFT"
      || cmd == "LANE_RIGHT"
      || cmd == "LANE_LEFT_STRAIGHT"
      || cmd == "LANE_RIGHT_STRAIGHT"
      || cmd == "LANE_LEFT_RIGHT"
      || cmd == "LANE_ALL"
      || cmd == "LANE_CLOSED"
      || cmd == "LANE_EMERGENCY"
      || cmd.startsWith("COUNT_")
      || cmd == "KEEP";
}

bool isEmergencyPhaseCommand(const String& cmd) {
  return cmd == "EMERGENCY_YELLOW"
      || cmd == "EMERGENCY_ALL_RED"
      || cmd == "EMERGENCY_RED";
}

void processEsp32Command(const String& cmd) {
  if (isRecognizedEsp32Command(cmd)) {
    // Only recognized control packets count as heartbeat.
    lastHeartbeatTime = millis();
    if (failSafeMode) {
      Serial.print(">> [SYSTEM] First valid packet [");
      Serial.print(cmd);
      Serial.println("] — AI mode active.");
      failSafeMode = false;
    }
  }

  // ── Traffic light commands ─────────────────────────────
  if (cmd == "CAR_GREEN") {
    bool emergencyState =
        currentState == STATE_EMERGENCY_YELLOW
        || currentState == STATE_EMERGENCY_ALL_RED
        || currentState == STATE_EMERGENCY_RED_HOLD;

    if (!emergencyState) {
      if (currentState != STATE_CAR_GREEN) {
        if (!forceCarGreenWithYellow) {
          Serial.println(">> [CMD] Priority: switch to car-green cycle.");
        }
        forceCarGreenWithYellow = true;
      }

      // Only transition once; repeated CAR_GREEN polls must not reset countdown.
      if (currentState == STATE_PED_GREEN) {
        switchState(STATE_PED_BLINK);
      }
    }
  }
  else if (cmd.startsWith("PED_GREEN_")) {
    long seconds = cmd.substring(10).toInt();
    if (seconds >= 5 && seconds <= 120) {
      forceCarGreenWithYellow = false;
      Serial.print(">> [CMD] Pedestrian crossing — ");
      Serial.print(seconds);
      Serial.println(" s.");
      requestPedestrianCrossing((unsigned long)seconds * 1000UL);
    } else {
      Serial.print(">> [CMD] Invalid PED_GREEN duration: ");
      Serial.println(cmd);
    }
  }
  else if (cmd == "EMERGENCY_YELLOW") {
    if (!emergencyPriorityEnabled) return;
    emergencyFromServer = true;
    emergencyActive = true;
    forceCarGreenWithYellow = false;
    if (currentState != STATE_EMERGENCY_YELLOW) {
      emergencyStartTime = 0;
      switchState(STATE_EMERGENCY_YELLOW);
    }
  }
  else if (cmd == "EMERGENCY_ALL_RED") {
    if (!emergencyPriorityEnabled) return;
    emergencyFromServer = true;
    emergencyActive = true;
    forceCarGreenWithYellow = false;
    if (currentState != STATE_EMERGENCY_ALL_RED && currentState != STATE_EMERGENCY_RED_HOLD) {
      switchState(STATE_EMERGENCY_ALL_RED);
    }
  }
  else if (cmd == "EMERGENCY_RED") {
    if (!emergencyPriorityEnabled) return;
    emergencyFromServer = true;
    emergencyActive = true;
    forceCarGreenWithYellow = false;
    if (currentState != STATE_EMERGENCY_RED_HOLD) {
      emergencyStartTime = millis();
      switchState(STATE_EMERGENCY_RED_HOLD);
    }
  }
  else if (cmd == "EMERGENCY_CLEAR") {
    emergencyFromServer = false;
    emergencyActive = false;
    emergencyStartTime = 0;
    forceCarGreenWithYellow = false;
    switchState(STATE_PED_RED_WAIT);
  }

  // ── Tidal lane commands ────────────────────────────────
  else if (cmd == "LANE_STRAIGHT")       { setLane(LANE_STRAIGHT); }
  else if (cmd == "LANE_LEFT")           { setLane(LANE_LEFT); }
  else if (cmd == "LANE_RIGHT")          { setLane(LANE_RIGHT); }
  else if (cmd == "LANE_LEFT_STRAIGHT")  { setLane(LANE_LEFT_STRAIGHT); }
  else if (cmd == "LANE_RIGHT_STRAIGHT") { setLane(LANE_RIGHT_STRAIGHT); }
  else if (cmd == "LANE_LEFT_RIGHT")     { setLane(LANE_LEFT_RIGHT); }
  else if (cmd == "LANE_ALL")            { setLane(LANE_ALL); }
  else if (cmd == "LANE_CLOSED")         { setLane(LANE_CLOSED); }
  else if (cmd == "LANE_EMERGENCY")      { setLane(LANE_EMERGENCY); }

  // ── Vehicle count update: "COUNT_8", "COUNT_12", etc. ──
  else if (cmd.startsWith("COUNT_")) {
    int count = cmd.substring(6).toInt();
    carCount = count;
    Serial.print(">> [CMD] Vehicle count updated: ");
    Serial.println(carCount);
  }

  // ── Heartbeat ─────────────────────────────────────────
  else if (cmd == "KEEP") {
    // Heartbeat only — already reset timer above
  }

  else {
    Serial.print(">> [CMD] Unknown command: ");
    Serial.println(cmd);
  }
}

// ── WiFi polling (replaces handleSerial1) ───────────────────

// Poll server every POLL_INTERVAL_MS and dispatch the command.
void pollServer() {
  if (millis() - lastPollMs < POLL_INTERVAL_MS) return;
  lastPollMs = millis();

  String cmd = fetchCommandFromServer();
  if (cmd.length() == 0) {
    // No valid command this poll; keep previous heartbeat timestamp
    // so FAILSAFE can trigger if link/server remains down.
    return;
  }

  if (emergencyFromServer && emergencyActive && !isEmergencyPhaseCommand(cmd)) {
    // The server clears emergencies by reverting command to KEEP/non-emergency.
    processEsp32Command("EMERGENCY_CLEAR");
  }

  // Dispatch the same way as if it arrived on Serial1.
  processEsp32Command(cmd);
}

const char* wifiStatusName(int status) {
  switch (status) {
    case WL_NO_SHIELD: return "WL_NO_SHIELD";
    case WL_IDLE_STATUS: return "WL_IDLE_STATUS";
#ifdef WL_NO_SSID_AVAIL
    case WL_NO_SSID_AVAIL: return "WL_NO_SSID_AVAIL";
#endif
    case WL_CONNECTED: return "WL_CONNECTED";
    case WL_CONNECT_FAILED: return "WL_CONNECT_FAILED";
    default: return "WL_UNKNOWN";
  }
}

bool shouldLogWifiDiag() {
  unsigned long now = millis();
  if (now - lastWifiDiagMs < WIFI_DIAG_INTERVAL_MS) return false;
  lastWifiDiagMs = now;
  return true;
}

bool ensureWiFiConnected() {
  int status = WiFi.status();
  if (status == WL_CONNECTED) {
    if (lastWifiStatus != WL_CONNECTED) {
      Serial.println(F("[WiFi] Link restored"));
      lastWifiStatus = WL_CONNECTED;
    }
    return true;
  }

  if (status != lastWifiStatus) {
    Serial.print(F("[WiFi] Link state="));
    Serial.print(wifiStatusName(status));
    Serial.print(F(" ("));
    Serial.print(status);
    Serial.println(F(")"));
    lastWifiStatus = status;
  }

  unsigned long now = millis();
  if (now < nextWifiReconnectMs) {
    if (shouldLogWifiDiag()) {
      Serial.println(F("[WiFi] Not connected → waiting for reconnect window"));
    }
    return false;
  }

  nextWifiReconnectMs = now + WIFI_RECONNECT_INTERVAL_MS;
  Serial.print(F("[WiFi] Reconnect attempt SSID="));
  Serial.println(WIFI_SSID);
  int beginStatus = WiFi.begin(WIFI_SSID, WIFI_PASS);
  if (beginStatus == WL_CONNECTED || WiFi.status() == WL_CONNECTED) {
    Serial.println(F("[WiFi] Reconnect success"));
    lastWifiStatus = WL_CONNECTED;
    return true;
  }

  if (shouldLogWifiDiag()) {
    Serial.print(F("[WiFi] Reconnect failed state="));
    Serial.print(wifiStatusName(beginStatus));
    Serial.print(F(" ("));
    Serial.print(beginStatus);
    Serial.println(F(")"));
  }
  return false;
}

bool connectStatsSocket(const char*& connectedHost) {
  connectedHost = nullptr;
  if (wifiClient.connected()) {
    wifiClient.stop();
  }

  if (wifiClient.connect(SERVER_HOST, SERVER_PORT)) {
    connectedHost = SERVER_HOST;
    return true;
  }

  if (SERVER_FALLBACK_HOST[0] != '\0') {
    if (wifiClient.connect(SERVER_FALLBACK_HOST, SERVER_PORT)) {
      connectedHost = SERVER_FALLBACK_HOST;
      return true;
    }
  }

  return false;
}

// HTTP GET /stats → parse "command" plus any local stats the Mega still uses.
// Returns empty string on any network/parse error.
String fetchCommandFromServer() {
  if (!ensureWiFiConnected()) {
    if (shouldLogWifiDiag()) {
      Serial.println(F("[WiFi] Not connected → no command"));
    }
    return "";
  }

  const char* connectedHost = nullptr;
  if (!connectStatsSocket(connectedHost)) {
    if (shouldLogWifiDiag()) {
      Serial.print(F("[WiFi] Connect failed host="));
      Serial.print(SERVER_HOST);
      if (SERVER_FALLBACK_HOST[0] != '\0') {
        Serial.print(F(" fallback="));
        Serial.print(SERVER_FALLBACK_HOST);
      }
      Serial.println(F(" → no command"));
    }
    return "";
  }

  if (connectedHost != nullptr
      && SERVER_FALLBACK_HOST[0] != '\0'
      && strcmp(connectedHost, SERVER_HOST) != 0
      && shouldLogWifiDiag()) {
    Serial.print(F("[WiFi] Connected via fallback host "));
    Serial.println(connectedHost);
  }

  // HTTP/1.0 avoids chunked transfer encoding.
  wifiClient.print(F("GET "));
  wifiClient.print(STATS_PATH);
  wifiClient.println(F(" HTTP/1.0"));
  wifiClient.print(F("Host: "));
  wifiClient.print(SERVER_HOST);
  wifiClient.print(F(":"));
  wifiClient.println(SERVER_PORT);
  wifiClient.println(F("Connection: close"));
  wifiClient.println();

  // Wait up to 3 s for response.
  unsigned long t0 = millis();
  while (!wifiClient.available()) {
    if (millis() - t0 > WIFI_HTTP_TIMEOUT_MS) {
      if (shouldLogWifiDiag()) {
        Serial.println(F("[WiFi] HTTP timeout waiting response → no command"));
      }
      wifiClient.stop();
      return "";
    }
  }

  String statusLine = wifiClient.readStringUntil('\n');
  statusLine.trim();
  if (!(statusLine.startsWith("HTTP/1.0 200") || statusLine.startsWith("HTTP/1.1 200"))) {
    if (shouldLogWifiDiag()) {
      Serial.print(F("[WiFi] HTTP status unexpected: "));
      Serial.println(statusLine);
    }
  }

  // Read response body.
  String body = "";
  bool inBody = false;
  while (wifiClient.connected() || wifiClient.available()) {
    String line = wifiClient.readStringUntil('\n');
    if (!inBody) {
      if (line == "\r" || line.length() == 0) inBody = true;
    } else {
      body += line;
    }
  }
  wifiClient.stop();

  String cmd = parseJsonString(body, "command");
  if (cmd.length() == 0) {
    if (shouldLogWifiDiag()) {
      Serial.print(F("[WiFi] Parse failed body_len="));
      Serial.println(body.length());
    }
    return "";
  }

  long carsTotal = parseJsonLong(body, "cars_total", -1);
  if (carsTotal < 0) {
    carsTotal = parseJsonLong(body, "cars", -1);
  }
  if (carsTotal >= 0) {
    carCount = (int)carsTotal;
  }

  int parsedLaneCounts[SERVER_LANE_BUCKETS] = {0, 0, 0};
  int parsedLaneCount = parseJsonIntArray(body, "lane_counts", parsedLaneCounts, SERVER_LANE_BUCKETS);
  if (parsedLaneCount > 0) {
    for (int i = 0; i < SERVER_LANE_BUCKETS; i++) {
      serverLaneCounts[i] = (i < parsedLaneCount) ? parsedLaneCounts[i] : 0;
    }
  }

  String tidalDirection = parseJsonString(body, "tidal_direction");
  if (tidalDirection.length() > 0) {
    serverTidalDirection = tidalDirection;
  }

  long sampleWindow = parseJsonLong(body, "sample_window", -1);
  if (sampleWindow >= 0) {
    serverSampleWindow = (int)sampleWindow;
  }

  String mode = parseJsonString(body, "mode");
  if (mode.length() > 0) {
    mode.trim();
    mode.toUpperCase();
    if (mode == "AUTO" || mode == "MANUAL") {
      if (serverControlMode != mode) {
        serverControlMode = mode;
        Serial.print(F(">> [WiFi] Control mode: "));
        Serial.println(serverControlMode);
      }
    }
  }

  bool parsedEmergencyPriority = parseJsonBool(body, "emergency_priority_active", emergencyPriorityEnabled);
  if (parsedEmergencyPriority != emergencyPriorityEnabled) {
    emergencyPriorityEnabled = parsedEmergencyPriority;
    Serial.print(F(">> [WiFi] Emergency priority: "));
    Serial.println(emergencyPriorityEnabled ? F("ON") : F("OFF"));
    if (!emergencyPriorityEnabled && emergencyActive) {
      emergencyActive = false;
      emergencyFromServer = false;
      emergencyStartTime = 0;
      forceCarGreenWithYellow = false;
      switchState(STATE_PED_RED_WAIT);
    }
  }

  Serial.print(F("[WiFi] cmd="));
  Serial.println(cmd);
  Serial.print(F("{cars_total="));
  Serial.print(carCount);
  Serial.print(F(", lane_counts=("));
  for (int i = 0; i < SERVER_LANE_BUCKETS; i++) {
    if (i > 0) Serial.print(F(","));
    Serial.print(serverLaneCounts[i]);
  }
  Serial.print(F("), tidal_direction="));
  Serial.print(serverTidalDirection);
  Serial.print(F(", sample_window="));
  Serial.print(serverSampleWindow);
  Serial.print(F(", mode="));
  Serial.print(serverControlMode);
  Serial.print(F(", emergency_priority="));
  Serial.print(emergencyPriorityEnabled ? F("ON") : F("OFF"));
  Serial.println(F("}"));
  return cmd;
}

// Extract a JSON string value by key (no JSON library needed).
String parseJsonString(const String& json, const String& key) {
  String needle = "\"" + key + "\":\"";
  int idx = json.indexOf(needle);
  if (idx == -1) {
    needle = "\"" + key + "\": \"";
    idx = json.indexOf(needle);
  }
  if (idx == -1) return "";
  int start = idx + needle.length();
  int end   = json.indexOf('"', start);
  return (end == -1) ? "" : json.substring(start, end);
}

// Extract a JSON integer value by key.
long parseJsonLong(const String& json, const String& key, long fallback) {
  String needle = "\"" + key + "\":";
  int idx = json.indexOf(needle);
  if (idx == -1) return fallback;

  int start = idx + needle.length();
  while (start < json.length() && json[start] == ' ') start++;

  bool negative = false;
  if (start < json.length() && json[start] == '-') {
    negative = true;
    start++;
  }

  int end = start;
  while (end < json.length() && isDigit(json[end])) end++;
  if (end == start) return fallback;

  long value = json.substring(start, end).toInt();
  return negative ? -value : value;
}

bool parseJsonBool(const String& json, const String& key, bool fallback) {
  String needle = "\"" + key + "\":";
  int idx = json.indexOf(needle);
  if (idx == -1) return fallback;

  int start = idx + needle.length();
  while (start < json.length() && json[start] == ' ') start++;
  if (start >= json.length()) return fallback;

  if (json.substring(start, start + 4) == "true") return true;
  if (json.substring(start, start + 5) == "false") return false;
  return fallback;
}

// Extract a JSON integer array value by key (e.g. "lane_counts":[1,2,3]).
// Returns number of parsed integers, up to maxCount.
int parseJsonIntArray(const String& json, const String& key, int* out, int maxCount) {
  if (out == nullptr || maxCount <= 0) return 0;

  String needle = "\"" + key + "\":";
  int idx = json.indexOf(needle);
  if (idx == -1) return 0;

  int start = json.indexOf('[', idx + needle.length());
  if (start == -1) return 0;
  int end = json.indexOf(']', start + 1);
  if (end == -1) return 0;

  int pos = start + 1;
  int count = 0;
  while (pos < end && count < maxCount) {
    while (pos < end && (json[pos] == ' ' || json[pos] == ',')) pos++;
    if (pos >= end) break;

    bool negative = false;
    if (json[pos] == '-') {
      negative = true;
      pos++;
    }

    int digitStart = pos;
    while (pos < end && isDigit(json[pos])) pos++;
    if (digitStart == pos) {
      while (pos < end && json[pos] != ',') pos++;
      continue;
    }

    int value = json.substring(digitStart, pos).toInt();
    out[count++] = negative ? -value : value;
    while (pos < end && json[pos] != ',') pos++;
    if (pos < end && json[pos] == ',') pos++;
  }

  return count;
}

// ============================================================
//  SECTION B — PRESSURE SENSOR
//  Legacy local path (ENABLE_PRESSURE_SENSOR=1).
//  Detects vehicle at stop-line.
//  - Red-light violation: pressure detected while car light is red
//  - Traffic jam: vehicle held > JAM_DURATION_THRESHOLD µs AND
//                 car count exceeds threshold
// ============================================================
void readPressureSensor() {
  int pressure = analogRead(PRESSURE_PIN);
  bool redIsOn = (currentState == STATE_PED_GREEN ||
                  currentState == STATE_PED_BLINK  ||
                  currentState == STATE_PED_RED_WAIT);

  if (pressure > PRESSURE_THRESHOLD) {
    if (!pressureOn) {
      pressureOn       = true;
      pressureStartUs  = micros();

      // Red-light violation: vehicle crosses stop line on red
      if (redIsOn) {
        redLightViolation = true;
        Serial.println("!! [VIOLATION] Vehicle crossed stop line on RED !!");
      }
    }
    else {
      pressureDuration = micros() - pressureStartUs;
      detect_jam();
    }
  }
  else {
    if (pressureOn) {
      pressureDuration = micros() - pressureStartUs;
      pressureOn       = false;
      detect_jam();
    }
  }

  // Release jam cooling period after COOLING_PERIOD_DURATION µs
  if (coolingPeriod &&
      (micros() - lastJamTimeUs > COOLING_PERIOD_DURATION)) {
    coolingPeriod = false;
    Serial.println("[INFO] Jam cooling period ended.");
  }
}

void detect_jam(){
  // Traffic jam detection: vehicle sat stationary for too long
  if (pressureDuration > JAM_DURATION_THRESHOLD &&
      carCount         > CAR_COUNT_JAM_THRESHOLD) {
        jam            = true;
        lastJamTimeUs  = micros();
        coolingPeriod  = true;
        Serial.println("!! [JAM] Traffic jam detected (local log only).");
      }
  else if (!coolingPeriod) {
    jam = false;
  }
}


// ============================================================
//  SECTION C — ILLUMINANCE SENSOR
//  Adjusts the LED brightness PWM based on ambient light.
// ============================================================
void BrightnessControl(){
  illuminance = analogRead(ILLUMINANCE_PIN);
  if (illuminance >= ILLUM_UPPER) {
    brightness = 255;
  }
  else if (illuminance <= ILLUM_LOWER) {
    brightness = MIN_BRIGHTNESS;
  }
  else {
    brightness = map(illuminance, ILLUM_LOWER, ILLUM_UPPER, MIN_BRIGHTNESS, 255);
  }
}

// ============================================================
//  SECTION D — RFID EMERGENCY VEHICLE DETECTION
//  Legacy local path (ENABLE_RFID=1).
//  Reads MFRC522. If a known emergency UID is detected,
//  the system enters emergency 3-phase sequence:
//  EMERGENCY_YELLOW -> EMERGENCY_ALL_RED -> EMERGENCY_RED_HOLD.
//  Note: EMERGENCY_RED_HOLD keeps a green corridor for the emergency direction.
// ============================================================
void checkRFID() {
#if !ENABLE_RFID
  return;
#else
  if (!emergencyPriorityEnabled) {
    return;
  }

  if (emergencyActive) {
    if (currentState == STATE_EMERGENCY_RED_HOLD &&
        (millis() - emergencyStartTime > EMERGENCY_DURATION)) {
      emergencyActive = false;
      emergencyFromServer = false;
      emergencyStartTime = 0;
      Serial.println("[RFID] Emergency period ended — resuming normal cycle.");
      switchState(STATE_PED_RED_WAIT);
    }
    return;
  }

  // Try to detect a new card
  if (!rfid.PICC_IsNewCardPresent()) return;
  if (!rfid.PICC_ReadCardSerial())   return;

  // Check UID against known emergency tags
  bool isEmergency = false;
  for (int t = 0; t < NUM_EMERGENCY_TAGS; t++) {
    bool match = true;
    for (int b = 0; b < 4; b++) {
      if (rfid.uid.uidByte[b] != EMERGENCY_UIDS[t][b]) {
        match = false;
        break;
      }
    }
    if (match) { isEmergency = true; break; }
  }

  if (isEmergency) {
    Serial.println("[RFID] *** EMERGENCY VEHICLE DETECTED — Override! ***");
    emergencyFromServer = false;
    emergencyActive    = true;
    emergencyStartTime = 0;
    switchState(STATE_EMERGENCY_YELLOW);
  }
  else {
    // Log unknown tag UID for debugging
    Serial.print("[RFID] Unknown tag: ");
    for (byte i = 0; i < rfid.uid.size; i++) {
      if (rfid.uid.uidByte[i] < 0x10) Serial.print("0");
      Serial.print(rfid.uid.uidByte[i], HEX);
      Serial.print(" ");
    }
    Serial.println();
  }

  rfid.PICC_HaltA();
  rfid.PCD_StopCrypto1();
#endif
}

// ============================================================
//  SECTION E — TRAFFIC LIGHT STATE MACHINE
// ============================================================
void runStateMachine() {
  unsigned long now          = millis();
  unsigned long timeInState  = now - stateStartTime;

  switch (currentState) {

    // Car Green — vehicles move, pedestrians wait
    // Car #2 cross-direction: RED
    case STATE_CAR_GREEN:
      setLights(0, 1, 0,  1, 0, 0);
      setCar2Lights(1, 0, 0);
      forceCarGreenWithYellow = false;
      if (failSafeMode && timeInState > FAILSAFE_CAR_GREEN) {
        pedGreenDuration = 15000;
        switchState(STATE_CAR_YELLOW);
      }
      break;

    // Car Yellow — short warning before red
    // Car #2 cross-direction: YELLOW (also transitioning)
    case STATE_CAR_YELLOW:
      setLights(0, 0, 1,  1, 0, 0);
      setCar2Lights(0, 0, 1);
      if (timeInState > YELLOW_DURATION) {
        if (forceCarGreenWithYellow) switchState(STATE_CAR_GREEN);
        else switchState(STATE_PED_GREEN);
      }
      break;

    // Pedestrian Green — Car #1 red, Car #2 gets GREEN (cross traffic moves)
    case STATE_PED_GREEN:
      setLights(1, 0, 0,  0, 1, 0);
      setCar2Lights(0, 1, 0);
      if (timeInState > pedGreenDuration) switchState(STATE_PED_BLINK);
      break;

    // Pedestrian Blinking (warning — clear the crossing)
    // Car #2 cross-direction: YELLOW (warning, about to go red)
    case STATE_PED_BLINK:
      if ((timeInState / 500) % 2 == 0) setLights(1, 0, 0,  0, 1, 0);
      else                              setLights(1, 0, 0,  0, 0, 0);
      setCar2Lights(0, 0, 1);
      if (timeInState > PED_BLINK_DURATION) switchState(STATE_PED_RED_WAIT);
      break;

    // All-red buffer before giving cars the green
    // Car #2 cross-direction: RED (all-red safety gap)
    case STATE_PED_RED_WAIT:
      setLights(1, 0, 0,  1, 0, 0);
      setCar2Lights(1, 0, 0);
      if (timeInState > PED_RED_WAIT_DUR) {
        if (forceCarGreenWithYellow) switchState(STATE_CAR_YELLOW);
        else switchState(STATE_CAR_GREEN);
      }
      break;

    // Emergency states — Car #2 stays RED throughout
    case STATE_EMERGENCY_YELLOW:
      setLights(0, 0, 1,  1, 0, 0);   // car Yellow on, ped Red on
      setCar2Lights(1, 0, 0);
      if (timeInState > EMERGENCY_YELLOW_DUR) switchState(STATE_EMERGENCY_ALL_RED);
      break;

    case STATE_EMERGENCY_ALL_RED:
      setLights(1, 0, 0,  1, 0, 0);
      setCar2Lights(1, 0, 0);
      if (timeInState > EMERGENCY_ALL_RED_DUR) {
        emergencyStartTime = millis();
        switchState(STATE_EMERGENCY_RED_HOLD);
      }
      break;

    case STATE_EMERGENCY_RED_HOLD:
      // Hold a green corridor for emergency vehicles.
      setLights(0, 1, 0,  1, 0, 0);
      setCar2Lights(1, 0, 0);
      break;
  }
}

// ============================================================
//  SECTION F — RED-LIGHT VIOLATION ALERT (legacy local path)
//  Mega no longer uplinks events to ESP32; this remains a log hook
//  when ENABLE_PRESSURE_SENSOR is enabled for local diagnostics.
// ============================================================
void triggerViolationAlert() {
  Serial.println("[ALERT] Local red-light violation detected.");
}

// ============================================================
//  SECTION G — TIDAL LANE OLED DISPLAY
// ============================================================
void setLane(TidalLane lane) {
  if (lane == currentLane) return;
  currentLane = lane;
  Serial.print(">> [LANE] Changed to: ");
  Serial.println(laneLabel(lane));
#if ENABLE_OLED
  updateOLED();
#endif
}

void updateOLED() {
#if !ENABLE_OLED
  return;
#else
  display.clearDisplay();

  switch (currentLane) {
    case LANE_STRAIGHT:       drawStraight();      break;
    case LANE_LEFT:           drawLeft();          break;
    case LANE_RIGHT:          drawRight();         break;
    case LANE_LEFT_STRAIGHT:  drawLeftStraight();  break;
    case LANE_RIGHT_STRAIGHT: drawRightStraight(); break;
    case LANE_LEFT_RIGHT:     drawLeftRight();     break;
    case LANE_ALL:            drawAll();           break;
    case LANE_CLOSED:         drawClosed();        break;
    case LANE_EMERGENCY:      writeEmergency();        break;
  }

  display.display();
#endif
}

// ── OLED arrow drawing helpers ─────────────────────────────
// (pixel geometry preserved from original main.ino)

#if ENABLE_OLED
void drawStraight() {
  display.fillRect(59, 17, 10, 42, WHITE);
  display.fillTriangle(64,17, 51,17, 51,39, WHITE);
  display.fillTriangle(64,17, 77,17, 77,39, WHITE);
  display.fillTriangle(64,17, 51,17, 64,5,  WHITE);
  display.fillTriangle(64,17, 77,17, 64,5,  WHITE);
}

void drawLeft() {
  display.fillRect(73,16, 10,40, WHITE);
  display.fillRect(57,16, 16,10, WHITE);
  display.fillTriangle(57,21, 57,34, 69,34, WHITE);
  display.fillTriangle(57,21, 57,8,  69,8,  WHITE);
  display.fillTriangle(57,21, 57,34, 45,21, WHITE);
  display.fillTriangle(57,21, 57,8,  45,21, WHITE);
}

void drawRight() {
  display.fillRect(45,16, 10,40, WHITE);
  display.fillRect(55,16, 16,10, WHITE);
  display.fillTriangle(71,21, 71,34, 59,34, WHITE);
  display.fillTriangle(71,21, 71,8,  59,8,  WHITE);
  display.fillTriangle(71,21, 71,34, 83,21, WHITE);
  display.fillTriangle(71,21, 71,8,  83,21, WHITE);
}

void drawLeftStraight() {
  // Left arrow
  display.fillRect(51,41, 20,10, WHITE);
  display.fillTriangle(51,46, 51,59, 63,59, WHITE);
  display.fillTriangle(51,46, 51,33, 63,33, WHITE);
  display.fillTriangle(51,46, 51,59, 39,46, WHITE);
  display.fillTriangle(51,46, 51,33, 39,46, WHITE);
  // Straight arrow
  display.fillRect(71,17, 10,42, WHITE);
  display.fillTriangle(76,17, 63,17, 63,29, WHITE);
  display.fillTriangle(76,17, 89,17, 89,29, WHITE);
  display.fillTriangle(76,17, 63,17, 76,5,  WHITE);
  display.fillTriangle(76,17, 89,17, 76,5,  WHITE);
}

void drawRightStraight() {
  // Right arrow
  display.fillRect(57,41, 20,10, WHITE);
  display.fillTriangle(77,46, 77,59, 65,59, WHITE);
  display.fillTriangle(77,46, 77,33, 65,33, WHITE);
  display.fillTriangle(77,46, 77,59, 89,46, WHITE);
  display.fillTriangle(77,46, 77,33, 89,46, WHITE);
  // Straight arrow
  display.fillRect(47,17, 10,42, WHITE);
  display.fillTriangle(52,17, 39,17, 39,29, WHITE);
  display.fillTriangle(52,17, 65,17, 65,29, WHITE);
  display.fillTriangle(52,17, 39,17, 52,5,  WHITE);
  display.fillTriangle(52,17, 65,17, 52,5,  WHITE);
}

void drawLeftRight() {
  // Left arrow
  display.fillRect(43,16, 16,10, WHITE);
  display.fillTriangle(43,21, 43,34, 55,34, WHITE);
  display.fillTriangle(43,21, 43,8,  55,8,  WHITE);
  display.fillTriangle(43,21, 43,34, 31,21, WHITE);
  display.fillTriangle(43,21, 43,8,  31,21, WHITE);
  // Right arrow
  display.fillRect(59,16, 10,40, WHITE);
  display.fillRect(69,16, 16,10, WHITE);
  display.fillTriangle(85,21, 85,34, 73,34, WHITE);
  display.fillTriangle(85,21, 85,8,  73,8,  WHITE);
  display.fillTriangle(85,21, 85,34, 97,21, WHITE);
  display.fillTriangle(85,21, 85,8,  97,21, WHITE);
}

void drawAll() {
  // Left arrow
  display.fillRect(39,41, 20,10, WHITE);
  display.fillTriangle(39,46, 39,59, 51,59, WHITE);
  display.fillTriangle(39,46, 39,33, 51,33, WHITE);
  display.fillTriangle(39,46, 39,59, 27,46, WHITE);
  display.fillTriangle(39,46, 39,33, 27,46, WHITE);
  // Straight arrow
  display.fillRect(59,17, 10,42, WHITE);
  display.fillTriangle(64,17, 51,17, 51,29, WHITE);
  display.fillTriangle(64,17, 77,17, 77,29, WHITE);
  display.fillTriangle(64,17, 51,17, 64,5,  WHITE);
  display.fillTriangle(64,17, 77,17, 64,5,  WHITE);
  // Right arrow
  display.fillRect(69,41, 20,10, WHITE);
  display.fillTriangle(89,46, 89,59, 77,59, WHITE);
  display.fillTriangle(89,46, 89,33, 77,33, WHITE);
  display.fillTriangle(89,46, 89,59, 101,46, WHITE);
  display.fillTriangle(89,46, 89,33, 101,46, WHITE);
}

void drawClosed() {
  // X symbol (road closed)
  display.fillTriangle(44,7,  39,12, 84,57, WHITE);
  display.fillTriangle(44,7,  84,57, 89,52, WHITE);
  display.fillTriangle(44,57, 39,52, 84,7,  WHITE);
  display.fillTriangle(44,57, 84,7,  89,12, WHITE);
}

void writeEmergency() {
  // text emergency
  display.setTextSize(4);
  display.setTextColor(WHITE);
  display.setCursor(0, 20);
  display.println("EMERGENCY VEHICLES ONLY!");
}
#endif

// ============================================================
//  SECTION H — HELPER FUNCTIONS
// ============================================================

void requestPedestrianCrossing(unsigned long duration) {
  if (currentState == STATE_CAR_GREEN && !emergencyActive) {
    pedGreenDuration = duration;
    switchState(STATE_CAR_YELLOW);
  }
}

void switchState(TrafficState newState) {
  currentState    = newState;
  stateStartTime  = millis();
  printSystemStatus(0);
}

bool isSoftwarePwmOn(int level) {
  if (level <= 0) return false;
  if (level >= 255) return true;
  unsigned long phaseUs = micros() % SOFTWARE_PWM_PERIOD_US;
  unsigned long onWindowUs = ((unsigned long)level * SOFTWARE_PWM_PERIOD_US) / 255UL;
  return phaseUs < onWindowUs;
}

void writeLampPin(uint8_t pin, int enabled) {
  int level = enabled ? brightness : 0;
  digitalWrite(pin, isSoftwarePwmOn(level) ? HIGH : LOW);
}

// Sets traffic light LEDs — scaled by ambient brightness.
// These pins are not hardware-PWM pins on Mega, so use software PWM.
// Parameters: car (R,G,Y), pedestrian (R,G,Y)  — 0 = off, 1 = on
// Car #2 is controlled separately via setCar2Lights().
void setLights(int cr, int cg, int cy, int pr, int pg, int py) {
  // Car #1
  writeLampPin(CAR_RED_PIN,    cr);
  writeLampPin(CAR_GREEN_PIN,  cg);
  writeLampPin(CAR_YELLOW_PIN, cy);
  // Pedestrian
  writeLampPin(PED_RED_PIN,    pr);
  writeLampPin(PED_GREEN_PIN,  pg);
  writeLampPin(PED_YELLOW_PIN, py);
}

// Sets Car #2 (showcase / cross-road direction) LEDs independently.
void setCar2Lights(int r, int g, int y) {
  writeLampPin(CAR2_RED_PIN,    r);
  writeLampPin(CAR2_GREEN_PIN,  g);
  writeLampPin(CAR2_YELLOW_PIN, y);
}

String laneLabel(TidalLane lane) {
  switch (lane) {
    case LANE_STRAIGHT:       return "STRAIGHT";
    case LANE_LEFT:           return "LEFT";
    case LANE_RIGHT:          return "RIGHT";
    case LANE_LEFT_STRAIGHT:  return "LEFT+STRAIGHT";
    case LANE_RIGHT_STRAIGHT: return "RIGHT+STRAIGHT";
    case LANE_LEFT_RIGHT:     return "LEFT+RIGHT";
    case LANE_ALL:            return "ALL";
    case LANE_CLOSED:         return "CLOSED";
    case LANE_EMERGENCY:      return "EMERGENCY";
    default:                  return "UNKNOWN";
  }
}

void printSystemStatus(unsigned long timeInState) {
  String modeStr;
  if (failSafeMode) {
    modeStr = "[Failsafe]";
  } else if (serverControlMode == "MANUAL") {
    modeStr = "[MANUAL]";
  } else {
    modeStr = "[AI-Smart]";
  }
  String emgStr   = emergencyActive ? " [EMERGENCY]" : "";
  String jamStr   = jam             ? " [JAM]"       : "";
  String lightStr;
  long   remaining = 0;

  switch (currentState) {
    case STATE_CAR_GREEN:
      lightStr  = "Car:GRN | Ped:RED";
      remaining = failSafeMode
                  ? ((long)FAILSAFE_CAR_GREEN - (long)timeInState) / 1000
                  : -1;
      break;
    case STATE_CAR_YELLOW:
      lightStr  = "Car:YEL | Ped:RED";
      remaining = ((long)YELLOW_DURATION   - (long)timeInState) / 1000;
      break;
    case STATE_PED_GREEN:
      lightStr  = "Car:RED | Ped:GRN";
      remaining = ((long)pedGreenDuration  - (long)timeInState) / 1000;
      break;
    case STATE_PED_BLINK:
      lightStr  = "Car:RED | Ped:BLK";
      remaining = ((long)PED_BLINK_DURATION - (long)timeInState) / 1000;
      break;
    case STATE_PED_RED_WAIT:
      lightStr  = "Car:RED | Ped:RED";
      remaining = ((long)PED_RED_WAIT_DUR  - (long)timeInState) / 1000;
      break;
    case STATE_EMERGENCY_YELLOW:
      lightStr  = "Emergency:YELLOW";
      remaining = ((long)EMERGENCY_YELLOW_DUR - (long)timeInState) / 1000;
      break;
    case STATE_EMERGENCY_ALL_RED:
      lightStr  = "Emergency:ALL_RED";
      remaining = ((long)EMERGENCY_ALL_RED_DUR - (long)timeInState) / 1000;
      break;
    case STATE_EMERGENCY_RED_HOLD:
      lightStr  = "Emergency:GREEN_HOLD";
      remaining = ((long)EMERGENCY_DURATION - (long)(millis() - emergencyStartTime)) / 1000;
      break;
  }

  String waitingLabel = (serverControlMode == "MANUAL")
                        ? "Awaiting manual cmd..."
                        : "Awaiting AI cmd...";
  String timeStr  = (remaining < 0) ? waitingLabel : String(remaining) + "s";
  String laneStr  = " | Lane:" + laneLabel(currentLane);

  Serial.print(modeStr); Serial.print(emgStr); Serial.print(jamStr);
  Serial.print(" "); Serial.print(lightStr);
  Serial.print(laneStr);
  Serial.print(" >> "); Serial.println(timeStr);
}
