#include "esp_camera.h"
#include <WiFi.h>
#include <HTTPClient.h>

const char *ssid = "";
const char *password = "";
const String serverName = "http://stl.gyke.net/detect_person";
const char* XOR_KEY = "MyIoTKey2026"; 

// 不再需要定義 MEGA_TX/RX，因為直接用 TX0/RX0 (Serial)
#define PWDN_GPIO_NUM    -1
#define RESET_GPIO_NUM   -1
#define XCLK_GPIO_NUM    15
#define SIOD_GPIO_NUM    4
#define SIOC_GPIO_NUM    5
#define Y9_GPIO_NUM      16
#define Y8_GPIO_NUM      17
#define Y7_GPIO_NUM      18
#define Y6_GPIO_NUM      12
#define Y5_GPIO_NUM      10
#define Y4_GPIO_NUM      8
#define Y3_GPIO_NUM      9
#define Y2_GPIO_NUM      11
#define VSYNC_GPIO_NUM   6
#define HREF_GPIO_NUM    7
#define PCLK_GPIO_NUM    13

WiFiClient wifiClient; 
unsigned long lastFrameTime = 0;
const int FRAME_INTERVAL = 200; 

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
  
  if (psramFound()) {
    config.frame_size = FRAMESIZE_VGA; 
    config.jpeg_quality = 12; 
    config.fb_count = 2;
    config.grab_mode = CAMERA_GRAB_LATEST;
  } else {
    config.frame_size = FRAMESIZE_VGA;  
    config.jpeg_quality = 12;
    config.fb_count = 1;
    config.fb_location = CAMERA_FB_IN_DRAM;
  }

  esp_err_t err = esp_camera_init(&config);
  if (err != ESP_OK) return;

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
    Serial.print(".");
  }
  Serial.println("\nWi-Fi Connected");
  
  wifiClient.setNoDelay(true); 
}

void loop() {
  if (WiFi.status() == WL_CONNECTED) {

    if (millis() - lastFrameTime < FRAME_INTERVAL) {
        delay(10);
        return;
    }
    
    camera_fb_t * fb = esp_camera_fb_get();
    if (!fb) return;

    lastFrameTime = millis();

    size_t keyLen = strlen(XOR_KEY);
    size_t keyIndex = 0;
    for (size_t i = 0; i < fb->len; i++) {
      fb->buf[i] ^= XOR_KEY[keyIndex++];
      if (keyIndex >= keyLen) keyIndex = 0;
    }

    HTTPClient http;
    http.setReuse(true); 
    http.setTimeout(2000); 
    
    http.begin(wifiClient, serverName); 
    http.addHeader("Content-Type", "application/octet-stream"); 

    int httpResponseCode = http.POST(fb->buf, fb->len);

    if (httpResponseCode <= 0) {
      wifiClient.stop(); 
    }

    http.end(); 
    esp_camera_fb_return(fb); 
  } else {
    WiFi.reconnect();
    delay(500);
  }
}
