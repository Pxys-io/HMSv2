"""Vitals reference ranges + flagging (Plan/14 D3)."""

from app.services.settings import get_setting

DEFAULT_RANGES = {
    "bp_sys": {"min": 90, "max": 140, "unit": "mmHg"},
    "bp_dia": {"min": 60, "max": 90, "unit": "mmHg"},
    "hr": {"min": 60, "max": 100, "unit": "bpm"},
    "temp": {"min": 36.0, "max": 37.5, "unit": "°C"},
    "spo2": {"min": 95, "max": 100, "unit": "%"},
    "weight": {"min": None, "max": None, "unit": "kg"},
    "height": {"min": None, "max": None, "unit": "cm"},
}


def reference_ranges(db) -> dict:
    stored = get_setting(db, "vitals.reference_ranges", None)
    if not isinstance(stored, dict):
        return DEFAULT_RANGES
    merged = dict(DEFAULT_RANGES)
    for key, rng in stored.items():
        if isinstance(rng, dict) and key in merged:
            merged[key] = {**merged[key], **rng}
    return merged


def flag_vitals(db, vitals: dict | None) -> dict | None:
    """Returns vitals with `{key}_flag` fields (low/high/normal) per ranges."""
    if not vitals:
        return vitals
    ranges = reference_ranges(db)
    out = dict(vitals)
    for key, value in vitals.items():
        if key in ranges and isinstance(value, int | float) and not isinstance(value, bool):
            lo = ranges[key].get("min")
            hi = ranges[key].get("max")
            if lo is None or hi is None:
                out[f"{key}_flag"] = "normal"
            elif value < lo:
                out[f"{key}_flag"] = "low"
            elif value > hi:
                out[f"{key}_flag"] = "high"
            else:
                out[f"{key}_flag"] = "normal"
    return out
