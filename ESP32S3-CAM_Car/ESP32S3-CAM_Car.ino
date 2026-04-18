// ============================================================
//  AI Thinker ESP32-CAM — Car Detection
// ------------------------------------------------------------
//  Board: AI Thinker ESP32-CAM  (no external GPIO connections)
//
//  Runtime flow:
//    - VGA frames -> POST /detect_car -> server returns command
//    - Pressure / RFID sensors are now on Arduino Mega directly.
//    - Violation capture still works via camera.
//
//  NOTE: Mega polls server independently via ESP8266 WiFi.
// ============================================================

// Serial debug output (USB; TX not connected to Mega)
#ifndef ENABLE_UART_DEBUG
#define ENABLE_UART_DEBUG 1
#endif

#include "esp_camera.h"
#include <ArduinoJson.h>
#include <HTTPClient.h>
#include <WiFi.h>

// ─────────────────────── CREDENTIALS ────────────────────────
const char *ssid = "Team2";
const char *password = "ee3070team2";

// ─────────────────────── SERVER ENDPOINTS ───────────────────
const String serverName = "http://stl.gyke.net/detect_car";
const String violationServerName = "http://stl.gyke.net/capture_violation";
const char *XOR_KEY = "MyIoTKey2026";

#if ENABLE_UART_DEBUG
#define DBG_PRINT(...) Serial.print(__VA_ARGS__)
#define DBG_PRINTLN(...) Serial.println(__VA_ARGS__)
#define DBG_PRINTF(...) Serial.printf(__VA_ARGS__)
#else
#define DBG_PRINT(...)                                                         \
  do {                                                                         \
  } while (0)
#define DBG_PRINTLN(...)                                                       \
  do {                                                                         \
  } while (0)
#define DBG_PRINTF(...)                                                        \
  do {                                                                         \
  } while (0)
#endif

// ─────────────────────── CAMERA PINS (AI Thinker ESP32-CAM) ─
#define PWDN_GPIO_NUM 32
#define RESET_GPIO_NUM -1
#define XCLK_GPIO_NUM 0
#define SIOD_GPIO_NUM 26
#define SIOC_GPIO_NUM 27
#define Y9_GPIO_NUM 35
#define Y8_GPIO_NUM 34
#define Y7_GPIO_NUM 39
#define Y6_GPIO_NUM 36
#define Y5_GPIO_NUM 21
#define Y4_GPIO_NUM 19
#define Y3_GPIO_NUM 18
#define Y2_GPIO_NUM 5
#define VSYNC_GPIO_NUM 25
#define HREF_GPIO_NUM 23
#define PCLK_GPIO_NUM 22

// ─────────────────────── TIMING ─────────────────────────────
const int FRAME_INTERVAL = 200;      // ms between normal detections
const int VIOLATION_COOLDOWN = 2000; // ms — debounce same trigger
const int MAX_QUEUE = 5;             // violation capture safety cap

// ─────────────────────── STATE ──────────────────────────────
WiFiClient wifiClient;
unsigned long lastFrameTime = 0;
unsigned long lastViolationTime = 0;

volatile int violationQueue = 0;
int carsOnRoad = 0;

// ============================================================
//  SETUP
// ============================================================
void setup() {
  Serial.begin(115200);

  camera_config_t config;
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer = LEDC_TIMER_0;
  config.pin_d0 = Y2_GPIO_NUM;
  config.pin_d1 = Y3_GPIO_NUM;
  config.pin_d2 = Y4_GPIO_NUM;
  config.pin_d3 = Y5_GPIO_NUM;
  config.pin_d4 = Y6_GPIO_NUM;
  config.pin_d5 = Y7_GPIO_NUM;
  config.pin_d6 = Y8_GPIO_NUM;
  config.pin_d7 = Y9_GPIO_NUM;
  config.pin_xclk = XCLK_GPIO_NUM;
  config.pin_pclk = PCLK_GPIO_NUM;
  config.pin_vsync = VSYNC_GPIO_NUM;
  config.pin_href = HREF_GPIO_NUM;
  config.pin_sccb_sda = SIOD_GPIO_NUM;
  config.pin_sccb_scl = SIOC_GPIO_NUM;
  config.pin_pwdn = PWDN_GPIO_NUM;
  config.pin_reset = RESET_GPIO_NUM;
  config.xclk_freq_hz = 8000000;
  config.pixel_format = PIXFORMAT_JPEG;
  config.grab_mode = CAMERA_GRAB_WHEN_EMPTY;
  config.fb_location = CAMERA_FB_IN_PSRAM;

  bool hasPsram = psramFound();
  if (hasPsram) {
    config.frame_size = FRAMESIZE_VGA;
    config.jpeg_quality = 12;
    config.fb_count = 2;
    config.grab_mode = CAMERA_GRAB_LATEST;
  } else {
    // Keep DRAM usage low when PSRAM is unavailable.
    config.frame_size = FRAMESIZE_QVGA;
    config.jpeg_quality = 15;
    config.fb_count = 1;
    config.fb_location = CAMERA_FB_IN_DRAM;
    config.grab_mode = CAMERA_GRAB_WHEN_EMPTY;
  }

  esp_err_t err = esp_camera_init(&config);
  if (err != ESP_OK && !hasPsram) {
    DBG_PRINTF("DBG cam init retry QQVGA (no PSRAM), err=0x%x\n", err);
    config.frame_size = FRAMESIZE_QQVGA;
    config.jpeg_quality = 20;
    err = esp_camera_init(&config);
  }
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
    if (s->id.PID == OV3660_PID)
      s->set_vflip(s, 1);
  }

  WiFi.begin(ssid, password);
  WiFi.setSleep(false);
  int wifiAttempts = 0;
  while (WiFi.status() != WL_CONNECTED && wifiAttempts < 30) {
    delay(500);
    DBG_PRINT(".");
    wifiAttempts++;
  }
  if (WiFi.status() == WL_CONNECTED) {
    DBG_PRINTLN("\nWi-Fi connected");
  } else {
    DBG_PRINTLN("\nWi-Fi connect timeout; will retry in loop()");
  }
  wifiClient.setNoDelay(true);
}

