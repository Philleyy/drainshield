// DrainShield LoRa sketch (v3) - Heltec WiFi LoRa 32 V3 (ESP32-S3 + SX1262) + A02YYUW ultrasonic sensor
// ============================================================================================================
// ONE sketch, two roles. Before flashing EACH board, set ROLE and NODE_ID just below.
//
//   ROLE_NODE      the battery sensor in a (mock) catch basin. Each wake-up:
//                    1. powers the sensor, takes a median of 5 readings, runs the tracking loop
//                    2. writes the reading to its own flash (ring buffer: nothing is lost if the radio is down)
//                    3. if it is time, sends every reading not yet acknowledged (oldest first, 8 per packet)
//                       and waits 0.5 s for the receiver's ACK, which also carries the mode the dashboard wants
//                    4. deep-sleeps until the next reading (30 min dry, 5 min watch, 60 s storm)
//   ROLE_RECEIVER  plugged into the laptop by USB (stand-in for the pilot's LoRaWAN gateway). Prints one JSON
//                  line per packet for lora_bridge.py and answers each packet with an ACK. With HAS_SENSOR 1 it
//                  also measures its own basin, so 3 boards = 3 monitored basins on the demo table.
//
// Arduino IDE setup (once):
//   Boards Manager: "esp32" by Espressif Systems (3.x) -> board "Heltec WiFi LoRa 32(V3)"
//                   (or "ESP32S3 Dev Module", Flash 8MB, Partition "8M with spiffs")
//   Library Manager: "RadioLib" by Jan Gromes (tested API: 6.x / 7.x)
//                    "ESP8266 and ESP32 OLED driver for SSD1306 displays" by ThingPulse (only if USE_OLED 1)
//   Serial Monitor: 115200 baud. Close it before starting lora_bridge.py (one program per port).
//
// Wiring (A02YYUW, 4 wires; check the colours on your sensor's label / DFRobot wiki):
//   VCC -> Vext (3.3 V switched by the board: off during sleep)   GND -> GND
//   TX  -> GPIO 47 (board RX)      RX -> GPIO 48 (board TX, idles HIGH = "processed" output mode)
//   Battery: 1S LiPo on the 1.25 mm battery plug. CHECK POLARITY FIRST (many cheap LiPo plugs are reversed).
//   NEVER put a primary (non-rechargeable) Li-SOCl2 cell on that plug: the board's charger would charge it.
// ============================================================================================================

#define ROLE_NODE      1
#define ROLE_RECEIVER  2

#define ROLE        ROLE_NODE    // <-- ROLE_NODE or ROLE_RECEIVER
#define NODE_ID     1            // <-- 1, 2, 3...: each board its own number (the receiver's own basin too)
#define HAS_SENSOR  1            // receiver only: 1 = it also measures its own basin, 0 = radio only
#define BENCH_MODE  0            // 1 = never sleep, OLED on, serial commands (DUMP, ?, MODE,n, CLEAR)
#define DEMO_TIMING 1            // 1 = competition timing (60 s / 20 s / 5 s), 0 = field timing (30 min / 5 min / 60 s)
#define USE_OLED    1            // 0 if you don't install the ThingPulse OLED library

#include <Arduino.h>
#include <SPI.h>
#include <RadioLib.h>
#include <LittleFS.h>
#include <esp_sleep.h>
#include <sys/time.h>
#include "drainshield_packet.h"
#if USE_OLED
#include <Wire.h>
#include <SSD1306Wire.h>
#endif

// ------------------------------------------------------------------ board pins (Heltec WiFi LoRa 32 V3)
#define LORA_NSS   8
#define LORA_SCK   9
#define LORA_MOSI  10
#define LORA_MISO  11
#define LORA_RST   12
#define LORA_BUSY  13
#define LORA_DIO1  14
#define VEXT_PIN   36            // LOW = 3.3 V on Vext (sensor + OLED), HIGH = off
#define BATT_ADC   1             // battery through a 390k/100k divider
#define BATT_CTRL  37            // switches the divider on only while reading (saves ~8 uA)
#define BATT_CTRL_ON LOW         // V3.0/V3.1 boards. Heltec V3.2 boards: HIGH. Check: battery reads ~3.7-4.2 V?
#define BATT_DIVIDER 4.9f        // (390k + 100k) / 100k
#define OLED_SDA   17
#define OLED_SCL   18
#define OLED_RST   21
#define SENSOR_RX  47            // board RX <- sensor TX
#define SENSOR_TX  48            // board TX -> sensor RX (held HIGH)

