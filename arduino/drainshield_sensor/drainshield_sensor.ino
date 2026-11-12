// DrainShield sensor sketch (v2) - ultrasonic water level for the DrainShield dashboard
// Board: Arduino Uno / Nano (5 V). Sensor: trigger/echo type (HC-SR04, JSN-SR04T, AJ-SR04M...).
//
// Sends one line per reading over USB:
//   DIST,<filtered cm>,<good pings of 5>,<rise rate cm/min>,<raw cm>
//   e.g. DIST,101.3,5,0.00,101.4     DIST,NaN,0,0.00,NaN = no echo at all
// Accepts (sent by sensor_bridge.py):
//   I,<ms>   dry-weather reading interval, 500 to 3600000 (e.g. I,300000 = every 5 min)
//   T,<C>    air temperature in the basin, for the speed of sound
//   ?        print the current settings
//
// How a reading is made:
//   1. 5 pings, keep the MEDIAN            -> removes most false echoes (walls, ladder rungs)
//   2. TRACKING LOOP (PID structure)       -> smooths the level, estimates how fast it moves,
//                                             and ignores a reading that jumps for no reason
//   3. STORM MODE                          -> reads every 30 s while the water moves, then goes
//                                             back to the slow interval: saves battery in dry weather

const int TRIG_PIN = 13;   // (pin 13 also drives the board's LED: it flickers, that's normal)
const int ECHO_PIN = 12;

const int PINGS = 5;
const unsigned long PING_GAP_MS = 60;          // let the previous echo die out
const unsigned long ECHO_TIMEOUT_US = 30000UL; // ~5 m round trip, then give up

// Tracking loop gains. It works like a PID loop, but instead of driving a motor it drives
// its ESTIMATE of the water towards the measurements.
const float KP = 0.5;    // proportional: share of each surprise accepted right away (0-1; higher = faster, noisier)
const float KI = 0.1;    // integral: how quickly the rate estimate adapts
const float KD = 0.0;    // derivative: left at 0 on purpose, it amplifies ultrasonic noise
const float GATE_CM = 15.0;                    // a reading this far from the prediction is suspect
const float STORM_RATE = 0.3;                  // cm/min: water moving faster than this -> storm mode
const unsigned long STORM_INTERVAL_MS = 30000; // reading interval in storm mode
const unsigned long STORM_HOLD_MS = 1800000UL; // stay in storm mode until still for 30 min

unsigned long intervalMs = 5000;   // dry-weather interval (bench default; ~300000 in the field)
float airTempC = 20.0;

float est = NAN;    // filtered distance to the water (cm)
float rate = 0;     // cm per minute (negative = water coming closer = rising)
float lastErr = 0;
byte suspect = 0;   // how many readings in a row were rejected
bool storm = false;
unsigned long lastReadingMs = 0, lastMoveMs = 0;

// ---------- 1. one reading = median of 5 pings ----------
float pingCm() {
  digitalWrite(TRIG_PIN, LOW);  delayMicroseconds(2);
  digitalWrite(TRIG_PIN, HIGH); delayMicroseconds(10);
  digitalWrite(TRIG_PIN, LOW);
  unsigned long us = pulseIn(ECHO_PIN, HIGH, ECHO_TIMEOUT_US);
  if (us == 0) return NAN;
  float speedCmPerUs = (331.3 + 0.606 * airTempC) / 10000.0;   // speed of sound vs temperature
  return us * speedCmPerUs / 2.0;                                // there and back
}

float medianCm(int &good) {
  float v[PINGS];
  good = 0;
  for (int i = 0; i < PINGS; i++) {
    float d = pingCm();
    if (!isnan(d)) {                       // insert in order (keeps the array sorted)
      int j = good++;
      while (j > 0 && v[j - 1] > d) { v[j] = v[j - 1]; j--; }
      v[j] = d;
    }
    delay(PING_GAP_MS);
  }
  return good ? v[good / 2] : NAN;
}

// ---------- 2. tracking loop ----------
void track(float meas, float dtMin) {
  if (isnan(meas)) return;                          // no echo: keep the last estimate
  if (isnan(est)) { est = meas; return; }           // first reading
  float pred = est + rate * dtMin;                  // where we expect the water now
  float err = meas - pred;                          // the surprise
  if (fabs(err) > GATE_CM) {
    if (++suspect < 3) { est = pred; return; }      // probably a false echo: ignore it
    est = meas; rate = 0; suspect = 0; lastErr = 0; // 3 in a row: it's real (or the sensor moved)
    return;
  }
  suspect = 0;
  est = pred + KP * err + KD * (err - lastErr);     // P (+ D) correct the level
  rate += KI * err / dtMin;                         // I corrects the rate
  lastErr = err;
}

// ---------- commands from the computer ----------
void handleCommands() {
  while (Serial.available()) {
    String line = Serial.readStringUntil('\n');
    line.trim();
    if (line.startsWith("I,")) {
      long ms = line.substring(2).toInt();
      if (ms >= 500 && ms <= 3600000L) { intervalMs = ms; Serial.print("OK,I,"); Serial.println(intervalMs); }
      else Serial.println("ERR,I,out of range (500 to 3600000 ms)");
    } else if (line.startsWith("T,")) {
      airTempC = line.substring(2).toFloat();
      Serial.print("OK,T,"); Serial.println(airTempC, 1);
    } else if (line == "?") {
      Serial.print("OK,STATUS,interval_ms="); Serial.print(intervalMs);
      Serial.print(",temp_c="); Serial.print(airTempC, 1);
      Serial.print(",storm="); Serial.println(storm ? 1 : 0);
    }
  }
}

void setup() {
  Serial.begin(9600);
  Serial.setTimeout(50);
  pinMode(TRIG_PIN, OUTPUT);
  pinMode(ECHO_PIN, INPUT);
  Serial.println("HELLO,DrainShield,2");
}

void loop() {
  handleCommands();
  unsigned long wait = storm ? min(intervalMs, STORM_INTERVAL_MS) : intervalMs;
  if (lastReadingMs != 0 && millis() - lastReadingMs < wait) return;

  float dtMin = lastReadingMs ? (millis() - lastReadingMs) / 60000.0 : 0;
  lastReadingMs = millis();
  int good;
  float raw = medianCm(good);
  track(raw, dtMin);

  // ---------- 3. storm mode ----------
  if (fabs(rate) > STORM_RATE) { storm = true; lastMoveMs = millis(); }
  else if (storm && millis() - lastMoveMs > STORM_HOLD_MS) storm = false;

  Serial.print("DIST,");
  if (isnan(raw) || isnan(est)) Serial.print("NaN"); else Serial.print(est, 1);  // no echo now -> say so
  Serial.print(","); Serial.print(good);
  Serial.print(","); Serial.print(fabs(rate) < 0.005 ? 0.0 : -rate, 2);          // + = rising
  Serial.print(","); if (isnan(raw)) Serial.println("NaN"); else Serial.println(raw, 1);
}
