// ============================================================
//  ESP32-S3 CAM — Car Detection + Local Sensor Events
// ------------------------------------------------------------
//  SAFE UART WIRING (one-way only):
//    ESP32 TX0  ──> Mega RX1 (pin 19)
//    Mega TX*   ──X  NOT connected to ESP32 RX (avoid 5V -> 3.3V risk)
//    ESP32 GND  <──> Mega GND
//
//  SENSOR WIRING (migrated from Mega to ESP32):
//    Pressure sensor (analog out) -> PRESSURE_PIN (GPIO35 by default), 3V3, GND
//    RFID MFRC522 (SPI)           -> SS/RST/SCK/MISO/MOSI pins below, 3V3, GND
//
//  Runtime flow:
//    - VGA frames -> /detect_car -> command -> [CMD] forwarded to Mega
//    - Pressure red-light event  -> queue violation capture -> /capture_violation
//    - RFID emergency UID         -> /trigger_emergency, auto clear -> /clear_emergency
// ============================================================

#ifndef ENABLE_PRESSURE_SENSOR
#define ENABLE_PRESSURE_SENSOR 1
#endif

#ifndef ENABLE_RFID_SENSOR
#define ENABLE_RFID_SENSOR 1
#endif

#ifndef ENABLE_UART_DEBUG
#define ENABLE_UART_DEBUG 0
#endif

#include "esp_camera.h"
#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>

#if ENABLE_RFID_SENSOR
  #include <SPI.h>
  #include <MFRC522.h>
#endif

// ─────────────────────── CREDENTIALS ────────────────────────
const char *ssid     = "";
const char *password = "";

// ─────────────────────── SERVER ENDPOINTS ───────────────────
const String serverName          = "http://stl.gyke.net/detect_car";
const String violationServerName = "http://stl.gyke.net/capture_violation";
const String emergencyTriggerUrl = "http://stl.gyke.net/trigger_emergency";
const String emergencyClearUrl   = "http://stl.gyke.net/clear_emergency";
const char* XOR_KEY              = "MyIoTKey2026";

// Keep Mega UART clean: set to 1 only when you explicitly want debug logs
// mixed into the Mega serial link.
#if ENABLE_UART_DEBUG
  #define DBG_PRINT(...)   Serial.print(__VA_ARGS__)
  #define DBG_PRINTLN(...) Serial.println(__VA_ARGS__)
  #define DBG_PRINTF(...)  Serial.printf(__VA_ARGS__)
#else
  #define DBG_PRINT(...)   do {} while (0)
  #define DBG_PRINTLN(...) do {} while (0)
  #define DBG_PRINTF(...)  do {} while (0)
#endif

void sendMegaPacket(const char* cmd) {
  if (cmd == nullptr || cmd[0] == '\0') return;
  Serial.print("[");
  Serial.print(cmd);
  Serial.println("]");
}

// ─────────────────────── CAMERA PINS ────────────────────────
#define PWDN_GPIO_NUM   -1
#define RESET_GPIO_NUM  -1
#define XCLK_GPIO_NUM   15
#define SIOD_GPIO_NUM    4
#define SIOC_GPIO_NUM    5
#define Y9_GPIO_NUM     16
#define Y8_GPIO_NUM     17
#define Y7_GPIO_NUM     18
#define Y6_GPIO_NUM     12
#define Y5_GPIO_NUM     10
#define Y4_GPIO_NUM      8
#define Y3_GPIO_NUM      9
#define Y2_GPIO_NUM     11
#define VSYNC_GPIO_NUM   6
#define HREF_GPIO_NUM    7
#define PCLK_GPIO_NUM   13

// ─────────────────────── SENSOR PINS ────────────────────────
#define PRESSURE_PIN 35

// Adjust these defaults to your exact ESP32-S3-CAM breakout pinout.
#define RFID_SS_PIN  36
#define RFID_RST_PIN 47
#define RFID_SCK_PIN 21
#define RFID_MISO_PIN 2
#define RFID_MOSI_PIN 1

// ─────────────────────── TIMING / THRESHOLDS ────────────────
const int FRAME_INTERVAL     = 200;   // ms between normal detections
const int VIOLATION_COOLDOWN = 2000;  // ms — debounce same trigger
const int MAX_QUEUE          = 5;     // violation capture safety cap
const unsigned long MEGA_FAILSAFE_TIMEOUT_MS = 5000UL;  // keep in sync with Mega FAILSAFE_TIMEOUT

