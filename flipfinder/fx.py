"""Currency conversion via the ECB daily reference rates (free, no key)."""
from __future__ import annotations

import logging
import re

log = logging.getLogger("flipfinder.fx")

# rough fallbacks, only used if the ECB feed is unreachable
FALLBACK = {"EUR": 1.0, "CZK": 24.4, "PLN": 4.27, "USD": 1.10, "GBP": 0.85, "SEK": 11.2,
            "NOK": 11.6, "DKK": 7.46, "HUF": 395.0, "CHF": 0.94}


class FX:
    def __init__(self, rates=None, source="fallback"):
        self.rates = dict(FALLBACK)
        if rates:
            self.rates.update(rates)
        self.source = source

    @classmethod
    def load(cls, fetcher) -> "FX":
        try:
            r = fetcher.get("https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml", check_block=False)
            rates = {m.group(1): float(m.group(2))
                     for m in re.finditer(r"currency='([A-Z]{3})'\s+rate='([\d.]+)'", r.text)}
            if rates.get("CZK") and rates.get("PLN"):
                return cls(rates, "ECB")
        except Exception as e:
            log.warning("ECB rates unavailable (%s) - using fallback rates", e)
        return cls()

    def to_eur(self, amount, currency: str) -> float:
        if amount is None:
            return 0.0
        c = (currency or "EUR").upper().replace("KČ", "CZK").replace("ZŁ", "PLN")
        c = {"KC": "CZK", "ZL": "PLN", "€": "EUR"}.get(c, c)
        rate = self.rates.get(c)
        if not rate:
            return float(amount)
        return float(amount) / rate
