// ============================================================
//  Arduino Mega 2560 — Unified Traffic Control System
//  Week 10 Integration: ESP32 Camera + Pressure Sensor + RFID
// ------------------------------------------------------------
//  Serial Ports
//    Serial  (USB)   — Debug monitor
//    Serial1 (19/18) — Receive commands FROM ESP32
//    Serial2 (17/16) — Send alerts    TO   ESP32 (e.g. violations)
//
//  Traffic LEDs  — Pins 22-27 (RGB for Car + Pedestrian)
//  RFID (SPI)    — SS=53, RST=49, MOSI=51, MISO=50, SCK=52
//  OLED (I2C)    — SDA=20, SCL=21
//  Pressure      — A0
//  Illuminance   — A1
// ============================================================

// ───────────────────── FEATURE FLAGS ────────────────────────
// 1 = enabled, 0 = disabled
#ifndef ENABLE_RFID
#define ENABLE_RFID 1
#endif

#ifndef ENABLE_OLED
#define ENABLE_OLED 1
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

// ─────────────────────────── PIN MAP ────────────────────────
#define CAR_RED_PIN     22
#define CAR_GREEN_PIN   23
#define CAR_BLUE_PIN    24
#define PED_RED_PIN     25
#define PED_GREEN_PIN   26
#define PED_BLUE_PIN    27

#define RFID_SS_PIN     53
#define RFID_RST_PIN    49

#define PRESSURE_PIN    A0
#define ILLUMINANCE_PIN A1

// ─────────────────────────── CONSTANTS ──────────────────────
// Pressure sensor
#define PRESSURE_THRESHOLD         60       // ADC counts
#define JAM_DURATION_THRESHOLD     60000000UL  // 60 s in µs
#define COOLING_PERIOD_DURATION   300000000UL  // 300 s in µs
#define CAR_COUNT_JAM_THRESHOLD    10       // vehicles on road

// Illuminance (0-255 ADC range assumed; scale to your sensor)
#define ILLUM_UPPER  100
#define ILLUM_LOWER   40

// Timing (ms)
#define FAILSAFE_TIMEOUT   5000UL   // lose ESP32 heartbeat → failsafe
#define EMERGENCY_DURATION 15000UL  // RFID emergency green duration
#define YELLOW_DURATION     3000UL
#define PED_BLINK_DURATION  4000UL
#define PED_RED_WAIT_DUR    2000UL
#define FAILSAFE_CAR_GREEN 30000UL  // car green time when no AI signal

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
  STATE_EMERGENCY       // RFID emergency-vehicle override
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
unsigned long emergencyStartTime = 0;

// --- Pressure sensor ---
bool     pressureOn        = false;
unsigned long pressureStartUs  = 0;
unsigned long pressureDuration = 0;
bool     jam               = false;
bool     coolingPeriod     = false;
unsigned long lastJamTimeUs    = 0;

// Whether a red-light violation was detected this vehicle pass
bool redLightViolation = false;

// Car count: updated via [COUNT_xx] packets from ESP32 camera
int carCount = 0;

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
  Serial.begin(115200);   // USB debug
  Serial1.begin(115200);  // ESP32 → Mega (receive commands)
  Serial2.begin(115200);  // Mega → ESP32 (send violation alerts)

  // Traffic LED pins
  pinMode(CAR_RED_PIN,   OUTPUT);
  pinMode(CAR_GREEN_PIN, OUTPUT);
  pinMode(CAR_BLUE_PIN,  OUTPUT);
  pinMode(PED_RED_PIN,   OUTPUT);
  pinMode(PED_GREEN_PIN, OUTPUT);
  pinMode(PED_BLUE_PIN,  OUTPUT);

  // RFID
#if ENABLE_RFID
  SPI.begin();
  rfid.PCD_Init();
  Serial.println("[RFID] Module initialised.");
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
  Serial.println("    Inputs: ESP32 Serial | Pressure A0 | RFID SPI");
}