const int PRESSURE_THRESHOLD         = 60;          // 8-bit ADC counts (0-255)
const unsigned long JAM_DURATION_US  = 60000000UL;  // 60 s
const unsigned long JAM_COOLING_US   = 300000000UL; // 300 s
const int CAR_COUNT_JAM_THRESHOLD    = 10;

const unsigned long EMERGENCY_YELLOW_MS      = 3000UL;
const unsigned long EMERGENCY_ALL_RED_MS     = 5000UL;
const unsigned long EMERGENCY_RED_HOLD_MS    = 15000UL;
const unsigned long LOCAL_EMERGENCY_TOTAL_MS = EMERGENCY_YELLOW_MS + EMERGENCY_ALL_RED_MS + EMERGENCY_RED_HOLD_MS;
const unsigned long EMERGENCY_WEBHOOK_GAP_MS = 2000UL;

// ─────────────────────── RFID UIDS ──────────────────────────
#if ENABLE_RFID_SENSOR
#define EMERGENCY_UID_1_B0 0xCC
#define EMERGENCY_UID_1_B1 0x0E
#define EMERGENCY_UID_1_B2 0x40
#define EMERGENCY_UID_1_B3 0x18

#define EMERGENCY_UID_2_B0 0xBA
#define EMERGENCY_UID_2_B1 0x9C
#define EMERGENCY_UID_2_B2 0xA9
#define EMERGENCY_UID_2_B3 0x1A

const byte EMERGENCY_UIDS[][4] = {
  { EMERGENCY_UID_1_B0, EMERGENCY_UID_1_B1, EMERGENCY_UID_1_B2, EMERGENCY_UID_1_B3 },
  { EMERGENCY_UID_2_B0, EMERGENCY_UID_2_B1, EMERGENCY_UID_2_B2, EMERGENCY_UID_2_B3 }
};
const int NUM_EMERGENCY_TAGS = sizeof(EMERGENCY_UIDS) / sizeof(EMERGENCY_UIDS[0]);
MFRC522 rfid(RFID_SS_PIN, RFID_RST_PIN);
#endif

// ─────────────────────── STATE ──────────────────────────────
WiFiClient wifiClient;
unsigned long lastFrameTime = 0;
unsigned long lastViolationTime = 0;
unsigned long lastEmergencyWebhookMs = 0;

volatile int violationQueue = 0;
int carsOnRoad = 0;

bool assumeCarRed = false;  // inferred from latest non-KEEP command sent to Mega
unsigned long lastControlPacketMs = 0;

bool pressureOn = false;
unsigned long pressureStartUs = 0;
unsigned long pressureDurationUs = 0;
bool jamDetected = false;
bool jamCoolingPeriod = false;
unsigned long lastJamTimeUs = 0;

bool emergencyWebhookActive = false;
bool localEmergencyActive = false;
unsigned long localEmergencyStartMs = 0;

