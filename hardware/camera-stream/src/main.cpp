#include <Arduino.h>
#include <WiFi.h>
#include <WebServer.h>
#include "esp_camera.h"

namespace
{

  constexpr char kApSsid[] = "ESP32-CAM";
  constexpr char kApPassword[] = "12345678";

  WebServer server(80);

  // Freenove firmware camera pin mapping.
  // Pinout for Freenove ESP32-S3-WROOM (OV3660)
  constexpr int kPwdnPin = -1;
  constexpr int kResetPin = -1;
  constexpr int kXclkPin = 15;
  constexpr int kSiodPin = 4;
  constexpr int kSiocPin = 5;
  constexpr int kY9Pin = 16;
  constexpr int kY8Pin = 17;
  constexpr int kY7Pin = 18;
  constexpr int kY6Pin = 12;
  constexpr int kY5Pin = 10;
  constexpr int kY4Pin = 8;
  constexpr int kY3Pin = 9;
  constexpr int kY2Pin = 11;
  constexpr int kVsyncPin = 6;
  constexpr int kHrefPin = 7;
  constexpr int kPclkPin = 13;

  constexpr framesize_t kHighResFrameSize = FRAMESIZE_UXGA;
  constexpr framesize_t kFallbackFrameSize = FRAMESIZE_VGA;

  constexpr char kStreamBoundary[] = "123456789000000000000987654321";

  bool cameraSetup();
  void handleRoot();
  void handleStream();
  void handleNotFound();
  String buildPage();

  bool cameraSetup()
  {
    camera_config_t config{};
    config.ledc_channel = LEDC_CHANNEL_0;
    config.ledc_timer = LEDC_TIMER_0;
    config.pin_d0 = kY2Pin;
    config.pin_d1 = kY3Pin;
    config.pin_d2 = kY4Pin;
    config.pin_d3 = kY5Pin;
    config.pin_d4 = kY6Pin;
    config.pin_d5 = kY7Pin;
    config.pin_d6 = kY8Pin;
    config.pin_d7 = kY9Pin;
    config.pin_xclk = kXclkPin;
    config.pin_pclk = kPclkPin;
    config.pin_vsync = kVsyncPin;
    config.pin_href = kHrefPin;
    config.pin_sccb_sda = kSiodPin;
    config.pin_sccb_scl = kSiocPin;
    config.pin_pwdn = kPwdnPin;
    config.pin_reset = kResetPin;

    config.xclk_freq_hz = 20000000;
    config.pixel_format = PIXFORMAT_JPEG;
    config.grab_mode = CAMERA_GRAB_WHEN_EMPTY;
    config.fb_location = CAMERA_FB_IN_PSRAM;
    config.jpeg_quality = 8;
    config.fb_count = 1;

    if (psramFound())
    {
      config.frame_size = kHighResFrameSize;
      config.fb_count = 2;
    }
    else
    {
      config.frame_size = kFallbackFrameSize;
      config.fb_location = CAMERA_FB_IN_DRAM;
    }
    esp_err_t err = esp_camera_init(&config);
    if (err != ESP_OK)
    {
      Serial.printf("Camera init failed: 0x%x\n", err);
      return false;
    }

    delay(100); // give sensor time to initialize

    sensor_t *sensor = esp_camera_sensor_get();
    if (sensor != nullptr && sensor->id.PID == OV3660_PID)
    {
      sensor->set_vflip(sensor, 1);
      sensor->set_hmirror(sensor, 0);
      sensor->set_brightness(sensor, 1);
      sensor->set_saturation(sensor, 0);
      sensor->set_ae_level(sensor, -2);
      sensor->set_exposure_ctrl(sensor, 1);
      sensor->set_gain_ctrl(sensor, 1);
    }

    return true;
  }

  String buildPage()
  {
    String page;
    page.reserve(1500);
    page += F("<!doctype html><html><head><meta name=viewport content='width=device-width,initial-scale=1'>");
    page += F("<title>ESP32 Camera</title><style>");
    page += F("body{margin:0;font-family:system-ui,sans-serif;background:#111;color:#eee;text-align:center}");
    page += F(".wrap{max-width:960px;margin:0 auto;padding:16px}h1{font-size:1.2rem;margin:8px 0 12px}");
    page += F("img{width:100%;height:auto;border-radius:12px;background:#000;box-shadow:0 10px 30px rgba(0,0,0,.35)}");
    page += F(".card{margin:12px 0;padding:12px;border:1px solid #2a2a2a;border-radius:12px;background:#1a1a1a}");
    page += F("code{color:#7dd3fc}</style></head><body><div class='wrap'>");
    page += F("<h1>ESP32-S3 Camera Stream</h1>");
    page += F("<div class='card'>Connect your phone to the ESP32 Wi-Fi hotspot, then open <code>http://192.168.4.1/</code>.</div>");
    page += F("<img src='/stream' alt='live stream'>");
    page += F("</div></body></html>");
    return page;
  }

  void handleRoot()
  {
    server.send(200, "text/html", buildPage());
  }

  void handleStream()
  {
    WiFiClient client = server.client();
    client.setNoDelay(true);

    client.printf("HTTP/1.1 200 OK\r\nContent-Type: multipart/x-mixed-replace;boundary=%s\r\nConnection: close\r\n\r\n", kStreamBoundary);

    while (client.connected())
    {
      camera_fb_t *fb = esp_camera_fb_get();
      if (fb == nullptr)
      {
        delay(10);
        continue;
      }

      client.printf("--%s\r\n", kStreamBoundary);
      client.print(F("Content-Type: image/jpeg\r\n"));
      client.printf("Content-Length: %u\r\n\r\n", static_cast<unsigned>(fb->len));
      client.write(fb->buf, fb->len);
      client.print(F("\r\n"));
      esp_camera_fb_return(fb);
    }
  }

  void handleNotFound()
  {
    server.send(404, "text/plain", "Not found");
  }

} // namespace

void setup()
{
  Serial.begin(115200);
  delay(200);

  WiFi.mode(WIFI_AP);
  const bool apStarted = WiFi.softAP(kApSsid, kApPassword);
  WiFi.setSleep(false);

  Serial.println();
  Serial.println("ESP32 camera starting...");
  Serial.print("AP SSID: ");
  Serial.println(kApSsid);
  Serial.print("AP started: ");
  Serial.println(apStarted ? "yes" : "no");
  Serial.print("AP IP: ");
  Serial.println(WiFi.softAPIP());

  if (!cameraSetup())
  {
    Serial.println("Camera initialization failed. Halting.");
    while (true)
    {
      delay(1000);
    }
  }

  server.on("/", HTTP_GET, handleRoot);
  server.on("/stream", HTTP_GET, handleStream);
  server.onNotFound(handleNotFound);
  server.begin();

  Serial.println("Open the root page on your phone to view the stream.");
}

void loop()
{
  server.handleClient();
  delay(2);
}