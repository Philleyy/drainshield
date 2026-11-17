"""
weather.py
----------
Rain forecasts, for the "inspect before the storm" logic.

* rain_series() fetches the REAL hourly rain from Environment Canada's GEM model through
  Open-Meteo (free, no API key): the past 7 days (to recognise storms) and the next 2 days
  (the forecast). It needs internet; offline it returns an empty table.
* RADAR_TILES is the live Environment Canada (MSC GeoMet) 1 km precipitation radar,
  shown as a map layer.
"""

import json
import time

import pandas as pd
import streamlit as st

import net

HEAVY_RAIN_MM = 15          # 15 mm or more in the next 12 h counts as heavy rain
FORECAST_HOURS = 12

OPEN_METEO = ("https://api.open-meteo.com/v1/gem?latitude={lat}&longitude={lon}"
              "&hourly=precipitation&past_days=7&forecast_days=2&timezone=America%2FToronto")
# The same Environment Canada GEM data from a second Open-Meteo server, for networks that can't reach the first
# (the website's host can't). Whichever answered last is tried first.
OPEN_METEO_BACKUP = ("https://historical-forecast-api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
                     "&hourly=precipitation&past_days=7&forecast_days=2&models=gem_seamless"
                     "&timezone=America%2FToronto")
_sources = [OPEN_METEO, OPEN_METEO_BACKUP]
RETRY_AFTER_S = 120         # after a failed download, don't make every page wait for the next 2 minutes
_failed_at = 0.0
RADAR_TILES = ("https://geo.weather.gc.ca/geomet?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetMap&FORMAT=image/png"
               "&TRANSPARENT=TRUE&LAYERS=RADAR_1KM_RRAI&STYLES=&CRS=EPSG:3857&WIDTH=256&HEIGHT=256"
               "&BBOX={bbox-epsg-3857}")


def empty_rain():
    return pd.DataFrame({"timestamp": pd.Series(dtype="datetime64[ns]"), "rain_mm": pd.Series(dtype=float)})


@st.cache_data(ttl=1800, show_spinner=False)
def _download_rain(lat, lon):
    """Cached for 30 min. Raises when offline, so a failed download is not cached (retried next refresh)."""
    for url in list(_sources):
        try:
            with net.urlopen(url.format(lat=lat, lon=lon), timeout=8) as response:
                data = json.load(response)["hourly"]
            break
        except Exception as e:
            error = e
            _sources.reverse()                       # the other server goes first from now on
    else:
        raise error
    rain = pd.DataFrame({"timestamp": pd.to_datetime(data["time"]),
                         "rain_mm": pd.to_numeric(pd.Series(data["precipitation"]), errors="coerce")})
    return rain.fillna(0.0)


def rain_series(lat, lon):
    """Hourly rain (mm in each hour): past 7 days + next 2 days. Empty table if offline."""
    global _failed_at
    if time.time() - _failed_at < RETRY_AFTER_S:
        return empty_rain()
    try:
        return _download_rain(lat, lon)
    except Exception:
        _failed_at = time.time()
        return empty_rain()


def forecast_from_series(rain, now, hours=FORECAST_HOURS):
    """Rain in the next `hours`: total mm, max hourly mm/h, start time (None if no data)."""
    if rain.empty or rain["timestamp"].max() <= now:
        return None
    window = rain[(rain["timestamp"] > now) & (rain["timestamp"] <= now + pd.Timedelta(hours=hours))]
    wet = window[window["rain_mm"] > 0]
    hourly = window.set_index("timestamp")["rain_mm"].resample("h").sum()
    return {"total_mm": float(window["rain_mm"].sum()),
            "max_mm_h": float(hourly.max()) if not hourly.empty else 0.0,
            "starts": wet["timestamp"].iloc[0] if not wet.empty else None}


def describe(fc):
    """'🌧️ 30 mm expected in the next 12 h · max 30 mm/h' or a dry message."""
    if fc is None:
        return "Forecast unavailable (no internet connection)"
    if fc["total_mm"] < 0.5:
        return f"☀️ No significant rain expected in the next {FORECAST_HOURS} h"
    when = f" · starts {fc['starts']:%a %H:%M}" if fc.get("starts") is not None else ""
    return (f"🌧️ {fc['total_mm']:.0f} mm expected in the next {FORECAST_HOURS} h · "
            f"max {fc['max_mm_h']:.0f} mm/h{when}")


def is_heavy(fc):
    return fc is not None and fc["total_mm"] >= HEAVY_RAIN_MM