// ============================================================
//  SETUP
// ============================================================
void setup() {
  Serial.begin(115200);  // TX0 -> Mega RX1 (one-way only)

#if ENABLE_PRESSURE_SENSOR
  analogReadResolution(8);  // keep threshold scale close to previous Mega tuning
  pinMode(PRESSURE_PIN, INPUT);
#endif

#if ENABLE_RFID_SENSOR
  SPI.begin(RFID_SCK_PIN, RFID_MISO_PIN, RFID_MOSI_PIN, RFID_SS_PIN);
  rfid.PCD_Init();
  DBG_PRINTLN("DBG RFID initialised.");
#else
  DBG_PRINTLN("DBG RFID disabled (ENABLE_RFID_SENSOR=0).");
#endif

  camera_config_t config;
  config.ledc_channel  = LEDC_CHANNEL_0;
  config.ledc_timer    = LEDC_TIMER_0;
  config.pin_d0        = Y2_GPIO_NUM;
  config.pin_d1        = Y3_GPIO_NUM;
  config.pin_d2        = Y4_GPIO_NUM;
  config.pin_d3        = Y5_GPIO_NUM;
  config.pin_d4        = Y6_GPIO_NUM;
  config.pin_d5        = Y7_GPIO_NUM;
  config.pin_d6        = Y8_GPIO_NUM;
  config.pin_d7        = Y9_GPIO_NUM;
  config.pin_xclk      = XCLK_GPIO_NUM;
  config.pin_pclk      = PCLK_GPIO_NUM;
  config.pin_vsync     = VSYNC_GPIO_NUM;
  config.pin_href      = HREF_GPIO_NUM;
  config.pin_sccb_sda  = SIOD_GPIO_NUM;
  config.pin_sccb_scl  = SIOC_GPIO_NUM;
  config.pin_pwdn      = PWDN_GPIO_NUM;
  config.pin_reset     = RESET_GPIO_NUM;
  config.xclk_freq_hz  = 8000000;
  config.pixel_format  = PIXFORMAT_JPEG;
  config.grab_mode     = CAMERA_GRAB_WHEN_EMPTY;
  config.fb_location   = CAMERA_FB_IN_PSRAM;

  if (psramFound()) {
    config.frame_size   = FRAMESIZE_VGA;
    config.jpeg_quality = 12;
    config.fb_count     = 2;
    config.grab_mode    = CAMERA_GRAB_LATEST;
  } else {
    config.frame_size   = FRAMESIZE_VGA;
    config.jpeg_quality = 12;
    config.fb_count     = 1;
    config.fb_location  = CAMERA_FB_IN_DRAM;
  }

  esp_err_t err = esp_camera_init(&config);
  if (err != ESP_OK) {
    DBG_PRINTF("DBG cam init failed: 0x%x\n", err);
    return;
  }

  sensor_t *s = esp_camera_sensor_get();
  if (s != NULL) {
    s->set_aec2(s, 0);
    s->set_ae_level(s, -2);
    s->set_contrast(s, 1);
    s->set_gain_ctrl(s, 1);
    if (s->id.PID == OV3660_PID) s->set_vflip(s, 1);
  }

  WiFi.begin(ssid, password);
  WiFi.setSleep(false);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    DBG_PRINT(".");
  }
  DBG_PRINTLN("\nWi-Fi connected");
  wifiClient.setNoDelay(true);
}

// ============================================================
//  LOOP
// ============================================================
void loop() {
  pollPressureSensor();
  pollRfidSensor();
  refreshEmergencyHold();

  if (violationQueue > 0) {
    violationQueue--;
    DBG_PRINTF("DBG violation capture; queued=%d\n", violationQueue);
    captureViolation();
    return;  // keep queue handling highest priority
  }

  if (WiFi.status() != WL_CONNECTED) {
    WiFi.reconnect();
    delay(500);
    return;
  }

  if (millis() - lastFrameTime < FRAME_INTERVAL) {
    delay(10);
    return;
  }

  sendDetectionFrame();
}

// ============================================================
//  SECTION A — LOCAL SENSOR EVENT GENERATION
// ============================================================
void queueViolationCapture(const char* reason) {
  unsigned long now = millis();
  if (now - lastViolationTime <= VIOLATION_COOLDOWN) {
    DBG_PRINTF("DBG violation ignored (%s); cooldown\n", reason ? reason : "unknown");
    return;
  }

  lastViolationTime = now;
  if (violationQueue < MAX_QUEUE) {
    violationQueue++;
    DBG_PRINTF("DBG violation queued (%s); depth=%d\n", reason ? reason : "unknown", violationQueue);
  } else {
    DBG_PRINTLN("DBG violation queue full; dropped");
  }
}

bool isEmergencyCommand(const char* cmd) {
  return strcmp(cmd, "EMERGENCY_YELLOW") == 0
      || strcmp(cmd, "EMERGENCY_ALL_RED") == 0
      || strcmp(cmd, "EMERGENCY_RED") == 0
      || strcmp(cmd, "EMERGENCY_CLEAR") == 0;
}

void updateCarSignalAssumption(const char* cmd) {
  if (cmd == nullptr || cmd[0] == '\0') return;

  if (strcmp(cmd, "CAR_GREEN") == 0) {
    assumeCarRed = false;
    return;
  }

  if (strncmp(cmd, "PED_GREEN_", 10) == 0 || isEmergencyCommand(cmd)) {
    assumeCarRed = true;
    return;
  }
}

void detectJamFromPressure() {
  if (pressureDurationUs > JAM_DURATION_US && carsOnRoad > CAR_COUNT_JAM_THRESHOLD) {
    if (!jamCoolingPeriod) {
      jamDetected = true;
      jamCoolingPeriod = true;
      lastJamTimeUs = micros();
      DBG_PRINTLN("DBG jam detected by pressure hold.");
    }
  } else if (!jamCoolingPeriod) {
    jamDetected = false;
  }
}

