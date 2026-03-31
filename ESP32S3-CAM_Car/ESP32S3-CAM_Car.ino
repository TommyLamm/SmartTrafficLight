// ============================================================
//  ESP32-S3 CAM — Car Detection + Red-Light Violation Capture
// ------------------------------------------------------------
//  Serial TX0 → Mega RX1 (pin 19) : sends [CMD] packets
//  Serial RX0 ← Mega TX2 (pin 16) : receives [VIOLATION] etc.
//
//  Normal mode  : VGA frame every 200ms → POST /detect_car
//                 server JSON response → forward [CMD] to Mega
//  Violation    : [VIOLATION] from Mega → queued → HD capture
//                 → POST /capture_violation (plate reader)
//  Double viol. : violationQueue counter — up to MAX_QUEUE
//                 captures, processed one per loop cycle
// ============================================================

#include "esp_camera.h"
#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>

// ─────────────────────── CREDENTIALS ────────────────────────
const char *ssid     = "Andy";
const char *password = "Andyandy1233";

// ─────────────────────── SERVER ENDPOINTS ───────────────────
const String serverName          = "http://stl.gyke.net/detect_car";
const String violationServerName = "http://stl.gyke.net/capture_violation";

const char* XOR_KEY = "MyIoTKey2026";

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

// ─────────────────────── TIMING ─────────────────────────────
const int FRAME_INTERVAL     = 200;   // ms between normal detections
const int VIOLATION_COOLDOWN = 2000;  // ms — debounce same car crossing

// ─────────────────────── STATE ──────────────────────────────
WiFiClient    wifiClient;
unsigned long lastFrameTime     = 0;
unsigned long lastViolationTime = 0;

// Violation queue — counts how many captures are pending
volatile int  violationQueue    = 0;
const int     MAX_QUEUE         = 5;   // safety cap

// ============================================================
//  SETUP
// ============================================================
void setup() {
  Serial.begin(115200);  // TX0 → Mega RX1  /  RX0 ← Mega TX2

  // ── Camera init ─────────────────────────────────────────
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
    Serial.printf("[CAM] Init failed: 0x%x\n", err);
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

  // ── WiFi ────────────────────────────────────────────────
  WiFi.begin(ssid, password);
  WiFi.setSleep(false);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    // dots have no [] so Mega ignores them
    Serial.print(".");
  }
  Serial.println("\nWi-Fi Connected");
  wifiClient.setNoDelay(true);
}

// ============================================================
//  LOOP
// ============================================================
void loop() {

  // ── 1. CHECK FOR SIGNALS FROM MEGA ──────────────────────
  checkMegaSerial();

  // ── 2. VIOLATION QUEUE (highest priority) ────────────────
  if (violationQueue > 0) {
    violationQueue--;
    Serial.printf("[VIOLATION] Capturing — %d still queued.\n", violationQueue);
    captureViolation();
    return;   // skip normal detection this cycle
  }

  // ── 3. NORMAL DETECTION LOOP ─────────────────────────────
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
//  SECTION A — LISTEN FOR MEGA SIGNALS ON RX0
//  Mega sends:  [VIOLATION]          — red-light runner
//               [EMERGENCY_DETECTED] — RFID emergency override
//               [JAM_DETECTED]       — pressure sensor jam
// ============================================================
void checkMegaSerial() {
  while (Serial.available() > 0) {
    char c = Serial.read();
    if (c != '[') continue;   // skip noise / WiFi debug chars

    String msg = Serial.readStringUntil(']');
    msg.trim();

    if (msg == "VIOLATION") {
      unsigned long now = millis();
      if (now - lastViolationTime > VIOLATION_COOLDOWN) {
        lastViolationTime = now;
        if (violationQueue < MAX_QUEUE) {
          violationQueue++;
          Serial.printf("[ESP32] Violation queued — depth: %d\n", violationQueue);
        } else {
          Serial.println("[ESP32] Violation queue full — dropped.");
        }
      } else {
        Serial.println("[ESP32] Violation ignored — cooldown (same car).");
      }
    }
    else if (msg == "EMERGENCY_DETECTED") {
      Serial.println("[ESP32] Emergency vehicle confirmed by Mega RFID.");
    }
    else if (msg == "JAM_DETECTED") {
      Serial.println("[ESP32] Traffic jam reported by Mega pressure sensor.");
    }
  }
}

// ============================================================
//  SECTION B — VIOLATION CAPTURE
//  Switches to HD resolution for plate detail, grabs a fresh
//  frame, POSTs to /capture_violation, restores VGA settings.
// ============================================================
void captureViolation() {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("[VIOLATION] No WiFi — frame dropped.");
    return;
  }

  sensor_t *s = esp_camera_sensor_get();

  // Boost resolution + quality for plate recognition
  if (s) {
    s->set_framesize(s, FRAMESIZE_HD);  // 1280x720
    s->set_quality(s, 6);              // lower = sharper JPEG
    s->set_contrast(s, 2);
  }
  delay(150);  // let exposure settle at new resolution

  // Discard stale frame buffered at old VGA settings
  camera_fb_t *discard = esp_camera_fb_get();
  if (discard) esp_camera_fb_return(discard);

  // Grab the actual HD violation frame
  camera_fb_t *fb = esp_camera_fb_get();
  if (!fb) {
    Serial.println("[VIOLATION] ERROR: failed to grab frame.");
    restoreNormalCameraSettings();
    return;
  }

  xorEncrypt(fb->buf, fb->len);

  HTTPClient http;
  http.setReuse(false);
  http.setTimeout(5000);          // HD frame is larger — allow more time
  http.begin(wifiClient, violationServerName);
  http.addHeader("Content-Type", "application/octet-stream");
  http.addHeader("X-Event-Type",  "violation");  // server routes by this

  int code = http.POST(fb->buf, fb->len);
  if (code > 0) {
    Serial.printf("[VIOLATION] Upload OK — HTTP %d\n", code);
  } else {
    Serial.printf("[VIOLATION] Upload FAILED — error %d\n", code);
    wifiClient.stop();
  }

  http.end();
  esp_camera_fb_return(fb);
  restoreNormalCameraSettings();
}

// ============================================================
//  SECTION C — NORMAL DETECTION FRAME
//  Preserves original logic: VGA → XOR → POST /detect_car
//  Parse JSON response → log fields → forward [CMD] to Mega
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
      const char* cmd            = doc["command"];
      int         carsTotal      = doc["cars_total"]      | -1;
      const char* tidalDirection = doc["tidal_direction"] | "UNKNOWN";
      int         sampleWindow   = doc["sample_window"]   | 0;
      JsonArray   laneCounts     = doc["lane_counts"].as<JsonArray>();

      // Debug log — Mega ignores this because it has no []
      Serial.print("{cars_total=");
      Serial.print(carsTotal);
      Serial.print(", lane_counts=(");
      for (int i = 0; i < (int)laneCounts.size(); i++) {
        if (i > 0) Serial.print(",");
        Serial.print(laneCounts[i].as<int>());
      }
      Serial.print("), tidal_direction=");
      Serial.print(tidalDirection);
      Serial.print(", sample_window=");
      Serial.print(sampleWindow);
      Serial.println("}");

      // Forward server command to Mega — Mega only acts on [] packets
      if (cmd) {
        Serial.print("[");
        Serial.print(cmd);
        Serial.println("]");
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