// ------------------------------------------------------------------ radio (LoRa peer-to-peer, 915 MHz band)
// 500 kHz bandwidth: shortest airtime (battery) and the bandwidth class Canada's 902-928 MHz rules treat as
// "digital modulation" without frequency hopping. SF9 still gives a large margin over a few metres of table;
// in the field this becomes LoRaWAN (US915) through a gateway.
#define LORA_FREQ_MHZ   915.0
#define LORA_BW_KHZ     500.0
#define LORA_SF         9
#define LORA_CR         7          // 4/7
#define LORA_POWER_DBM  10         // enough for a demo table; field: 14-20 dBm
#define LORA_TCXO_V     1.8        // the V3's crystal oscillator runs at 1.8 V
#define ACK_TIMEOUT_MS  500
#define MAX_PACKETS_PER_WAKE 3     // 3 x 8 readings per wake-up when catching up after an outage

// ------------------------------------------------------------------ sensor + tracking loop (mm, mm/min)
#define PINGS            5
#define SENSOR_WARMUP_MS 300
#define SENSOR_TIMEOUT_MS 2000
#define BLIND_ZONE_MM    30        // A02YYUW datasheet: 3 cm (NOT 25-30 cm: that is the A01NYUB)
#define FLOOR_MARGIN_MM  20        // a reading within 20 mm of the blind zone counts as "at the floor"
#define NEAR_SENSOR_MM   150       // water this close, then no echo -> probably submerged
#define MAX_VALID_MM     4500
#define KP 0.5f                    // share of each surprise accepted right away
#define KI 0.1f                    // how fast the rise-rate estimate adapts
#define GATE_MM 150                // a reading this far from the prediction is suspect...
#define CONFIRM_MM 30              // ...unless 2 more readings taken right away agree within 30 mm
#define STORM_RATE_MM_MIN 3.0f     // water moving faster than 3 mm/min (0.3 cm/min) -> local storm mode
#define RISE_TRIGGER_MM 30         // ...or water 3 cm above this basin's own dry level -> local storm mode
                                   // (WHY both: waking every 30 min, a clean basin's 5 cm rise looks slow per minute)

// ------------------------------------------------------------------ timing per mode (seconds)
#if DEMO_TIMING
static const uint32_t SAMPLE_S[3]   = {60, 20, 5};        // DRY, WATCH, STORM
static const uint32_t TX_EVERY_S[3] = {60, 20, 10};
#define STORM_HOLD_S 120
#else
static const uint32_t SAMPLE_S[3]   = {1800, 300, 60};    // 30 min, 5 min, 60 s
static const uint32_t TX_EVERY_S[3] = {1800, 300, 120};   // storm: send every 2 min (2 readings per packet)
#define STORM_HOLD_S 1800                                 // stay in storm mode 30 min after the water stops
#endif
#define SERVER_MODE_EXPIRE_S (12UL * 3600)                // no ACK for 12 h -> forget the dashboard's mode

// ------------------------------------------------------------------ flash ring buffer
#define RING_FILE  "/ring.bin"
#define META_FILE  "/meta.bin"
#define RING_SLOTS 8192            // 8192 x 16 B = 128 KB: ~5.7 days of storm mode, ~170 days of dry mode
#define META_MAGIC 0x44534D31UL    // "DSM1"

struct StoredRec {                 // 16 bytes in flash
  uint32_t t;                      // node clock (s): counts through deep sleep, starts at 0 at power-on
  uint16_t raw_mm, filt_mm;
  int16_t  rise10;
  int8_t   temp_c;
  uint8_t  batt20;
  uint8_t  flags;
  uint8_t  pad[3];
};
static_assert(sizeof(StoredRec) == 16, "stored record must be 16 bytes");

struct Meta { uint32_t magic, head, tail, lost; };   // head = readings written, tail = readings acknowledged

// ------------------------------------------------------------------ state kept through deep sleep (RTC RAM)
RTC_DATA_ATTR float    est = NAN;          // filtered distance (mm)
RTC_DATA_ATTR float    rate = 0;           // mm/min, NEGATIVE = water coming closer = rising
RTC_DATA_ATTR float    baseline = NAN;     // resting distance in dry weather (learned slowly)
RTC_DATA_ATTR uint8_t  suspect = 0, floorCount = 0;
RTC_DATA_ATTR uint32_t lastSampleT = 0, lastTxT = 0, lastAckT = 0, stormUntil = 0;
RTC_DATA_ATTR uint8_t  serverMode = MODE_DRY;
RTC_DATA_ATTR bool     everRan = false;

