from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field, asdict
from typing import Optional

from . import normalize as N


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


@dataclass
class Car:
    source: str            # sslv | sauto | bazos | otomoto | autoplius | auto24 | autoscout24 | facebook
    native_id: str
    country: str           # LV CZ PL LT EE DE ...
    url: str
    title: str
    price: float
    currency: str = "EUR"
    price_eur: float = 0.0
    make: Optional[str] = None
    family: Optional[str] = None
    model_raw: str = ""
    year: Optional[int] = None
    km: Optional[int] = None
    fuel: Optional[str] = None
    gearbox: Optional[str] = None
    engine_l: Optional[float] = None
    power_kw: Optional[int] = None
    location: str = ""
    seller: Optional[str] = None      # private | dealer
    image: Optional[str] = None
    text: str = ""                    # short description, used for red/green flags
    posted: Optional[str] = None
    first_seen: str = field(default_factory=now_iso)
    last_seen: str = field(default_factory=now_iso)
    inspection: Optional[str] = None  # LV tehniskā apskate valid until
    has_ac: Optional[bool] = None
    hint: Optional[str] = None        # site's own price verdict, e.g. autoscout24 "good-price"

    @property
    def id(self) -> str:
        return f"{self.source}:{self.native_id}"

    def finish(self, fx) -> "Car":
        """Fill canonical fields that the source parser didn't set."""
        if not self.make:
            self.make, rest = N.find_make_in_text(self.title)
            if not self.model_raw:
                self.model_raw = rest
        if self.make and not self.family:
            self.family = N.canon_family(self.make, self.model_raw or self.title)
        if not self.year:
            self.year = N.year_from_text(self.title) or N.year_from_text(self.text[:300])
        if not self.km:
            self.km = N.km_from_text(self.title) or N.km_from_text(self.text)
        blob = f"{self.title} {self.model_raw} {self.text[:400]}"
        if not self.fuel:
            self.fuel = N.canon_fuel(blob)
        if not self.engine_l:
            self.engine_l = N.engine_from_text(f"{self.title} {self.model_raw}")
        if not self.power_kw:
            self.power_kw = N.power_kw_from_text(blob)
        if not self.price_eur:
            self.price_eur = round(fx.to_eur(self.price, self.currency), 0)
        self.text = (self.text or "")[:700]
        self.title = (self.title or "").strip()[:140]
        return self

    def to_dict(self) -> dict:
        d = asdict(self)
        d["id"] = self.id
        return d

    @staticmethod
    def from_dict(d: dict) -> "Car":
        d = dict(d)
        d.pop("id", None)
        known = Car.__dataclass_fields__.keys()
        return Car(**{k: v for k, v in d.items() if k in known})
