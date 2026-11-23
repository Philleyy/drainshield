"""
season.py: the time of year sets how closely DrainShield watches the basins.

Every city we asked named the same two risky seasons: spring (snowmelt carries the winter's road grit into the
basins) and fall (leaves). In those months a smaller storm is worth cleaning before, and sensors read more often
in dry weather. In winter they read less often to save battery.

shortcut: the bridges/firmware still use their own dry-weather interval; they get this one in the upload reply
(dry_every_s) and should follow it once the firmware reads that field.
"""

SEASONS = {   # heavy_mm: forecast total (next 12 h) that triggers "clean before the storm"
    "spring": {"risk": True, "heavy_mm": 10, "dry_every_min": 15},
    "summer": {"risk": False, "heavy_mm": 15, "dry_every_min": 30},
    "fall": {"risk": True, "heavy_mm": 10, "dry_every_min": 15},
    "winter": {"risk": False, "heavy_mm": 15, "dry_every_min": 60},
}


def key(ts):
    md = (ts.month, ts.day)
    if (3, 15) <= md <= (5, 31):
        return "spring"
    if (6, 1) <= md <= (9, 14):
        return "summer"
    if (9, 15) <= md <= (11, 30):
        return "fall"
    return "winter"


def info(ts):
    k = key(ts)
    return {"key": k, **SEASONS[k]}