SX1262 radio = new Module(LORA_NSS, LORA_DIO1, LORA_RST, LORA_BUSY);
volatile bool radioFlag = false;
void IRAM_ATTR onRadio() { radioFlag = true; }
Meta meta;
bool radioOk = false;
#if USE_OLED
SSD1306Wire oled(0x3c, OLED_SDA, OLED_SCL);
#endif

uint32_t nowS() { return (uint32_t)time(nullptr); }
#if ROLE == ROLE_RECEIVER
void handlePacket();               // defined in the receiver section (answers nodes even while measuring)
#endif

// ============================================================================================================
// SENSOR: one reading = median of 5 UART frames (0xFF, high byte, low byte, checksum)
// ============================================================================================================
void sensorPower(bool on) {
  pinMode(VEXT_PIN, OUTPUT);
  digitalWrite(VEXT_PIN, on ? LOW : HIGH);
}

int readSensorMedian(int &good) {
  uint16_t v[PINGS];
  uint8_t f[4];
  int pos = 0;
  good = 0;
  while (Serial1.available()) Serial1.read();                     // drop stale bytes
  uint32_t t0 = millis();
  while (good < PINGS && millis() - t0 < SENSOR_TIMEOUT_MS) {
    while (Serial1.available() && good < PINGS) {
      uint8_t b = Serial1.read();
      if (pos == 0 && b != 0xFF) continue;                         // wait for a frame start
      f[pos++] = b;
      if (pos < 4) continue;
      pos = 0;
      if (((f[0] + f[1] + f[2]) & 0xFF) != f[3]) continue;         // bad checksum: skip the frame
      uint16_t mm = ((uint16_t)f[1] << 8) | f[2];
      if (mm == 0 || mm > MAX_VALID_MM) continue;                  // out of range = no echo
      int j = good++;                                              // insert in order (array stays sorted)
      while (j > 0 && v[j - 1] > mm) { v[j] = v[j - 1]; j--; }
      v[j] = mm;
    }
#if ROLE == ROLE_RECEIVER
    if (radioFlag) { radioFlag = false; handlePacket(); }         // a node's ACK can't wait for our sensor
#endif
    if (good < PINGS) delay(5);
  }
  return good ? v[good / 2] : -1;
}

// Tracking loop (same idea as the Uno sketch v2, in mm): smooth the level, estimate the rise rate, reject a
// sudden jump unless it is confirmed. Returns the REC_* flags of this reading.
uint8_t track(int meas, float dtMin, bool confirmed, float tempC) {
  if (meas < 0) {                                                  // no echo at all
    uint8_t fl = REC_NO_ECHO;
    if (tempC < 0) fl |= REC_ICED;                                 // frost on the face, most likely
    if (!isnan(est) && est <= BLIND_ZONE_MM + NEAR_SENSOR_MM) fl |= REC_AT_BLIND;   // water was right there
    return fl;
  }
  if (meas <= BLIND_ZONE_MM + FLOOR_MARGIN_MM) {                   // at the blind-zone floor
    bool wasClose = !isnan(est) && est <= BLIND_ZONE_MM + NEAR_SENSOR_MM;
    if (++floorCount >= 2 || wasClose || confirmed) {              // sustained = REAL: water at the sensor
      est = meas; rate = 0; suspect = 0;
      return REC_AT_BLIND;                                         // (project rule: never reject this as noise)
    }
    return REC_SUSPECT;
  }
  floorCount = 0;
  if (isnan(est)) { est = meas; return 0; }                        // first reading after power-on
  float pred = est + rate * dtMin;                                 // where we expect the water now
  float err = meas - pred;                                         // the surprise
  if (fabsf(err) > GATE_MM && !confirmed) {
    if (++suspect < 3) { est = pred; return REC_SUSPECT; }         // probably a false echo: ignore it
  }
  if (fabsf(err) > GATE_MM) {                                      // confirmed jump (or 3 in a row): it's real
    float jumpRate = dtMin > 0.05f ? err / dtMin : 0;
    est = meas; rate = constrain(jumpRate, -500.0f, 500.0f); suspect = 0;
    return 0;
  }
  suspect = 0;
  est = pred + KP * err;                                           // P corrects the level
  rate += KI * err / max(dtMin, 0.05f);                            // I corrects the rate
  rate = constrain(rate, -500.0f, 500.0f);
  return 0;
}

