"""
sensor_bridge.py: connect a USB sensor to the DrainShield dashboard
-------------------------------------------------------------------
The Arduino sends its readings over the USB cable (the "serial port"). This script
listens to that port and appends each reading to data/live_readings.csv, which the
dashboard reads. It also passes the reading interval you choose in the dashboard
(Live sensor page) back to the Arduino.

    [ultrasonic sensor] -> [Arduino] --USB--> [sensor_bridge.py] -> data/live_readings.csv -> [dashboard]
                                         <-- "I,5000" (new interval) <-- data/sensor_settings.json <--

HOW TO USE (in a second terminal, while the dashboard is running in the first one):
    python sensor_bridge.py                      -> lists the serial ports, e.g. COM3
    python sensor_bridge.py COM3 --basin TEST-01  -> starts recording for basin TEST-01
Stop it with Ctrl+C. Close the Arduino IDE's Serial Monitor first: only one program
can use the port at a time.

It understands two kinds of Arduino output:
    DIST,123.4,5,0.20,123.6   (drainshield_sensor.ino: filtered distance in cm, good pings,
                               rise rate in cm/min, raw distance; only the filtered distance is saved)
    Distance: 123.4           (your first test sketch)
With the first test sketch (which sends 20 readings a second), the bridge keeps one
reading per interval: the median of what it received, to ignore false echoes.
"""

import argparse
import csv
import json
import os
import statistics
import sys
import time
from datetime import datetime

import uploader

LIVE_FILE = os.path.join("data", "live_readings.csv")
SETTINGS_FILE = os.path.join("data", "sensor_settings.json")
STATUS_FILE = os.path.join("data", "sensor_status.json")
DEFAULT_INTERVAL_S = 5


def list_ports():
    from serial.tools import list_ports as lp
    ports = list(lp.comports())
    if not ports:
        print("No serial port found. Is the Arduino plugged in? (Try another USB cable: some only charge.)")
    for p in ports:
        print(f"  {p.device:8s} {p.description}")
    return ports


def read_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def write_status(basin, **info):
    status = read_json(STATUS_FILE)
    status.setdefault(basin, {}).update(info)
    with open(STATUS_FILE, "w", encoding="utf-8") as f:
        json.dump(status, f, indent=2)


def save_reading(basin, distance_cm):
    new = not os.path.exists(LIVE_FILE)
    with open(LIVE_FILE, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["basin_id", "timestamp", "distance_cm", "battery_v"])
        stamp = datetime.now().isoformat(timespec="seconds")
        w.writerow([basin, stamp, "" if distance_cm is None else round(distance_cm, 1), ""])  # USB: no battery
    return stamp


def parse(line):
    """Return ('dist', cm or None), ('ok', text), ('hello', text) or (None, None)."""
    line = line.strip()
    if line.startswith("DIST,"):
        parts = line.split(",")
        try:
            value = float(parts[1])
            return "dist", (None if value != value else value)      # NaN -> None (no echo)
        except ValueError:
            return "dist", None
    if line.lower().startswith("distance:"):
        try:
            value = float(line.split(":", 1)[1])
            return "legacy", (value if value > 0 else None)          # 0 = no echo in the first sketch
        except ValueError:
            return None, None
    if line.startswith("OK,") or line.startswith("ERR,"):
        return "ok", line
    if line.startswith("HELLO"):
        return "hello", line
    return None, None


REC_ON_USB = 0x20            # same flag the LoRa firmware uses


def run(port, basin, baud, up=None):
    import serial
    os.makedirs("data", exist_ok=True)
    ser = serial.serial_for_url(port, baud, timeout=0.5)   # "COM3", "/dev/ttyUSB0"... (or a test URL)
    print(f"Connected to {port}. Recording basin {basin} into {LIVE_FILE}. Ctrl+C to stop.")
    time.sleep(2)                                       # the Arduino restarts when the port opens
    ser.reset_input_buffer()

    interval_s = None
    sent_interval = None
    firmware = "unknown"
    buffer, window_start = [], time.time()
    last_settings_check = 0

    while True:
        # 1. Did someone change the interval in the dashboard?
        if time.time() - last_settings_check > 2:
            last_settings_check = time.time()
            interval_s = read_json(SETTINGS_FILE).get(basin, {}).get("interval_s", DEFAULT_INTERVAL_S)
            if interval_s != sent_interval:
                ser.write(f"I,{int(interval_s * 1000)}\n".encode())   # ignored by the first test sketch
                sent_interval = interval_s
                write_status(basin, requested_interval_s=interval_s, port=port)
                print(f"   interval set to {interval_s} s")

        # 2. Read one line from the Arduino
        raw = ser.readline().decode(errors="ignore")
        if up:
            up.flush()                                  # retries anything waiting (every 30 s at most)
        kind, value = parse(raw) if raw else (None, None)

        if kind == "dist":                              # DrainShield sketch: one line = one reading
            firmware = "drainshield"
            stamp = save_reading(basin, value)
            write_status(basin, firmware=firmware, last_seen=stamp, last_distance_cm=value)
            if up:
                up.send([uploader.reading(basin, stamp, None if value is None else round(value, 1),
                                          flags=REC_ON_USB, mode="USB")])
            extra = raw.strip().split(",")
            try:
                rise = f"  water {float(extra[3]):+.2f} cm/min" if float(extra[3]) != 0 else ""
            except (IndexError, ValueError):
                rise = ""
            print(f"{stamp}  {basin}  {'no echo' if value is None else f'{value:.1f} cm'}{rise}")
        elif kind == "legacy":                          # first test sketch: keep 1 reading per interval
            firmware = "basic test sketch"
            if value is not None:
                buffer.append(value)
        elif kind in ("ok", "hello"):
            print(f"   Arduino says: {value}")
            if value.startswith("OK,I,"):
                write_status(basin, device_interval_ms=int(value.split(",")[2]))

        if firmware == "basic test sketch" and time.time() - window_start >= interval_s:
            median = statistics.median(buffer) if buffer else None
            stamp = save_reading(basin, median)
            write_status(basin, firmware=firmware, last_seen=stamp, last_distance_cm=median)
            if up:
                up.send([uploader.reading(basin, stamp, None if median is None else round(median, 1),
                                          flags=REC_ON_USB, mode="USB")])
            print(f"{stamp}  {basin}  {'no echo' if median is None else f'{median:.1f} cm'}  "
                  f"(median of {len(buffer)})")
            buffer, window_start = [], time.time()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Send Arduino sensor readings to the DrainShield dashboard.")
    parser.add_argument("port", nargs="?", help="serial port, e.g. COM3 (leave empty to list ports)")
    parser.add_argument("--basin", default="TEST-01", help="basin ID these readings belong to (default TEST-01)")
    parser.add_argument("--baud", type=int, default=9600, help="must match Serial.begin() in the sketch")
    uploader.add_arguments(parser)
    args = parser.parse_args()
    try:
        import serial  # noqa: F401
    except ImportError:
        sys.exit("pyserial is missing. Run:  python -m pip install pyserial")
    if not args.port:
        print("Serial ports on this computer:")
        list_ports()
        print("\nThen run:  python sensor_bridge.py COM3 --basin TEST-01   (with your port)")
        sys.exit(0)
    try:
        run(args.port, args.basin, args.baud, uploader.from_args(args))
    except KeyboardInterrupt:
        print("\nStopped.")
