"""Turn a listing + LV market model + reliability into a deal verdict."""
from __future__ import annotations

from typing import Optional

from . import normalize as N
from .models import Car
from .pricing import Market
from .reliability import assess

CONF_MULT = {"high": 1.0, "medium": 0.8, "low": 0.5}


def evaluate(car: Car, market: Market, cfg: dict, with_comps: bool = False) -> Optional[dict]:
    if not (car.make and car.family and car.year and car.price_eur):
        return None
    pred = market.predict(car)
    rel = assess(car)
    c = cfg["costs"]
    if car.country == "LV":
        kind = "local"
        costs = {"recon": c["recon_buffer_eur"], "paperwork": c["local_costs_eur"]}
    else:
        kind = "import"
        tr = c["transport_eur"]
        costs = {"transport": tr.get(car.country, tr.get("other", 800)), "registration": c["registration_eur"],
                 "history_check": c["history_check_eur"], "recon": c["recon_buffer_eur"]}
    landed = car.price_eur + sum(costs.values())
    out = {"kind": kind, "costs": costs, "landed": round(landed), "risk": rel, "label": N.label(car.make, car.family)}
    if not pred:
        out.update({"value": None, "profit": None, "roi": None, "discount": None, "score": 0, "hot": False})
        return out
    sale = pred["value"] * (1 - c["sale_discount_pct"] / 100.0)
    profit = sale - landed
    roi = profit / landed if landed else 0
    discount = 1 - car.price_eur / pred["value"]
    mult = CONF_MULT[pred["conf"]] * max(0.15, 1 - rel["risk"] / 13)
    if rel["flags"].get("major"):
        mult *= 0.3
    if car.hint and "toolow" in car.hint:
        mult *= 0.75  # the site itself thinks it's suspiciously cheap
    score = profit * mult
    a = cfg["alerts"]
    risky = rel["level"] == "high" or bool(rel["flags"].get("major"))
    if kind == "import":
        hot = profit >= a["min_profit_eur"] and roi * 100 >= a["min_roi_pct"]
    else:
        hot = discount * 100 >= a["local_min_discount_pct"] and profit >= a["local_min_profit_eur"]
    hot = hot and pred["conf"] != "low" and not (a.get("skip_high_risk", True) and risky)
    out.update({"value": pred["value"], "value_low": pred["low"], "value_high": pred["high"], "conf": pred["conf"],
                "n": pred["n"], "sale": round(sale), "profit": round(profit), "roi": round(roi, 3),
                "discount": round(discount, 3), "score": round(score), "hot": bool(hot)})
    if with_comps:
        m = market.model_for(car)
        out["comps"] = m.comps(car) if m else []
    return out


def personal_match(car: Car, ev: Optional[dict], cfg: dict) -> Optional[dict]:
    p = cfg.get("my_car") or {}
    if not p.get("enabled") or not ev:
        return None
    if car.country not in p.get("countries", ["LV"]):
        return None
    if car.make not in p.get("makes", []):
        return None
    if car.price_eur > p["max_price_eur"] or (car.year or 0) < p["min_year"]:
        return None
    if car.km and car.km > p["max_km"]:
        return None
    if car.fuel and car.fuel not in p.get("fuels", []) and not (car.fuel in ("lpg", "cng") and "petrol" in p.get("fuels", [])):
        return None
    if car.fuel in ("petrol", "lpg", "cng") and car.engine_l and car.engine_l > p.get("max_petrol_engine_l", 9):
        return None
    if ev["risk"]["level"] == "high" or ev["risk"]["flags"].get("major"):
        return None
    reasons = []
    if ev.get("discount") is not None:
        reasons.append(f"{round(ev['discount'] * 100)}% vs LV market")
    fam = ev["risk"].get("family") or {}
    if fam.get("verdict") in ("bulletproof", "solid"):
        reasons.append(f"{fam['verdict']} model")
    ac = car.has_ac
    if ac is None:
        t = N.strip_accents((car.text or "").lower())
        if any(w in t for w in ("kondicion", "klimat", "кондиц", "климат", "a/c", " ac ", "climate")):
            ac = True
    if p.get("must_have_ac") and ac is False:
        return None
    value_score = (ev.get("discount") or 0) * 100 + (10 - ev["risk"]["risk"]) * 2
    return {"ac": ac, "reasons": reasons, "score": round(value_score, 1),
            "ping": (ev.get("discount") or -1) * 100 >= p.get("min_discount_pct", 5) and ev.get("conf") != "low"}