float readBatteryV() {
  pinMode(BATT_CTRL, OUTPUT);
  digitalWrite(BATT_CTRL, BATT_CTRL_ON);
  delay(5);
  uint32_t mv = analogReadMilliVolts(BATT_ADC);
  digitalWrite(BATT_CTRL, BATT_CTRL_ON == LOW ? HIGH : LOW);
  return mv * BATT_DIVIDER / 1000.0f;
}

// One complete measurement. Fills a StoredRec. Re-measures right away to confirm a suspicious jump
// (WHY: in dry mode the next wake is 30 min away; waiting for 3 wakes to accept a real rise would hide
// the first hour of a storm).
StoredRec measure(bool onUsb, bool &jumped) {
  StoredRec r = {};
  uint32_t t = nowS();
  float dtMin = (everRan && lastSampleT) ? (t - lastSampleT) / 60.0f : 0;
  float tempC = temperatureRead();                                 // ESP32-S3 die temperature (approximate)
  int good;
  int raw = readSensorMedian(good);
  float before = est;
  uint8_t fl = track(raw, dtMin, false, tempC);
  if (fl & REC_SUSPECT) {
    int g1, g2;
    int a = readSensorMedian(g1);
    int b = readSensorMedian(g2);
    if (a > 0 && b > 0 && abs(a - raw) <= CONFIRM_MM && abs(b - raw) <= CONFIRM_MM) {
      est = before;                                                // undo the "ignore" step, then accept
      fl = track(raw, dtMin, true, tempC);
    }
  }
  jumped = !isnan(before) && !isnan(est) && fabsf(est - before) > GATE_MM;
  lastSampleT = t;
  everRan = true;
  r.t = t;
  r.raw_mm = raw > 0 ? raw : 0;
  r.filt_mm = isnan(est) ? 0 : (uint16_t)lroundf(est);
  r.rise10 = (int16_t)lroundf(constrain(-rate * 10.0f, -32000.0f, 32000.0f));
  r.temp_c = (int8_t)lroundf(constrain(tempC, -100.0f, 100.0f));
  float vb = onUsb ? 0 : readBatteryV();
  r.batt20 = (uint8_t)constrain(lroundf(vb * 1000.0f / 20.0f), 0L, 255L);
  r.flags = fl | (onUsb ? REC_ON_USB : 0);
  return r;
}

// ============================================================================================================
// FLASH RING BUFFER (LittleFS). WHY internal flash and not a microSD card: no extra part, no card contacts to
// corrode in a sewer, no card drawing current in sleep, and 128 KB already holds ~5.7 days of storm readings.
// WHY fixed 16-byte binary slots and not CSV lines: slot = index % N makes a true ring (the oldest reading is
// overwritten when full), and the CSV is produced on demand by the DUMP command or by the dashboard.
// ============================================================================================================
bool metaSave() {
  File f = LittleFS.open(META_FILE, "w");
  if (!f) return false;
  f.write((const uint8_t *)&meta, sizeof(meta));
  f.close();
  return true;
}

bool ringBegin() {
  if (!LittleFS.begin(true)) return false;                         // true = format on first use
  File f = LittleFS.open(META_FILE, "r");
  bool ok = f && f.read((uint8_t *)&meta, sizeof(meta)) == sizeof(meta) && meta.magic == META_MAGIC;
  if (f) f.close();
  File r = LittleFS.open(RING_FILE, "r");
  bool sized = r && r.size() == (size_t)RING_SLOTS * sizeof(StoredRec);
  if (r) r.close();
  if (!ok || !sized) {                                             // first boot: create the empty ring
    File w = LittleFS.open(RING_FILE, "w");
    if (!w) return false;
    uint8_t zero[512] = {0};
    for (uint32_t done = 0; done < (uint32_t)RING_SLOTS * sizeof(StoredRec); done += sizeof(zero))
      w.write(zero, sizeof(zero));
    w.close();
    meta = {META_MAGIC, 0, 0, 0};
    metaSave();
  }
  return true;
}

bool ringRead(uint32_t index, StoredRec &rec) {
  File f = LittleFS.open(RING_FILE, "r");
  if (!f) return false;
  f.seek((index % RING_SLOTS) * sizeof(StoredRec));
  bool ok = f.read((uint8_t *)&rec, sizeof(rec)) == sizeof(rec);
  f.close();
  return ok;
}

