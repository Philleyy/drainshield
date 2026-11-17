// DrainShield Wi-Fi sensor sketch - ESP8266 sends water-level readings straight to the website
// Board: ESP8266 dev board (NodeMCU 1.0 or Wemos/LOLIN D1 mini). Sensor: HC-SR04 (trigger/echo).
//
//   [HC-SR04] -> [ESP8266] --Wi-Fi--> https://x9unyy6jkf5h.ample.run/api/ingest -> Sensors page
//
// Wiring (pin names as printed on the board):
//   HC-SR04 VCC  -> VIN (NodeMCU) or 5V (D1 mini)    the HC-SR04 needs 5 V
//   HC-SR04 GND  -> G / GND
//   HC-SR04 TRIG -> D5
//   HC-SR04 ECHO -> 1 kOhm -> D6, and D6 -> 2 kOhm -> GND
//                   (ECHO is a 5 V signal; the ESP8266 pins take 3.3 V, the two resistors bring it down)
//
// Put your Wi-Fi name/password, upload key and basin ID in secrets.h (copy secrets_example.h).
// Serial Monitor: 115200 baud.

#include <ESP8266WiFi.h>
#include <ESP8266HTTPClient.h>
#include <WiFiClientSecureBearSSL.h>
#include <time.h>
#include "secrets.h"

const char* INGEST_URL = "https://x9unyy6jkf5h.ample.run/api/ingest";
const int TRIG_PIN = D5;
const int ECHO_PIN = D6;
const unsigned long INTERVAL_MS = 30000;        // one reading every 30 s for the bench test
const int PINGS = 5;
const unsigned long PING_GAP_MS = 60;
const unsigned long ECHO_TIMEOUT_US = 30000UL;  // ~5 m round trip
const int QUEUE_MAX = 20;                       // readings kept while Wi-Fi or the website is down

struct Reading { time_t t; float cm; };
Reading queue[QUEUE_MAX];
int queued = 0;
unsigned long lastMs = 0;

float pingCm() {
  digitalWrite(TRIG_PIN, LOW);  delayMicroseconds(2);
  digitalWrite(TRIG_PIN, HIGH); delayMicroseconds(10);
  digitalWrite(TRIG_PIN, LOW);
  unsigned long us = pulseIn(ECHO_PIN, HIGH, ECHO_TIMEOUT_US);
  if (us == 0) return NAN;
  return us * 0.0343 / 2.0;   // speed of sound at 20 C, there and back
}

// Median of 5 pings: ignores most false echoes (same as the USB sketch)
float medianCm() {
  float v[PINGS];
  int good = 0;
  for (int i = 0; i < PINGS; i++) {
    float d = pingCm();
    if (!isnan(d)) {
      int j = good++;
      while (j > 0 && v[j - 1] > d) { v[j] = v[j - 1]; j--; }
      v[j] = d;
    }
    delay(PING_GAP_MS);
  }
  return good ? v[good / 2] : NAN;
}

void connectWifi() {
  if (WiFi.status() == WL_CONNECTED) return;
  Serial.print("Wi-Fi: connecting to "); Serial.println(WIFI_SSID);
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  for (int i = 0; i < 40 && WiFi.status() != WL_CONNECTED; i++) delay(500);
  if (WiFi.status() == WL_CONNECTED) { Serial.print("Wi-Fi: connected, IP "); Serial.println(WiFi.localIP()); }
  else Serial.println("Wi-Fi: FAILED. Wrong name/password? The ESP8266 only sees 2.4 GHz networks.");
}

String isoUtc(time_t t) {
  char buf[24];
  strftime(buf, sizeof buf, "%Y-%m-%dT%H:%M:%SZ", gmtime(&t));
  return buf;
}

// Sends every queued reading in one request. Returns the HTTP status (negative = no connection).
int upload() {
  String body = "{\"readings\":[";
  for (int i = 0; i < queued; i++) {
    if (i) body += ",";
    body += "{\"basin_id\":\"" BASIN_ID "\",\"timestamp\":\"" + isoUtc(queue[i].t) + "\",\"distance_cm\":";
    body += isnan(queue[i].cm) ? String("null") : String(queue[i].cm, 1);
    body += ",\"mode\":\"DRY\"}";
  }
  body += "]}";

  BearSSL::WiFiClientSecure client;
  // shortcut: the website's certificate is not checked (fine for a bench test with a key you can revoke);
  // pin the certificate before sensors go in the field.
  client.setInsecure();
  HTTPClient http;
  if (!http.begin(client, INGEST_URL)) return -1;
  http.addHeader("Content-Type", "application/json");
  http.addHeader("Authorization", String("Bearer ") + UPLOAD_KEY);
  int code = http.POST(body);
  String answer = http.getString();
  http.end();
  Serial.print("Upload: HTTP "); Serial.print(code); Serial.print(" "); Serial.println(answer);
  if (code == 401) Serial.println("  -> the upload key is wrong or revoked: make a new one on the website.");
  return code;
}

void setup() {
  Serial.begin(115200);
  delay(200);
  Serial.println("\nHELLO,DrainShield Wi-Fi,1");
  pinMode(TRIG_PIN, OUTPUT);
  pinMode(ECHO_PIN, INPUT);
  connectWifi();
  configTime(0, 0, "pool.ntp.org", "time.nist.gov");   // readings are stamped in UTC from internet time
}

void loop() {
  if (lastMs != 0 && millis() - lastMs < INTERVAL_MS) return;
  lastMs = millis();

  connectWifi();
  time_t now = time(nullptr);
  if (now < 1700000000) { Serial.println("Clock: waiting for internet time..."); return; }

  float cm = medianCm();
  Serial.print("Reading: "); if (isnan(cm)) Serial.println("no echo"); else { Serial.print(cm, 1); Serial.println(" cm"); }

  if (queued == QUEUE_MAX) {   // full: drop the oldest reading
    memmove(queue, queue + 1, sizeof(Reading) * (QUEUE_MAX - 1));
    queued--;
  }
  queue[queued++] = {now, cm};

  if (WiFi.status() != WL_CONNECTED) { Serial.print("Kept for later: "); Serial.println(queued); return; }
  int code = upload();
  if (code == 200 || code == 422) queued = 0;   // 422 = the website refused the data: resending won't help
  else { Serial.print("Kept for later: "); Serial.println(queued); }
}