bool hasFreshLightStateAssumption() {
  return lastControlPacketMs > 0
      && (millis() - lastControlPacketMs) <= MEGA_FAILSAFE_TIMEOUT_MS;
}

void pollPressureSensor() {
#if !ENABLE_PRESSURE_SENSOR
  return;
#else
  int pressure = analogRead(PRESSURE_PIN);
  bool pressed = pressure > PRESSURE_THRESHOLD;

  if (pressed) {
    if (!pressureOn) {
      pressureOn = true;
      pressureStartUs = micros();
      if (assumeCarRed && hasFreshLightStateAssumption()) {
        queueViolationCapture("pressure/red");
      }
    } else {
      pressureDurationUs = micros() - pressureStartUs;
      detectJamFromPressure();
    }
  } else if (pressureOn) {
    pressureDurationUs = micros() - pressureStartUs;
    pressureOn = false;
    detectJamFromPressure();
  }

  if (jamCoolingPeriod && (micros() - lastJamTimeUs > JAM_COOLING_US)) {
    jamCoolingPeriod = false;
    jamDetected = false;
    DBG_PRINTLN("DBG jam cooling period ended.");
  }
#endif
}

bool isKnownEmergencyTag() {
#if !ENABLE_RFID_SENSOR
  return false;
#else
  if (rfid.uid.size < 4) return false;

  for (int t = 0; t < NUM_EMERGENCY_TAGS; t++) {
    bool match = true;
    for (int b = 0; b < 4; b++) {
      if (rfid.uid.uidByte[b] != EMERGENCY_UIDS[t][b]) {
        match = false;
        break;
      }
    }
    if (match) return true;
  }
  return false;
#endif
}

void pollRfidSensor() {
#if !ENABLE_RFID_SENSOR
  return;
#else
  if (!rfid.PICC_IsNewCardPresent()) return;
  if (!rfid.PICC_ReadCardSerial()) return;

  bool isEmergency = isKnownEmergencyTag();
  if (isEmergency) {
    if (!localEmergencyActive) {
      sendMegaPacket("EMERGENCY_YELLOW");
      DBG_PRINTLN("DBG RFID emergency detected.");
      triggerEmergencyWebhook();
      localEmergencyActive = true;
      localEmergencyStartMs = millis();
    }
  } else {
    DBG_PRINT("DBG unknown RFID tag: ");
    for (byte i = 0; i < rfid.uid.size; i++) {
      if (rfid.uid.uidByte[i] < 0x10) DBG_PRINT("0");
      DBG_PRINT(rfid.uid.uidByte[i], HEX);
      DBG_PRINT(" ");
    }
    DBG_PRINTLN("");
  }

  rfid.PICC_HaltA();
  rfid.PCD_StopCrypto1();
#endif
}

void refreshEmergencyHold() {
  if (!localEmergencyActive) return;
  if (millis() - localEmergencyStartMs <= LOCAL_EMERGENCY_TOTAL_MS) return;

  localEmergencyActive = false;
  sendMegaPacket("EMERGENCY_CLEAR");
  DBG_PRINTLN("DBG emergency hold elapsed; clearing webhook.");
  clearEmergencyWebhook();
}

// ============================================================
//  SECTION B — VIOLATION CAPTURE
// ============================================================
void captureViolation() {
  if (WiFi.status() != WL_CONNECTED) {
    DBG_PRINTLN("DBG violation dropped; no WiFi");
    return;
  }

  sensor_t *s = esp_camera_sensor_get();
  if (s) {
    s->set_framesize(s, FRAMESIZE_HD);  // 1280x720
    s->set_quality(s, 6);               // lower = sharper JPEG
    s->set_contrast(s, 2);
  }
  delay(150);

  camera_fb_t *discard = esp_camera_fb_get();
  if (discard) esp_camera_fb_return(discard);

  camera_fb_t *fb = esp_camera_fb_get();
  if (!fb) {
    DBG_PRINTLN("DBG violation capture failed; no frame");
    restoreNormalCameraSettings();
    return;
  }

  xorEncrypt(fb->buf, fb->len);

  HTTPClient http;
  http.setReuse(false);
  http.setTimeout(5000);
  http.begin(wifiClient, violationServerName);
  http.addHeader("Content-Type", "application/octet-stream");
  http.addHeader("X-Event-Type", "violation");

  int code = http.POST(fb->buf, fb->len);
  if (code > 0) {
    DBG_PRINTF("DBG violation upload ok; http=%d\n", code);
  } else {
    DBG_PRINTF("DBG violation upload failed; err=%d\n", code);
    wifiClient.stop();
  }

  http.end();
  esp_camera_fb_return(fb);
  restoreNormalCameraSettings();
}