bool ringPush(const StoredRec &rec) {
  File f = LittleFS.open(RING_FILE, "r+");
  if (!f) return false;
  f.seek((meta.head % RING_SLOTS) * sizeof(StoredRec));
  f.write((const uint8_t *)&rec, sizeof(rec));
  f.close();
  meta.head++;
  if (meta.head - meta.tail > RING_SLOTS) {                        // full: the oldest unsent reading is lost
    meta.lost += meta.head - meta.tail - RING_SLOTS;
    meta.tail = meta.head - RING_SLOTS;
  }
  return metaSave();
}

// After a power loss (battery swap) the clock restarts at 0, but readings still in flash carry the old clock.
// Restart the clock just after the newest stored reading so ages stay positive, and flag the gap.
bool restoreClockAfterPowerLoss() {
  if (meta.head == 0) return false;
  StoredRec last;
  if (!ringRead(meta.head - 1, last)) return false;
  if (nowS() > last.t) return false;
  struct timeval tv = {(time_t)(last.t + 1), 0};
  settimeofday(&tv, nullptr);
  return true;
}

void dumpCsv() {                                                   // serial command DUMP
  Serial.println("index,node_clock_s,raw_mm,filtered_mm,rise_mm_min,temp_c,battery_v,flags,sent");
  uint32_t first = meta.head > RING_SLOTS ? meta.head - RING_SLOTS : 0;
  for (uint32_t i = first; i < meta.head; i++) {
    StoredRec r;
    if (!ringRead(i, r)) break;
    Serial.printf("%lu,%lu,%u,%u,%.1f,%d,%.2f,%u,%d\n", (unsigned long)i, (unsigned long)r.t, r.raw_mm,
                  r.filt_mm, r.rise10 / 10.0f, r.temp_c, r.batt20 * 0.02f, r.flags, i < meta.tail ? 1 : 0);
  }
}

// ============================================================================================================
// RADIO
// ============================================================================================================
bool radioBegin() {
  SPI.begin(LORA_SCK, LORA_MISO, LORA_MOSI, LORA_NSS);
  int st = radio.begin(LORA_FREQ_MHZ, LORA_BW_KHZ, LORA_SF, LORA_CR, RADIOLIB_SX126X_SYNC_WORD_PRIVATE,
                       LORA_POWER_DBM, 8, LORA_TCXO_V, false);
  if (st != RADIOLIB_ERR_NONE) { Serial.printf("radio init failed (%d)\n", st); return false; }
  radio.setDio2AsRfSwitch(true);
  radio.setDio1Action(onRadio);
  return true;
}

// Send one packet and wait for the matching ACK. Returns true and the wanted mode if acknowledged.
bool sendWithAck(const uint8_t *buf, size_t len, uint32_t ackIndex, uint8_t &modeOut) {
  if (radio.transmit((uint8_t *)buf, len) != RADIOLIB_ERR_NONE) return false;
  radioFlag = false;
  radio.startReceive();
  uint32_t t0 = millis();
  while (millis() - t0 < ACK_TIMEOUT_MS) {
    if (radioFlag) {
      radioFlag = false;
      DsAckMode a;
      size_t n = radio.getPacketLength();
      if (n == sizeof(a) && radio.readData((uint8_t *)&a, sizeof(a)) == RADIOLIB_ERR_NONE &&
          a.ack.magic == DS_MAGIC_ACK && a.ack.node_id == NODE_ID && a.ack.ack_index == ackIndex) {
        modeOut = a.mode <= (uint8_t)MODE_STORM ? a.mode : (uint8_t)MODE_DRY;
        radio.standby();
        return true;
      }
      radio.startReceive();                                        // someone else's packet: keep listening
    }
    delay(2);
  }
  radio.standby();
  return false;
}