// ============================================================
//  LOOP
// ============================================================
void loop() {
  BrightnessControl();

  // ── 1. RECEIVE COMMANDS FROM ESP32 ──────────────────────
  handleSerial1();

  // ── 2. CHECK HEARTBEAT / FAILSAFE ───────────────────────
  if (!failSafeMode && (millis() - lastHeartbeatTime > FAILSAFE_TIMEOUT)) {
    Serial.println("!! [WARNING] ESP32 lost — entering Failsafe !!");
    failSafeMode = true;
  }

  // ── 3. READ SENSORS ─────────────────────────────────────
  readPressureSensor();

  // ── 4. CHECK RFID FOR EMERGENCY VEHICLES ────────────────
  checkRFID();

  // ── 5. TRAFFIC LIGHT STATE MACHINE ──────────────────────
  runStateMachine();

  // ── 6. UPDATE OLED TIDAL LANE DISPLAY ───────────────────
  // Refresh only when needed (flag set by command handler)
  // updateOLED() is called from handleSerial1() on lane change

  // ── 7. HANDLE RED-LIGHT VIOLATION ───────────────────────
  if (redLightViolation) {
    triggerViolationAlert();
    redLightViolation = false;
  }

  // ── 8. CANCEL VIOLATION FLAG ONCE LIGHT TURNS GREEN ─────
  bool carGreen = (currentState == STATE_CAR_GREEN || currentState == STATE_EMERGENCY);
  if (carGreen) {
    redLightViolation = false; // clear stale flag when light is green
  }

  // ── 9. PERIODIC STATUS LOG ──────────────────────────────
  unsigned long now = millis();
  if (now - lastLogTime >= 1000) {
    lastLogTime = now;
    printSystemStatus(now - stateStartTime);
  }
}

