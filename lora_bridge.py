"""
lora_bridge.py: connect the DrainShield LoRa receiver to the dashboard
---------------------------------------------------------------------
    [node 1] ~~LoRa~~\
    [node 2] ~~LoRa~~-> [receiver board] --USB--> [lora_bridge.py] -> data/live_readings.csv -> [dashboard]
    [receiver's own sensor] ------/                       |   data/node_telemetry.csv (raw, temperature, radio)
                                  <-- "M,<node>,<mode>" --+-- data/sensor_settings.json <-- polling_controller.py

The receiver (drainshield_lora.ino, ROLE_RECEIVER) prints one JSON line per packet:
    {"type":"pkt","node":1,"first":42,"mode":0,"backlog":0,"rssi":-38.5,"snr":9.8,
     "records":[[age_s, raw_mm, filt_mm, rise_x10, temp_c, batt_20mv, flags], ...]}
This script:
  * rebuilds each reading's time as (time received - age_s): the node needs no real-time clock;
  * drops duplicates (an ACK lost on the way back -> the node sends the same readings again): each reading
    has a running number, and we remember the last one saved per node (data/lora_seen.json);
  * writes the dashboard's usual data contract (basin_id, timestamp, distance_cm, battery_v);
  * every 2 s, passes the mode chosen by polling_controller.py (or the interval set on the Live sensor
    page) back to the receiver, which puts it in its next ACK to that node.

Which basin is node 1? The bridge looks for a monitored basin whose sensor_id is "1", "DS-01" or "NODE-01"
(set it on the Add basin page), or use --map 1=PILOT-A,2=PILOT-B. Unmapped nodes are saved as NODE-01...

    python lora_bridge.py                          (lists the serial ports)
    python lora_bridge.py COM5
    python lora_bridge.py COM5 --map 1=TEST-01,2=TEST-02,3=TEST-03
"""

import argparse
import csv
import json
import os
import sys
import time
from datetime import datetime, timedelta

DATA = "data"
LIVE_FILE = os.path.join(DATA, "live_readings.csv")
TELEMETRY_FILE = os.path.join(DATA, "node_telemetry.csv")
SETTINGS_FILE = os.path.join(DATA, "sensor_settings.json")
STATUS_FILE = os.path.join(DATA, "sensor_status.json")
SEEN_FILE = os.path.join(DATA, "lora_seen.json")
MONITORED_FILE = os.path.join(DATA, "monitored_basins.csv")
BAUD = 115200

MODES = ["DRY", "WATCH", "STORM"]
REC_NO_ECHO, REC_AT_BLIND, REC_SUSPECT, REC_ICED, REC_CLOCK_GAP, REC_ON_USB = 0x01, 0x02, 0x04, 0x08, 0x10, 0x20
BLIND_ZONE_CM = 3.0                     # A02YYUW: a reading "at the sensor" is saved as this distance
TELEMETRY_COLUMNS = ["received", "timestamp", "node", "basin_id", "index", "raw_mm", "filtered_mm",
                     "rise_mm_min", "temp_c", "battery_v", "flags", "flag_text", "rssi", "snr", "mode", "backlog"]


def read_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def write_json(path, data):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)


def flag_text(flags):
    names = [(REC_AT_BLIND, "water at sensor"), (REC_NO_ECHO, "no echo"), (REC_ICED, "sensor iced?"),
             (REC_SUSPECT, "false echo rejected"), (REC_CLOCK_GAP, "after power loss"), (REC_ON_USB, "USB power")]
    return ", ".join(n for bit, n in names if flags & bit)