// Send the backlog, oldest first, up to MAX_PACKETS_PER_WAKE packets. Returns true if at least one ACK came.
bool sendBacklog(uint8_t mode) {
  bool any = false;
  for (int p = 0; p < MAX_PACKETS_PER_WAKE && meta.head > meta.tail; p++) {
    uint8_t buf[sizeof(DsHeader) + DS_MAX_RECORDS * sizeof(DsRecord)];
    uint32_t pending = meta.head - meta.tail;
    uint8_t n = pending > DS_MAX_RECORDS ? DS_MAX_RECORDS : pending;
    uint32_t rest = pending - n;
    DsHeader h = {DS_MAGIC_UP, DS_VERSION, NODE_ID, meta.tail, mode, n, (uint16_t)(rest > 65535 ? 65535 : rest)};
    memcpy(buf, &h, sizeof(h));
    uint32_t t = nowS();
    for (uint8_t i = 0; i < n; i++) {
      StoredRec s;
      ringRead(meta.tail + i, s);
      DsRecord r = {t >= s.t ? t - s.t : 0, s.raw_mm, s.filt_mm, s.rise10, s.temp_c, s.batt20, s.flags};
      memcpy(buf + sizeof(h) + i * sizeof(DsRecord), &r, sizeof(r));
    }
    uint8_t wanted;
    if (!sendWithAck(buf, sizeof(h) + n * sizeof(DsRecord), meta.tail + n, wanted)) break;   // no ACK: retry next wake
    meta.tail += n;
    metaSave();
    serverMode = wanted;
    lastAckT = t;
    any = true;
  }
  return any;
}

// ============================================================================================================
// OLED (bench / demo only)
// ============================================================================================================
const char *MODE_NAME[3] = {"DRY", "WATCH", "STORM"};

void show(const char *l1, const char *l2, const char *l3, const char *l4) {
#if USE_OLED
  static bool started = false;
  if (!started) {
    pinMode(OLED_RST, OUTPUT); digitalWrite(OLED_RST, LOW); delay(20); digitalWrite(OLED_RST, HIGH);
    oled.init(); oled.flipScreenVertically(); oled.setFont(ArialMT_Plain_10);
    started = true;
  }
  oled.clear();
  oled.drawString(0, 0, l1); oled.drawString(0, 14, l2); oled.drawString(0, 28, l3); oled.drawString(0, 42, l4);
  oled.display();
#endif
}

// Local storm trigger, shared by both roles: fast movement, a confirmed jump, water at the sensor, or water
// clearly above the basin's own dry level. Also keeps learning that dry level while nothing happens.
bool localStormTrigger(const StoredRec &r, bool jumped) {
  bool valid = !(r.flags & (REC_NO_ECHO | REC_AT_BLIND | REC_SUSPECT)) && !isnan(est);
  bool risen = valid && !isnan(baseline) && (baseline - est) > RISE_TRIGGER_MM;
  if (valid && !risen && fabsf(rate) < 0.5f && nowS() >= stormUntil)
    baseline = isnan(baseline) ? est : baseline + 0.2f * (est - baseline);
  bool trigger = fabsf(rate) > STORM_RATE_MM_MIN || jumped || (r.flags & REC_AT_BLIND) || risen;
  if (trigger) stormUntil = nowS() + STORM_HOLD_S;
  return trigger;
}

#if ROLE == ROLE_NODE
// ============================================================================================================
// NODE
// ============================================================================================================
uint8_t currentMode() {
  uint32_t t = nowS();
  if (lastAckT && t - lastAckT > SERVER_MODE_EXPIRE_S) serverMode = MODE_DRY;   // lost the dashboard: own rules
  uint8_t local = (t < stormUntil) ? MODE_STORM : MODE_DRY;
  return max(serverMode, local);                                   // the more careful of the two wins
}

// One wake-up. Returns the seconds to sleep.
uint32_t cycle(bool clockGap) {
  bool jumped;
  StoredRec r = measure(false, jumped);
  if (clockGap) r.flags |= REC_CLOCK_GAP;
  bool alarm = (r.flags & REC_AT_BLIND) || jumped;                // send now, don't wait for the slot
  localStormTrigger(r, jumped);
  ringPush(r);

  uint8_t mode = currentMode();
  bool due = nowS() - lastTxT >= TX_EVERY_S[mode] || lastTxT == 0;
  bool sent = false;
  if (radioOk && (due || alarm)) {                                 // alarm: send now, don't wait for the slot
    sent = sendBacklog(mode);
    lastTxT = nowS();
    mode = currentMode();                                          // the ACK may have changed it
  }
  radio.sleep();

  char l1[32], l2[32], l3[32], l4[32];
  snprintf(l1, sizeof(l1), "Node %d  %s", NODE_ID, MODE_NAME[mode]);
  snprintf(l2, sizeof(l2), "Water at %u mm", r.filt_mm);
  snprintf(l3, sizeof(l3), "Rise %+.1f mm/min", r.rise10 / 10.0f);
  snprintf(l4, sizeof(l4), "%.2f V  %s  %lu queued", r.batt20 * 0.02f, sent ? "TX ok" : (due ? "no ACK" : "-"),
           (unsigned long)(meta.head - meta.tail));
  if (BENCH_MODE) show(l1, l2, l3, l4);
  Serial.printf("[%s] raw=%u filt=%u rise=%+.1f mm/min flags=0x%02X batt=%.2fV queued=%lu\n", MODE_NAME[mode],
                r.raw_mm, r.filt_mm, r.rise10 / 10.0f, r.flags, r.batt20 * 0.02f,
                (unsigned long)(meta.head - meta.tail));
  return SAMPLE_S[mode];
}