// ============================================================
//  SECTION A — ESP32 SERIAL COMMAND HANDLER
//  Protocol: [COMMAND] packets on Serial1
//  Commands received:
//    CAR_GREEN         — push traffic to car-green cycle
//    PED_GREEN_10/20/30 — pedestrian crossing duration
//    LANE_STRAIGHT / LEFT / RIGHT / LEFT_STRAIGHT /
//    LANE_RIGHT_STRAIGHT / LEFT_RIGHT / ALL / CLOSED
//    COUNT_xx          — update vehicle count (xx = number)
//    KEEP              — heartbeat only
// ============================================================
void handleSerial1() {
  if (Serial1.available() == 0) return;

  char c = Serial1.read();
  if (c != '[') return;  // ignore noise outside brackets

  String cmd = Serial1.readStringUntil(']');
  cmd.trim();
  if (cmd.length() == 0) return;

  // Valid packet → reset heartbeat
  lastHeartbeatTime = millis();
  if (failSafeMode) {
    Serial.print(">> [SYSTEM] First valid packet [");
    Serial.print(cmd);
    Serial.println("] — AI mode active.");
    failSafeMode = false;
  }

  // ── Traffic light commands ─────────────────────────────
  if (cmd == "CAR_GREEN") {
    if (currentState != STATE_CAR_GREEN && currentState != STATE_CAR_YELLOW
        && currentState != STATE_EMERGENCY) {
      Serial.println(">> [CMD] Priority: switch to car-green cycle.");
      switchState(STATE_PED_BLINK);
    }
  }
  else if (cmd == "PED_GREEN_10") {
    Serial.println(">> [CMD] Pedestrian crossing — 10 s.");
    requestPedestrianCrossing(10000);
  }
  else if (cmd == "PED_GREEN_20") {
    Serial.println(">> [CMD] Pedestrian crossing — 20 s.");
    requestPedestrianCrossing(20000);
  }
  else if (cmd == "PED_GREEN_30") {
    Serial.println(">> [CMD] Wheelchair priority — 30 s.");
    requestPedestrianCrossing(30000);
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

// ============================================================
//  SECTION B — PRESSURE SENSOR
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
        Serial.println("!! [JAM] Traffic jam detected — notifying ESP32.");
        Serial2.println("[JAM_DETECTED]");
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
  illuminance = analogRead(A1);
  if(illuminance > ILLUM_UPPER){
    brightness = 255;
  }
  else if(illuminance < ILLUM_LOWER){
    brightness = 135;
  }
  else {
    brightness = illuminance * 2 + 55;
  }
}

// ============================================================
//  SECTION D — RFID EMERGENCY VEHICLE DETECTION
//  Reads MFRC522. If a known emergency UID is detected,
//  the system immediately switches to STATE_EMERGENCY
//  (car gets green) for EMERGENCY_DURATION ms.
// ============================================================
void checkRFID() {
#if !ENABLE_RFID
  return;
#else
  // Check if emergency already active and has expired
  if (emergencyActive &&
      (millis() - emergencyStartTime > EMERGENCY_DURATION)) {
    emergencyActive = false;
    Serial.println("[RFID] Emergency period ended — resuming normal cycle.");
    switchState(STATE_CAR_YELLOW);  // transition through yellow
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
    Serial2.println("[EMERGENCY_DETECTED]");  // notify ESP32
    emergencyActive    = true;
    emergencyStartTime = millis();
    switchState(STATE_EMERGENCY);
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
    case STATE_CAR_GREEN:
      setLights(0, 1, 0,  1, 0, 0);
      if (failSafeMode && timeInState > FAILSAFE_CAR_GREEN) {
        pedGreenDuration = 15000;
        switchState(STATE_CAR_YELLOW);
      }
      break;

    // Car Yellow — short warning before red
    case STATE_CAR_YELLOW:
      setLights(0, 0, 1,  1, 0, 0);
      if (timeInState > YELLOW_DURATION) switchState(STATE_PED_GREEN);
      break;

    // Pedestrian Green
    case STATE_PED_GREEN:
      setLights(1, 0, 0,  0, 1, 0);
      if (timeInState > pedGreenDuration) switchState(STATE_PED_BLINK);
      break;

    // Pedestrian Blinking (warning — clear the crossing)
    case STATE_PED_BLINK:
      if ((timeInState / 500) % 2 == 0) setLights(1, 0, 0,  0, 1, 0);
      else                              setLights(1, 0, 0,  0, 0, 0);
      if (timeInState > PED_BLINK_DURATION) switchState(STATE_PED_RED_WAIT);
      break;

    // All-red buffer before giving cars the green
    case STATE_PED_RED_WAIT:
      setLights(1, 0, 0,  1, 0, 0);
      if (timeInState > PED_RED_WAIT_DUR) switchState(STATE_CAR_GREEN);
      break;

    // EMERGENCY OVERRIDE — car green held until timer expires
    // (timer managed in checkRFID)
    case STATE_EMERGENCY:
      setLights(0, 1, 0,  1, 0, 0);   // Car: Green, Ped: Red
      // Flicker blue to signal emergency mode
      if ((timeInState / 300) % 2 == 0) {
        analogWrite(CAR_BLUE_PIN, brightness / 3);  // subtle blue pulse
      } else {
        analogWrite(CAR_BLUE_PIN, 0);
      }
      break;
  }
}

// ============================================================
//  SECTION F — RED-LIGHT VIOLATION ALERT
//  Sends a [VIOLATION] packet to ESP32 via Serial2 so that
//  the ESP32 can trigger its camera to capture the plate.
// ============================================================
void triggerViolationAlert() {
  Serial2.println("[VIOLATION]");   // ESP32 listens for this on its UART
  Serial.println("[ALERT] Violation packet sent to ESP32 camera.");
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
  if (currentState == STATE_CAR_GREEN) {
    pedGreenDuration = duration;
    switchState(STATE_CAR_YELLOW);
  }
}

void switchState(TrafficState newState) {
  currentState    = newState;
  stateStartTime  = millis();
  printSystemStatus(0);
}

// Sets traffic light LEDs — scaled by ambient brightness
// Parameters: car (R,G,B), pedestrian (R,G,B)  — 0 = off, 1 = on
void setLights(int cr, int cg, int cb, int pr, int pg, int pb) {
  analogWrite(CAR_RED_PIN,   cr ? brightness : 0);
  analogWrite(CAR_GREEN_PIN, cg ? brightness : 0);
  analogWrite(CAR_BLUE_PIN,  cb ? brightness : 0);
  analogWrite(PED_RED_PIN,   pr ? brightness : 0);
  analogWrite(PED_GREEN_PIN, pg ? brightness : 0);
  analogWrite(PED_BLUE_PIN,  pb ? brightness : 0);
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
  String modeStr  = failSafeMode    ? "[Failsafe]" : "[AI-Smart]";
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
    case STATE_EMERGENCY:
      lightStr  = "Car:GRN | Ped:RED";
      remaining = ((long)EMERGENCY_DURATION -
                   (long)(millis() - emergencyStartTime)) / 1000;
      break;
  }

  String timeStr  = (remaining < 0) ? "Awaiting AI cmd..." : String(remaining) + "s";
  String laneStr  = " | Lane:" + laneLabel(currentLane);

  Serial.print(modeStr); Serial.print(emgStr); Serial.print(jamStr);
  Serial.print(" "); Serial.print(lightStr);
  Serial.print(laneStr);
  Serial.print(" >> "); Serial.println(timeStr);
}