// ============================================================
//  SECTION C — NORMAL DETECTION FRAME
// ============================================================
void sendDetectionFrame() {
  camera_fb_t *fb = esp_camera_fb_get();
  if (!fb) return;

  lastFrameTime = millis();
  xorEncrypt(fb->buf, fb->len);

  HTTPClient http;
  http.setReuse(true);
  http.setTimeout(2000);
  http.begin(wifiClient, serverName);
  http.addHeader("Content-Type", "application/octet-stream");

  int httpResponseCode = http.POST(fb->buf, fb->len);
  if (httpResponseCode > 0) {
    String response = http.getString();
    DynamicJsonDocument doc(512);
    DeserializationError error = deserializeJson(doc, response);

    if (!error) {
      const char* cmd            = doc["command"]         | nullptr;
      int         carsTotal      = doc["cars_total"]      | -1;
      const char* tidalDirection = doc["tidal_direction"] | "UNKNOWN";
      int         sampleWindow   = doc["sample_window"]   | 0;
      JsonArray   laneCounts     = doc["lane_counts"].as<JsonArray>();

      if (carsTotal >= 0) {
        carsOnRoad = carsTotal;
      }
      updateCarSignalAssumption(cmd);

      DBG_PRINT("{cars_total=");
      DBG_PRINT(carsTotal);
      DBG_PRINT(", lane_counts=(");
      for (int i = 0; i < (int)laneCounts.size(); i++) {
        if (i > 0) DBG_PRINT(",");
        DBG_PRINT(laneCounts[i].as<int>());
      }
      DBG_PRINT("), tidal_direction=");
      DBG_PRINT(tidalDirection);
      DBG_PRINT(", sample_window=");
      DBG_PRINT(sampleWindow);
      DBG_PRINT(", car_red_assumed=");
      DBG_PRINT(assumeCarRed ? "true" : "false");
      DBG_PRINTLN("}");

      if (cmd) {
        lastControlPacketMs = millis();
        sendMegaPacket(cmd);
      }
    }
  } else {
    wifiClient.stop();
  }

  http.end();
  esp_camera_fb_return(fb);
}

// ============================================================
//  HELPERS
// ============================================================
void xorEncrypt(uint8_t* buf, size_t len) {
  size_t keyLen   = strlen(XOR_KEY);
  size_t keyIndex = 0;
  for (size_t i = 0; i < len; i++) {
    buf[i] ^= XOR_KEY[keyIndex++];
    if (keyIndex >= keyLen) keyIndex = 0;
  }
}

void restoreNormalCameraSettings() {
  sensor_t *s = esp_camera_sensor_get();
  if (s) {
    s->set_framesize(s, FRAMESIZE_VGA);
    s->set_quality(s, 12);
    s->set_contrast(s, 1);
  }
}

void postEmergencyEvent(const String& url, const char* payload) {
  if (WiFi.status() != WL_CONNECTED) return;

  HTTPClient http;
  http.setReuse(false);
  http.setTimeout(2000);
  http.begin(wifiClient, url);
  http.addHeader("Content-Type", "application/json");
  int code = http.POST(payload);
  if (code <= 0) {
    wifiClient.stop();
  }
  http.end();
}

void triggerEmergencyWebhook() {
  unsigned long now = millis();
  if (emergencyWebhookActive || (now - lastEmergencyWebhookMs < EMERGENCY_WEBHOOK_GAP_MS)) {
    return;
  }
  emergencyWebhookActive = true;
  lastEmergencyWebhookMs = now;
  postEmergencyEvent(emergencyTriggerUrl, "{}");
}

void clearEmergencyWebhook() {
  emergencyWebhookActive = false;
  lastEmergencyWebhookMs = millis();
  postEmergencyEvent(emergencyClearUrl, "{}");
}