void handleSerial() {
  while (Serial.available()) {
    String line = Serial.readStringUntil('\n');
    line.trim();
    if (line == "DUMP") dumpCsv();
    else if (line == "CLEAR") { meta = {META_MAGIC, 0, 0, 0}; metaSave(); Serial.println("OK,CLEAR"); }
    else if (line.startsWith("MODE,")) { serverMode = constrain(line.substring(5).toInt(), 0, 2);
                                         Serial.printf("OK,MODE,%d\n", serverMode); }
    else if (line == "?") Serial.printf("OK,STATUS,node=%d,mode=%s,written=%lu,queued=%lu,lost=%lu\n", NODE_ID,
                                        MODE_NAME[currentMode()], (unsigned long)meta.head,
                                        (unsigned long)(meta.head - meta.tail), (unsigned long)meta.lost);
  }
}

void setup() {
  Serial.begin(115200);
  bool coldBoot = esp_sleep_get_wakeup_cause() == ESP_SLEEP_WAKEUP_UNDEFINED;
  sensorPower(true);
  Serial1.begin(9600, SERIAL_8N1, SENSOR_RX, SENSOR_TX);
  bool fsOk = ringBegin();
  bool clockGap = coldBoot && fsOk && restoreClockAfterPowerLoss();
  radioOk = radioBegin();
  if (coldBoot) Serial.printf("HELLO,DrainShield,3,node,%d,%s\n", NODE_ID, fsOk ? "flash ok" : "FLASH ERROR");
  delay(SENSOR_WARMUP_MS);
#if BENCH_MODE
  cycle(clockGap);
#else
  uint32_t sleepS = cycle(clockGap);
  Serial.flush();
  Serial1.end();
  sensorPower(false);                                              // sensor + OLED off during sleep
  esp_sleep_enable_timer_wakeup((uint64_t)sleepS * 1000000ULL);
  esp_deep_sleep_start();                                          // wakes up in setup() again
#endif
}

void loop() {                                                      // only reached in BENCH_MODE
  static uint32_t next = millis() + SAMPLE_S[MODE_DRY] * 1000UL;
  handleSerial();
  if ((int32_t)(millis() - next) >= 0) next = millis() + cycle(false) * 1000UL;
  delay(10);
}

#else
// ============================================================================================================
// RECEIVER (gateway stand-in, plugged into the laptop)
// ============================================================================================================
#define MAX_NODES 16
uint8_t wantedMode[MAX_NODES + 1] = {0};      // per node id, set by lora_bridge.py ("M,<node>,<mode>")
uint32_t localIndex = 0;
uint32_t nextLocalMs = 0;

void printRecordsJson(const DsHeader &h, const DsRecord *recs, float rssi, float snr, bool hasRadio) {
  Serial.printf("{\"type\":\"pkt\",\"node\":%u,\"first\":%lu,\"mode\":%u,\"backlog\":%u,", h.node_id,
                (unsigned long)h.first_index, h.mode, h.backlog);
  if (hasRadio) Serial.printf("\"rssi\":%.1f,\"snr\":%.1f,", rssi, snr);
  else Serial.print("\"rssi\":null,\"snr\":null,");
  Serial.print("\"records\":[");
  for (uint8_t i = 0; i < h.n_records; i++) {
    const DsRecord &r = recs[i];
    Serial.printf("%s[%lu,%u,%u,%d,%d,%u,%u]", i ? "," : "", (unsigned long)r.age_s, r.raw_mm, r.filt_mm,
                  r.rise_mm_min_x10, r.temp_c, r.batt_20mv, r.flags);
  }
  Serial.println("]}");
}