def node_map(cli_map=None, monitored_file=MONITORED_FILE):
    """{node_id: basin_id} from --map, then from monitored_basins.csv sensor_id."""
    mapping = {}
    if os.path.exists(monitored_file):
        with open(monitored_file, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                sid = (row.get("sensor_id") or "").strip().upper()
                for prefix in ("DS-", "NODE-", "NODE", "DS"):
                    if sid.startswith(prefix):
                        sid = sid[len(prefix):]
                if sid.isdigit():
                    mapping[int(sid)] = row["basin_id"]
    if cli_map:
        for part in cli_map.split(","):
            node, basin = part.split("=")
            mapping[int(node)] = basin.strip()
    return mapping


def basin_for(node, mapping):
    return mapping.get(node, f"NODE-{node:02d}")


def decode(line, received, mapping, seen):
    """One JSON line from the receiver -> list of reading dicts (new ones only). Updates `seen` in place."""
    try:
        msg = json.loads(line)
    except ValueError:
        return None, []
    if msg.get("type") != "pkt":
        return msg, []
    node, first = int(msg["node"]), int(msg["first"])
    last_saved = seen.get(str(node), -1)
    if first == 0 and last_saved >= len(msg["records"]):      # counter restarted (flash erased, receiver reboot)
        last_saved = -1
    out = []
    for i, rec in enumerate(msg["records"]):
        index = first + i
        if index <= last_saved:
            continue                                          # duplicate (resent after a lost ACK)
        age, raw, filt, rise10, temp, batt20, flags = rec
        ts = received - timedelta(seconds=int(age))
        if flags & REC_AT_BLIND:
            dist_cm = BLIND_ZONE_CM                            # water at/above the sensor: HIGH, not an error
        elif flags & REC_NO_ECHO or filt == 0:
            dist_cm = None
        else:
            dist_cm = round(filt / 10, 1)
        out.append({"node": node, "basin_id": basin_for(node, mapping), "index": index,
                    "timestamp": ts.replace(microsecond=0), "distance_cm": dist_cm,
                    "battery_v": None if flags & REC_ON_USB or batt20 == 0 else round(batt20 * 0.02, 2),
                    "raw_mm": raw, "filtered_mm": filt, "rise_mm_min": rise10 / 10, "temp_c": temp,
                    "flags": flags, "rssi": msg.get("rssi"), "snr": msg.get("snr"),
                    "mode": MODES[msg.get("mode", 0)] if msg.get("mode", 0) < 3 else "?",
                    "backlog": msg.get("backlog", 0)})
        seen[str(node)] = index
    return msg, out


def append_rows(readings, received, live_file=LIVE_FILE, telemetry_file=TELEMETRY_FILE):
    os.makedirs(os.path.dirname(live_file) or ".", exist_ok=True)
    readings = sorted(readings, key=lambda r: r["timestamp"])
    new = not os.path.exists(live_file)
    with open(live_file, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["basin_id", "timestamp", "distance_cm", "battery_v"])
        for r in readings:
            w.writerow([r["basin_id"], r["timestamp"].isoformat(), "" if r["distance_cm"] is None else r["distance_cm"],
                        "" if r["battery_v"] is None else r["battery_v"]])
    new = not os.path.exists(telemetry_file)
    with open(telemetry_file, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(TELEMETRY_COLUMNS)
        for r in readings:
            w.writerow([received.isoformat(timespec="seconds"), r["timestamp"].isoformat(), r["node"], r["basin_id"],
                        r["index"], r["raw_mm"], r["filtered_mm"], r["rise_mm_min"], r["temp_c"],
                        "" if r["battery_v"] is None else r["battery_v"], r["flags"], flag_text(r["flags"]),
                        "" if r["rssi"] is None else r["rssi"], "" if r["snr"] is None else r["snr"],
                        r["mode"], r["backlog"]])


def update_status(readings, status_file=STATUS_FILE):
    status = read_json(status_file)
    for r in readings:
        s = status.setdefault(r["basin_id"], {})
        s.update(firmware="DrainShield LoRa v3", node=r["node"], last_seen=r["timestamp"].isoformat(),
                 last_distance_cm=r["distance_cm"], mode=r["mode"], backlog=r["backlog"], temp_c=r["temp_c"],
                 flags=flag_text(r["flags"]))
        if r["rssi"] is not None:
            s.update(rssi=r["rssi"], snr=r["snr"])
    write_json(status_file, status)


def wanted_modes(mapping, settings):
    """{node: mode number} from sensor_settings.json: 'mode' (polling_controller.py) or, failing that, the
    interval set on the Live sensor page (<= 90 s -> STORM, <= 10 min -> WATCH, else DRY)."""
    out = {}
    for node, basin in mapping.items():
        s = settings.get(basin, {})
        if s.get("mode") in MODES:
            out[node] = MODES.index(s["mode"])
        elif "interval_s" in s:
            sec = float(s["interval_s"])
            out[node] = 2 if sec <= 90 else 1 if sec <= 600 else 0
    return out


def run(port, cli_map):
    import serial
    ser = serial.serial_for_url(port, BAUD, timeout=0.5)
    print(f"Connected to {port}. Ctrl+C to stop.")
    time.sleep(2)
    ser.reset_input_buffer()
    seen = read_json(SEEN_FILE)
    sent_modes, last_check, mapping = {}, 0, node_map(cli_map)
    print("Nodes -> basins:", mapping or "none mapped yet (saved as NODE-01, NODE-02...)")
    while True:
        if time.time() - last_check > 2:                      # pass the dashboard's choice to the receiver
            last_check = time.time()
            mapping = node_map(cli_map)
            for node, mode in wanted_modes(mapping, read_json(SETTINGS_FILE)).items():
                if sent_modes.get(node) != mode:
                    ser.write(f"M,{node},{mode}\n".encode())
                    sent_modes[node] = mode
                    print(f"   node {node} ({basin_for(node, mapping)}) -> {MODES[mode]} at its next transmission")
        raw = ser.readline().decode(errors="ignore").strip()
        if not raw:
            continue
        received = datetime.now()
        msg, rows = decode(raw, received, mapping, seen)
        if msg is None:
            print(f"   receiver: {raw}")
            continue
        if msg.get("type") != "pkt":
            print(f"   receiver: {raw}")
            if msg.get("type") == "hello":
                sent_modes.clear()                            # receiver restarted: resend the modes
                seen.pop(str(msg.get("node")), None)          # and its own sensor counts from 0 again
            continue
        if rows:
            append_rows(rows, received)
            update_status(rows)
            write_json(SEEN_FILE, seen)
        radio = "" if msg.get("rssi") is None else f"  {msg['rssi']:.0f} dBm"
        for r in rows:
            d = "no echo" if r["distance_cm"] is None else f"{r['distance_cm']:.1f} cm"
            extra = f"  [{flag_text(r['flags'])}]" if r["flags"] & ~REC_ON_USB else ""
            print(f"{r['timestamp']:%H:%M:%S}  {r['basin_id']:10s} {d:>9s}  {r['mode']:5s}{radio}{extra}")
        if not rows:
            print(f"   node {msg['node']}: duplicate packet ignored (lost ACK, resent)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="DrainShield LoRa receiver -> dashboard.")
    ap.add_argument("port", nargs="?", help="serial port of the receiver, e.g. COM5 (empty = list ports)")
    ap.add_argument("--map", help="node to basin, e.g. 1=TEST-01,2=TEST-02,3=TEST-03")
    args = ap.parse_args()
    try:
        import serial  # noqa: F401
        from serial.tools import list_ports
    except ImportError:
        sys.exit("pyserial is missing. Run:  python -m pip install pyserial")
    if not args.port:
        for p in list_ports.comports():
            print(f"  {p.device:8s} {p.description}")
        print("\nThen run:  python lora_bridge.py COM5   (with the receiver's port)")
        sys.exit(0)
    try:
        run(args.port, args.map)
    except KeyboardInterrupt:
        print("\nStopped.")
