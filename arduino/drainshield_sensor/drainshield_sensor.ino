// DrainShield sensor sketch (v1) - ultrasonic distance for the DrainShield dashboard
// Board: Arduino Uno / Nano (5 V). Sensor: trigger/echo type (HC-SR04, JSN-SR04T, AJ-SR04M...).
//
// What it sends over USB (one line per reading):      DIST,<distance cm>,<good pings out of 5>
//   e.g.  DIST,123.4,5      or   DIST,NaN,0   (no echo at all)
// What it accepts from the computer (sensor_bridge.py sends these):
//   I,<milliseconds>   reading interval, 500 to 3600000  (e.g. I,5000 = every 5 s)
//   T,<deg C>          air temperature inside the basin, for the speed of sound
//   ?                  print the current settings
//
// Improvements over the first test sketch:
//  1. pulseIn() has a timeout, so a missing echo doesn't freeze the loop for 1 s.
//  2. Each reading is the MEDIAN of 5 pings, which removes false echoes (walls, ladder rungs).
//  3. 60 ms between pings so the previous echo has died out (needed by JSN-SR04T-type sensors).
//  4. The speed of sound is corrected for temperature: at 0 C it's ~3.5 % slower than at 20 C,
//     which is about 5 cm of error over 1.4 m in a catch basin in winter.
//  5. The reading interval can be changed from the dashboard, without re-uploading the sketch.
//  6. A machine-readable output format that the bridge can't misread.

const int TRIG_PIN = 13;   // (pin 13 also drives the board's LED: it will flicker, that's normal)
const int ECHO_PIN = 12;

const int PINGS_PER_READING = 5;
const unsigned long PING_GAP_MS = 60;           // let the previous echo die out
const unsigned long ECHO_TIMEOUT_US = 30000UL;  // ~5 m round trip; no echo -> give up

unsigned long intervalMs = 5000;   // time between readings (changed by "I,<ms>")
float airTempC = 20.0;             // changed by "T,<deg C>" (later: from a temperature sensor)
unsigned long lastReadingMs = 0;

// Speed of sound in cm per microsecond, corrected for air temperature
float soundCmPerUs() {
  return (331.3 + 0.606 * airTempC) / 10000.0;
}

// One ping: distance in cm, or NAN if no echo came back
float pingOnceCm() {
  digitalWrite(TRIG_PIN, LOW);
  delayMicroseconds(2);
  digitalWrite(TRIG_PIN, HIGH);
  delayMicroseconds(10);
  digitalWrite(TRIG_PIN, LOW);
  unsigned long duration = pulseIn(ECHO_PIN, HIGH, ECHO_TIMEOUT_US);
  if (duration == 0) return NAN;
  return duration * soundCmPerUs() / 2.0;   // there and back: divide by 2
}

// Median of several pings; also returns how many pings got an echo
float readDistanceCm(int &goodPings) {
  float values[PINGS_PER_READING];
  goodPings = 0;
  for (int i = 0; i < PINGS_PER_READING; i++) {
    float d = pingOnceCm();
    if (!isnan(d)) values[goodPings++] = d;
    delay(PING_GAP_MS);
  }
  if (goodPings == 0) return NAN;
  for (int i = 1; i < goodPings; i++) {          // sort (insertion sort, small array)
    float v = values[i];
    int j = i - 1;
    while (j >= 0 && values[j] > v) { values[j + 1] = values[j]; j--; }
    values[j + 1] = v;
  }
  return values[goodPings / 2];
}

// Commands from the computer
void handleCommands() {
  while (Serial.available()) {
    String line = Serial.readStringUntil('\n');
    line.trim();
    if (line.startsWith("I,")) {
      long ms = line.substring(2).toInt();
      if (ms >= 500 && ms <= 3600000L) {
        intervalMs = ms;
        Serial.print("OK,I,"); Serial.println(intervalMs);
      } else {
        Serial.println("ERR,I,out of range (500 to 3600000 ms)");
      }
    } else if (line.startsWith("T,")) {
      airTempC = line.substring(2).toFloat();
      Serial.print("OK,T,"); Serial.println(airTempC, 1);
    } else if (line == "?") {
      Serial.print("OK,STATUS,interval_ms="); Serial.print(intervalMs);
      Serial.print(",temp_c="); Serial.println(airTempC, 1);
    }
  }
}

void setup() {
  Serial.begin(9600);
  Serial.setTimeout(50);
  pinMode(TRIG_PIN, OUTPUT);
  pinMode(ECHO_PIN, INPUT);
  digitalWrite(TRIG_PIN, LOW);
  Serial.println("HELLO,DrainShield,1");
}

void loop() {
  handleCommands();
  if (millis() - lastReadingMs >= intervalMs || lastReadingMs == 0) {
    lastReadingMs = millis();
    int good;
    float d = readDistanceCm(good);
    Serial.print("DIST,");
    if (isnan(d)) Serial.print("NaN"); else Serial.print(d, 1);
    Serial.print(",");
    Serial.println(good);
  }
}