// ============================================================
//  LOOP
// ============================================================
void loop() {
  // WiFi check first — needed by both violation upload and detection.
  if (WiFi.status() != WL_CONNECTED) {
    WiFi.reconnect();
    delay(500);
    return;
  }

  if (violationQueue > 0) {
    violationQueue--;
    DBG_PRINTF("DBG violation capture; queued=%d\n", violationQueue);
    captureViolation();
    return;
  }

  if (millis() - lastFrameTime < FRAME_INTERVAL) {
    delay(10);
    return;
  }

  sendDetectionFrame();
}

// ============================================================
//  VIOLATION CAPTURE
// ============================================================
void queueViolationCapture(const char *reason) {
  unsigned long now = millis();
  if (now - lastViolationTime <= VIOLATION_COOLDOWN) {
    DBG_PRINTF("DBG violation ignored (%s); cooldown\n",
               reason ? reason : "unknown");
    return;
  }

  lastViolationTime = now;
  if (violationQueue < MAX_QUEUE) {
    violationQueue++;
    DBG_PRINTF("DBG violation queued (%s); depth=%d\n",
               reason ? reason : "unknown", violationQueue);
  } else {
    DBG_PRINTLN("DBG violation queue full; dropped");
  }
}

void captureViolation() {
  if (WiFi.status() != WL_CONNECTED) {
    DBG_PRINTLN("DBG violation dropped; no WiFi");
    return;
  }

  sensor_t *s = esp_camera_sensor_get();
  if (s) {
    s->set_framesize(s, FRAMESIZE_HD); // 1280x720
    s->set_quality(s, 6);              // lower = sharper JPEG
    s->set_contrast(s, 2);
  }
  delay(150);

  camera_fb_t *discard = esp_camera_fb_get();
  if (discard)
    esp_camera_fb_return(discard);

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
  xorEncrypt(fb->buf, fb->len);  // restore buffer before returning to driver
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
//  NORMAL DETECTION FRAME
// ============================================================
void sendDetectionFrame() {
  camera_fb_t *fb = esp_camera_fb_get();
  if (!fb)
    return;

  lastFrameTime = millis();
  xorEncrypt(fb->buf, fb->len);

  HTTPClient http;
  http.setReuse(false);
  http.setTimeout(2000);
  http.begin(wifiClient, serverName);
  http.addHeader("Content-Type", "application/octet-stream");

  int httpResponseCode = http.POST(fb->buf, fb->len);
  xorEncrypt(fb->buf, fb->len);  // restore buffer before returning to driver
  if (httpResponseCode > 0) {
    String response = http.getString();
    DynamicJsonDocument doc(512);
    DeserializationError error = deserializeJson(doc, response);

    if (!error) {
      const char *cmd = doc["command"] | nullptr;
      int carsTotal = doc["cars_total"] | -1;
      const char *tidalDirection = doc["tidal_direction"] | "UNKNOWN";
      int sampleWindow = doc["sample_window"] | 0;
      JsonArray laneCounts = doc["lane_counts"].as<JsonArray>();

      if (carsTotal >= 0) {
        carsOnRoad = carsTotal;
      }

      DBG_PRINT("{cars_total=");
      DBG_PRINT(carsTotal);
      DBG_PRINT(", lane_counts=(");
      for (int i = 0; i < (int)laneCounts.size(); i++) {
        if (i > 0)
          DBG_PRINT(",");
        DBG_PRINT(laneCounts[i].as<int>());
      }
      DBG_PRINT("), tidal_direction=");
      DBG_PRINT(tidalDirection);
      DBG_PRINT(", sample_window=");
      DBG_PRINT(sampleWindow);
      DBG_PRINTLN("}");

      (void)cmd; // command is consumed by the server; logged above if needed
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
void xorEncrypt(uint8_t *buf, size_t len) {
  size_t keyLen = strlen(XOR_KEY);
  size_t keyIndex = 0;
  for (size_t i = 0; i < len; i++) {
    buf[i] ^= XOR_KEY[keyIndex++];
    if (keyIndex >= keyLen)
      keyIndex = 0;
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
