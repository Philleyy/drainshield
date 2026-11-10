"""
weather.py
----------
Rain forecasts, for the "inspect before the storm" logic.

* In the demo, the forecast for the next 12 h is simply the simulated rain that is
  about to fall (a perfect forecast). That lets the predictive logic be tested.
* live_forecast() fetches the REAL forecast from Environment Canada's GEM/HRDPS model
  through Open-Meteo (free, no API key). It needs internet; it returns None if offline.
* RADAR_TILES is the live Environment Canada (MSC GeoMet) 1 km precipitation radar,
  shown as a map layer.
"""

import json
import urllib.request

import pandas as pd
import streamlit as st

HEAVY_RAIN_MM = 15          # 15 mm or more in the next 12 h counts as heavy rain
FORECAST_HOURS = 12

OPEN_METEO = ("https://api.open-meteo.com/v1/gem?latitude={lat}&longitude={lon}"
              "&hourly=precipitation,precipitation_probability&forecast_days=2&timezone=America%2FToronto")
RADAR_TILES = ("https://geo.weather.gc.ca/geomet?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetMap&FORMAT=image/png"
               "&TRANSPARENT=TRUE&LAYERS=RADAR_1KM_RRAI&STYLES=&CRS=EPSG:3857&WIDTH=256&HEIGHT=256"
               "&BBOX={bbox-epsg-3857}")


def simulated_forecast(rain, now, hours=FORECAST_HOURS):
    """Rain in the next `hours` from the simulated record: total mm, max hourly mm/h, start time."""
    window = rain[(rain["timestamp"] > now) & (rain["timestamp"] <= now + pd.Timedelta(hours=hours))]
    wet = window[window["rain_mm"] > 0]
    hourly = window.set_index("timestamp")["rain_mm"].resample("h").sum() if not window.empty else pd.Series()
    return {"total_mm": float(window["rain_mm"].sum()),
            "max_mm_h": float(hourly.max()) if not hourly.empty else 0.0,
            "starts": wet["timestamp"].iloc[0] if not wet.empty else None,
            "source": "simulated"}


@st.cache_data(ttl=1800, show_spinner=False)
def live_forecast(lat, lon, hours=FORECAST_HOURS):
    """Real forecast for the next `hours` (Environment Canada GEM via Open-Meteo), or None if offline."""
    try:
        with urllib.request.urlopen(OPEN_METEO.format(lat=lat, lon=lon), timeout=8) as response:
            data = json.load(response)["hourly"]
    except Exception:
        return None
    df = pd.DataFrame({"time": pd.to_datetime(data["time"]), "mm": data["precipitation"],
                       "prob": data["precipitation_probability"]})
    now = pd.Timestamp.now(tz="America/Toronto").tz_localize(None).floor("h")
    nxt = df[(df["time"] >= now) & (df["time"] < now + pd.Timedelta(hours=hours))].fillna(0)
    wet = nxt[nxt["mm"] > 0]
    return {"total_mm": float(nxt["mm"].sum()), "max_mm_h": float(nxt["mm"].max() if not nxt.empty else 0),
            "max_prob": float(nxt["prob"].max() if not nxt.empty else 0),
            "starts": wet["time"].iloc[0] if not wet.empty else None, "source": "live"}


def describe(fc):
    """'🌧️ 30 mm expected in the next 12 h · max 30 mm/h' or a dry message."""
    if fc is None:
        return "Forecast unavailable"
    if fc["total_mm"] < 0.5:
        return f"☀️ No significant rain expected in the next {FORECAST_HOURS} h"
    when = f" · starts {fc['starts']:%a %H:%M}" if fc.get("starts") is not None else ""
    return (f"🌧️ {fc['total_mm']:.0f} mm expected in the next {FORECAST_HOURS} h · "
            f"max {fc['max_mm_h']:.0f} mm/h{when}")


def is_heavy(fc):
    return fc is not None and fc["total_mm"] >= HEAVY_RAIN_MM