void handlePacket() {
  uint8_t buf[sizeof(DsHeader) + DS_MAX_RECORDS * sizeof(DsRecord)];
  size_t len = radio.getPacketLength();
  if (len < sizeof(DsHeader) || len > sizeof(buf) || radio.readData(buf, len) != RADIOLIB_ERR_NONE) {
    radio.startReceive();
    return;
  }
  DsHeader h;
  memcpy(&h, buf, sizeof(h));
  if (h.magic != DS_MAGIC_UP || h.version != DS_VERSION || h.n_records == 0 || h.n_records > DS_MAX_RECORDS ||
      len != sizeof(h) + h.n_records * sizeof(DsRecord)) {
    radio.startReceive();
    return;
  }
  float rssi = radio.getRSSI(), snr = radio.getSNR();
  DsAckMode a = {{DS_MAGIC_ACK, DS_VERSION, h.node_id, h.first_index + h.n_records},
                 h.node_id <= MAX_NODES ? wantedMode[h.node_id] : (uint8_t)MODE_DRY, 0};
  radio.transmit((uint8_t *)&a, sizeof(a));                        // ACK FIRST: the node only listens 0.5 s
  DsRecord recs[DS_MAX_RECORDS];
  memcpy(recs, buf + sizeof(h), h.n_records * sizeof(DsRecord));
  printRecordsJson(h, recs, rssi, snr, true);                      // then tell the laptop
  radioFlag = false;
  radio.startReceive();
}

void measureOwnBasin() {                                           // the 3rd demo basin, powered by USB
  bool jumped;
  StoredRec r = measure(true, jumped);
  localStormTrigger(r, jumped);
  uint8_t mode = max(wantedMode[NODE_ID <= MAX_NODES ? NODE_ID : 0], (uint8_t)(nowS() < stormUntil ? MODE_STORM : MODE_DRY));
  DsHeader h = {DS_MAGIC_UP, DS_VERSION, NODE_ID, localIndex++, mode, 1, 0};
  DsRecord rec = {0, r.raw_mm, r.filt_mm, r.rise10, r.temp_c, 0, r.flags};
  printRecordsJson(h, &rec, 0, 0, false);
  char l2[32], l3[32];
  snprintf(l2, sizeof(l2), "Own basin %u mm", r.filt_mm);
  snprintf(l3, sizeof(l3), "Rise %+.1f mm/min", r.rise10 / 10.0f);
  show("DrainShield receiver", l2, l3, MODE_NAME[mode]);
  nextLocalMs = millis() + SAMPLE_S[mode] * 1000UL;
}

void handleSerial() {
  while (Serial.available()) {
    String line = Serial.readStringUntil('\n');
    line.trim();
    if (line.startsWith("M,")) {                                   // M,<node>,<mode>
      int comma = line.indexOf(',', 2);
      int node = line.substring(2, comma).toInt();
      int mode = line.substring(comma + 1).toInt();
      if (comma > 0 && node >= 1 && node <= MAX_NODES && mode >= 0 && mode <= 2) {
        wantedMode[node] = mode;
        Serial.printf("{\"type\":\"ok\",\"node\":%d,\"mode\":%d}\n", node, mode);
      } else {
        Serial.println("{\"type\":\"error\",\"msg\":\"use M,<node 1-16>,<mode 0-2>\"}");
      }
    } else if (line == "?") {
      Serial.printf("{\"type\":\"status\",\"role\":\"receiver\",\"node\":%d,\"radio\":%s}\n", NODE_ID,
                    radioOk ? "true" : "false");
    }
  }
}

void setup() {
  Serial.begin(115200);
  Serial.setTimeout(50);
  sensorPower(true);                                               // OLED (and own sensor) always on: USB power
  if (HAS_SENSOR) Serial1.begin(9600, SERIAL_8N1, SENSOR_RX, SENSOR_TX);
  radioOk = radioBegin();
  if (radioOk) radio.startReceive();
  Serial.printf("{\"type\":\"hello\",\"role\":\"receiver\",\"fw\":3,\"node\":%d,\"radio\":%s}\n", NODE_ID,
                radioOk ? "true" : "false");
  show("DrainShield receiver", radioOk ? "Radio OK, listening" : "RADIO ERROR", "", "");
  delay(SENSOR_WARMUP_MS);
}

void loop() {
  handleSerial();
  if (radioFlag) { radioFlag = false; handlePacket(); }
  if (HAS_SENSOR && (int32_t)(millis() - nextLocalMs) >= 0) measureOwnBasin();
  delay(1);
}
#endif
