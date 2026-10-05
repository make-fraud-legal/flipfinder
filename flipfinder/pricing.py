"""Latvian market value model, learned from every ss.lv listing.

Per model family we fit   log(price) ~ age + age² + km + fuel   (robust, outliers trimmed)
so a 2014 / 190k km / diesel Golf gets a fair LV asking-price estimate even if no identical
car is listed right now. Small families fall back to a simpler model; tiny ones get none."""
from __future__ import annotations

import datetime as dt
import math
import statistics as st
from collections import defaultdict
from typing import Dict, List, Optional

import numpy as np

from . import normalize as N
from .models import Car
from .reliability import text_flags

FUELS = ("diesel", "hybrid", "electric")  # petrol/lpg/cng = baseline


def _fuel_vec(fuel: Optional[str], shares: Dict[str, float]):
    if fuel is None:
        return [shares.get(f, 0.0) for f in FUELS]
    f = "hybrid" if fuel == "phev" else fuel
    return [1.0 if f == x else 0.0 for x in FUELS]


class FamilyModel:
    def __init__(self, key: str, cars: List[Car], ref_year: int):
        self.key = key
        self.ref_year = ref_year
        self.ok = False
        rows = [c for c in cars if c.year and 300 <= c.price_eur <= 250000 and 1985 <= c.year <= ref_year + 1]
        self.n_all = len(rows)
        if len(rows) < 6:
            return
        # impute missing km from the family's km-per-year
        kpy = [c.km / max(1, ref_year - c.year + 0.5) for c in rows if c.km]
        self.km_per_year = st.median(kpy) if kpy else 16000.0
        n_f = len(rows)
        self.shares = {f: sum(1 for c in rows if (c.fuel == f or (f == "hybrid" and c.fuel == "phev"))) / n_f for f in FUELS}
        self.simple = len(rows) < 15
        X, y = [], []
        for c in rows:
            X.append(self._x(c))
            y.append(math.log(c.price_eur))
        X, y = np.array(X), np.array(y)
        keep = np.ones(len(y), dtype=bool)
        beta = None
        for _ in range(3):
            Xk, yk = X[keep], y[keep]
            lam = np.eye(X.shape[1]) * 0.05
            lam[0, 0] = 0
            try:
                beta = np.linalg.solve(Xk.T @ Xk + lam, Xk.T @ yk)
            except np.linalg.LinAlgError:
                return
            res = y - X @ beta
            mad = np.median(np.abs(res[keep] - np.median(res[keep]))) * 1.4826 or 0.15
            keep = np.abs(res) < max(2.5 * mad, 0.25)
        self.beta = beta
        res = (y - X @ beta)[keep]
        self.sigma = float(np.median(np.abs(res)) * 1.4826) if len(res) else 0.5
        self.n = int(keep.sum())
        years = [c.year for c in rows]
        self.year_min, self.year_max = min(years), max(years)
        kms = [c.km for c in rows if c.km]
        self.km_max = max(kms) if kms else 300000
        self.rows = rows
        self.ok = True

    def _x(self, c: Car):
        age = max(0.0, self.ref_year - c.year + 0.5)
        km = c.km if c.km else self.km_per_year * age
        if self.simple:
            return [1.0, age, km / 100000.0]
        return [1.0, age, age * age / 10.0, km / 100000.0, *(_fuel_vec(c.fuel, self.shares))]

    def predict(self, c: Car) -> Optional[dict]:
        if not self.ok or not c.year:
            return None
        v = float(np.exp(np.array(self._x(c)) @ self.beta))
        conf = "low"
        if self.n >= 40 and self.sigma <= 0.25:
            conf = "high"
        elif self.n >= 15 and self.sigma <= 0.38:
            conf = "medium"
        extrapolating = c.year < self.year_min - 1 or c.year > self.year_max + 1 or (c.km or 0) > self.km_max + 60000
        if extrapolating:
            conf = "low"
        if c.km is None and conf == "high":
            conf = "medium"
        band = math.exp(self.sigma)
        return {"value": round(v, -1), "low": round(v / band, -1), "high": round(v * band, -1),
                "conf": conf, "n": self.n, "sigma": round(self.sigma, 3), "extrapolating": extrapolating}

    def comps(self, c: Car, k: int = 6) -> List[dict]:
        def dist(o: Car):
            d = abs((o.year or 0) - (c.year or 0)) * 1.0
            if c.km and o.km:
                d += abs(o.km - c.km) / 40000
            if c.fuel and o.fuel and c.fuel != o.fuel:
                d += 1.5
            return d
        best = sorted(self.rows, key=dist)[:k]
        return [{"url": o.url, "price": o.price_eur, "year": o.year, "km": o.km, "fuel": o.fuel} for o in best]


class Market:
    def __init__(self, lv_cars: List[Car], today: Optional[dt.date] = None):
        self.today = today or dt.date.today()
        groups = defaultdict(list)
        for c in lv_cars:
            if not (c.make and c.family and c.year and c.price_eur):
                continue
            if text_flags(c.text).get("major"):
                continue  # damaged / for-parts ads would drag the baseline down
            groups[f"{c.make}|{c.family}"].append(c)
        self.groups = groups
        self.models: Dict[str, FamilyModel] = {}
        for key, cars in groups.items():
            m = FamilyModel(key, cars, self.today.year)
            if m.ok:
                self.models[key] = m

    def model_for(self, c: Car) -> Optional[FamilyModel]:
        return self.models.get(f"{c.make}|{c.family}")

    def predict(self, c: Car) -> Optional[dict]:
        m = self.model_for(c)
        return m.predict(c) if m else None

    def summary(self, history: Optional[dict] = None) -> List[dict]:
        out = []
        for key, m in self.models.items():
            rows = m.rows
            prices = sorted(c.price_eur for c in rows)
            by_year = defaultdict(list)
            for c in rows:
                by_year[c.year].append(c.price_eur)
            curve = [[y, round(st.median(v))] for y, v in sorted(by_year.items()) if len(v) >= 3]
            kms = [c.km for c in rows if c.km]
            make, fam = key.split("|", 1)
            row = {"key": key, "label": N.label(make, fam), "make": make, "family": fam, "n": len(rows),
                   "median": round(st.median(prices)), "p25": round(prices[len(prices) // 4]),
                   "p75": round(prices[(len(prices) * 3) // 4]),
                   "median_year": round(st.median([c.year for c in rows])),
                   "median_km": round(st.median(kms)) if kms else None,
                   "diesel_share": round(m.shares.get("diesel", 0), 2), "curve": curve,
                   "sigma": round(m.sigma, 3), "fit_n": m.n}
            if history and key in history:
                row["trend"] = history[key][-30:]
            out.append(row)
        out.sort(key=lambda r: -r["n"])
        return out

    def export_points(self) -> Dict[str, list]:
        """Compact LV listing points for the dashboard's scatter charts."""
        fuel_code = {"diesel": "d", "petrol": "p", "hybrid": "h", "phev": "h", "electric": "e", "lpg": "g", "cng": "g"}
        pts = {}
        for key, m in self.models.items():
            arr = []
            for c in m.rows:
                path = c.url.replace("https://www.ss.lv/msg/lv/transport/cars/", "").replace(".html", "")
                arr.append([c.year, round((c.km or 0) / 1000), int(c.price_eur), fuel_code.get(c.fuel or "", "?"), path])
            pts[key] = arr
        return pts
