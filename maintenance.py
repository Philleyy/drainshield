"""
maintenance.py
--------------
The crew's maintenance log, and the life cycle of each issue:

    Detected (unverified)  ->  Verified / crew dispatched  ->  Resolved

Each entry is one line of data/maintenance_log.csv:
    basin_id, time, action, sediment_mm, note
`time` is the moment the crew did it (in the demo: the replay time).
"Cleaned / vacuumed" and "No issue found" close the issue: storms before that
moment no longer count, and the sediment estimate restarts from what the crew measured.
"""

import os

import pandas as pd

LOG_FILE = os.path.join("data", "maintenance_log.csv")
COLUMNS = ["basin_id", "time", "action", "sediment_mm", "note"]

ACTIONS = ["Crew dispatched", "Inspected", "Obstruction found", "Requires further investigation",
           "Cleaned / vacuumed", "No issue found"]
RESOLVES = {"Cleaned / vacuumed", "No issue found"}


def load():
    if not os.path.exists(LOG_FILE):
        return pd.DataFrame(columns=COLUMNS)
    return pd.read_csv(LOG_FILE, parse_dates=["time"])


def add(basin_id, time, action, sediment_mm=None, note=""):
    log = load()
    entry = pd.DataFrame([{"basin_id": basin_id, "time": time, "action": action,
                           "sediment_mm": sediment_mm, "note": note}])
    log = pd.concat([log, entry], ignore_index=True) if not log.empty else entry
    os.makedirs("data", exist_ok=True)
    log.to_csv(LOG_FILE, index=False)


def for_basin(log, basin_id, now):
    """Entries for one basin that happened before `now`, newest last."""
    if log.empty:
        return log
    return log[(log["basin_id"] == basin_id) & (log["time"] <= now)].sort_values("time")


def last_reset(entries):
    """(time, measured sediment in cm or None) of the last visit that closed the issue, or None."""
    done = entries[entries["action"].isin(RESOLVES)] if not entries.empty else entries
    if done.empty:
        return None
    last = done.iloc[-1]
    if last["action"] == "No issue found":     # false alarm: keep the sediment estimate as it was
        return last["time"], None
    sed = last["sediment_mm"]
    return last["time"], (float(sed) / 10 if pd.notna(sed) else 0.0)


def lifecycle(S, entries):
    """Where the current issue stands: None (no issue), 'Detected (unverified)' or
    'Verified / crew dispatched'. (Resolved issues don't show: the status is back to normal.)"""
    if S["status"] in ("ok", "no_data") or S.get("issue_since") is None:
        return None
    after = entries[entries["time"] >= S["issue_since"]] if not entries.empty else entries
    return "Verified / crew dispatched" if not after.empty else "Detected (unverified)"
