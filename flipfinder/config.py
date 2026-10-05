from __future__ import annotations

import copy
import os

import yaml

DEFAULTS = {
    "budget": {"min_buy_eur": 800, "max_buy_eur": 15000},
    "markets": {"sauto_cz": True, "bazos_cz": True, "otomoto_pl": True, "autoplius_lt": True,
                "auto24": True, "autoscout24_de": True, "facebook": True},
    "pages": {"sauto_cz": 5, "bazos_cz": 12, "otomoto_pl": 25, "autoplius_lt": 10, "auto24": 3, "autoscout24_de": 20},
    "mac_sources": [],
    "sslv": {"full_crawl_every_hours": 24},
    "costs": {"transport_eur": {"LT": 200, "EE": 250, "PL": 450, "CZ": 650, "DE": 700, "LV": 0, "other": 800},
              "registration_eur": 210, "history_check_eur": 25, "recon_buffer_eur": 300,
              "local_costs_eur": 30, "sale_discount_pct": 7},
    "alerts": {"min_profit_eur": 600, "min_roi_pct": 15, "local_min_discount_pct": 20, "local_min_profit_eur": 500,
               "max_per_run": 12, "skip_high_risk": True},
    "facebook": {"cities": ["riga", "vilnius", "kaunas", "tallinn", "warsaw", "prague", "berlin"],
                 "max_price_eur": 10000, "scrolls_per_city": 4},
    "my_car": {"enabled": True, "max_price_eur": 3800, "min_year": 2008, "max_km": 280000,
               "makes": ["toyota", "volkswagen", "skoda", "honda", "opel", "mazda"],
               "fuels": ["diesel", "petrol", "hybrid"], "max_petrol_engine_l": 1.4, "countries": ["LV"],
               "must_have_ac": True, "min_discount_pct": 5},
    "watchlists": [],
}


def _merge(base, over):
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def load(path: str = "config.yaml") -> dict:
    data = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    return _merge(DEFAULTS, data)
