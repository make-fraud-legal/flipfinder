"""Car research: known problems by model / engine / gearbox / mileage, plus red-flag
words in the ad text (LV, RU, EN, DE, PL, CZ, LT, EE)."""
from __future__ import annotations

import datetime as dt
import json
import os
import re
from functools import lru_cache
from typing import Dict, List, Optional

from . import normalize as N
from .models import Car

DATA = os.path.join(os.path.dirname(__file__), "data", "reliability.json")


@lru_cache(maxsize=1)
def kb() -> dict:
    with open(DATA, encoding="utf-8") as f:
        return json.load(f)


def family_entry(make: Optional[str], family: Optional[str]) -> Optional[dict]:
    fams = kb()["families"]
    key = f"{make}|{family}"
    e = fams.get(key)
    hops = 0
    while e and "same_as" in e and hops < 3:
        key = e["same_as"]
        e = fams.get(key)
        hops += 1
    if e:
        e = dict(e)
        e["key"] = key
    return e


def _flag_regex(words):
    parts = []
    for w in words:
        w = N.strip_accents(w.lower())
        tail = r"(?![a-zа-я])" if len(w) <= 6 else ""
        parts.append(r"(?<![a-zа-я])" + re.escape(w) + tail)
    return re.compile("|".join(parts))


@lru_cache(maxsize=1)
def _flags():
    rf = kb()["red_flags"]
    return {k: (_flag_regex(v), v) for k, v in rf.items()}


def text_flags(text: str) -> Dict[str, List[str]]:
    t = N.strip_accents((text or "").lower())
    out = {}
    for k, (rx, _) in _flags().items():
        hits = sorted({m.group(0).strip() for m in rx.finditer(t)})
        if hits:
            out[k] = hits[:5]
    return out


def _engine_match(e: dict, car: Car, blob: str) -> Optional[str]:
    """None = no match, 'certain' or 'possible' (engine not confirmed by the ad text)."""
    makes = e.get("make", ["*"])
    if "*" not in makes and car.make not in makes:
        return None
    if e.get("families") and car.family not in e["families"]:
        return None
    y0, y1 = e.get("years", [1900, 2100])
    if car.year and not (y0 <= car.year <= y1):
        return None
    uncertain = False
    if e.get("fuel"):
        if car.fuel is None:
            uncertain = True
        elif car.fuel not in e["fuel"]:
            return None
    if e.get("gearbox"):
        if car.gearbox is None:
            uncertain = True
        elif car.gearbox != e["gearbox"]:
            return None
    if e.get("engine_l"):
        if car.engine_l is None:
            uncertain = True
        elif not any(abs(car.engine_l - x) < 0.051 for x in e["engine_l"]):
            return None
    if e.get("max_kw") and car.power_kw and car.power_kw > e["max_kw"]:
        return None
    for x in e.get("exclude_text", []):
        if x in blob:
            return None
    if e.get("text"):
        if not any(re.search(r"(?<![a-z])" + re.escape(x), blob) for x in e["text"]):
            uncertain = True
    if not car.year:
        uncertain = True
    return "possible" if uncertain else "certain"


def assess(car: Car, today: Optional[dt.date] = None) -> dict:
    """Everything the UI/alerts need to judge mechanical risk for one listing."""
    today = today or dt.date.today()
    km = car.km or 0
    age = (today.year - car.year) if car.year else None
    blob = N.strip_accents(f"{car.title} {car.model_raw} {car.text}".lower())
    fam = family_entry(car.make, car.family)
    issues = []

    def add(src, it, certainty="certain", label=None):
        if it.get("years") and car.year and not (it["years"][0] <= car.year <= it["years"][1]):
            return
        if it.get("families") and car.family not in it["families"]:
            return
        if it.get("gearbox") and car.gearbox and it["gearbox"] != car.gearbox:
            return
        if it.get("fuel") and car.fuel and it["fuel"] != car.fuel:
            return
        if it.get("gearbox") and car.gearbox is None:
            certainty = "possible"
        if it.get("fuel") and car.fuel is None:
            certainty = "possible"
        due = km >= it.get("km", 0) if car.km is not None else it.get("km", 0) == 0
        issues.append({"t": it["t"], "sev": it.get("sev", 1), "cost": it.get("cost", ""), "km": it.get("km", 0),
                       "due": bool(due), "src": src, "certainty": certainty, "label": label})

    engines = []
    for e in kb()["engines"]:
        m = _engine_match(e, car, blob)
        if not m:
            continue
        engines.append({"id": e["id"], "label": e["label"], "verdict": e["verdict"], "certainty": m, "good": e.get("good", [])})
        for it in e["issues"]:
            add(e["id"], it, m, e["label"])
    if fam:
        for it in fam.get("watch", []):
            add("family", it)
    imported = car.country != "LV"
    for g in kb()["generic"]:
        w = g["when"]
        ok = True
        if "imported" in w and w["imported"] != imported:
            ok = False
        if "fuel" in w and car.fuel not in w["fuel"]:
            ok = False
        if "gearbox" in w and car.gearbox not in w["gearbox"]:
            ok = False
        if "min_km" in w and km < w["min_km"]:
            ok = False
        if "min_age" in w and (age is None or age < w["min_age"]):
            ok = False
        if "km_missing" in w and (car.km is not None) == w["km_missing"]:
            ok = False
        if "max_km_per_year" in w:
            if not car.km or not age or age < 1 or car.km / age > w["max_km_per_year"]:
                ok = False
        if ok:
            issues.append({"t": g["t"], "sev": g["sev"], "cost": g.get("cost", ""), "km": w.get("min_km", 0),
                           "due": True, "src": "generic", "certainty": "certain", "label": None})

    flags = text_flags(f"{car.title} {car.text}")
    # risk 0..10: certain & due issues weigh most
    risk = 0.0
    for it in issues:
        w = it["sev"] * (1.0 if it["due"] else 0.35) * (1.0 if it["certainty"] == "certain" else 0.45)
        risk += w
    if fam:
        risk += max(0, 7 - fam.get("score", 7)) * 0.8
    verdicts = [e["verdict"] for e in engines if e["certainty"] == "certain"]
    if "avoid" in verdicts:
        risk += 3
    if "bulletproof" in verdicts:
        risk -= 1.5
    risk += 4 * len(flags.get("major", [])) + 0.8 * len(flags.get("minor", [])) - 0.7 * len(flags.get("good", []))
    risk = max(0.0, min(10.0, risk / 1.6))
    level = "low" if risk < 3 else ("medium" if risk < 6 else "high")
    issues.sort(key=lambda i: (not i["due"], i["certainty"] != "certain", -i["sev"], i["km"]))
    return {
        "risk": round(risk, 1), "level": level,
        "family": {k: fam.get(k) for k in ("score", "verdict", "summary", "good", "key")} if fam else None,
        "engines": engines, "issues": issues[:10], "flags": flags,
    }
