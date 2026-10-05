"""Telegram pings. Needs TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID (GitHub secrets / local env)."""
from __future__ import annotations

import html
import logging
import os
import re

import requests

log = logging.getLogger("flipfinder.alerts")
FLAG = {"LV": "🇱🇻", "LT": "🇱🇹", "EE": "🇪🇪", "PL": "🇵🇱", "CZ": "🇨🇿", "DE": "🇩🇪", "AT": "🇦🇹", "NL": "🇳🇱", "BE": "🇧🇪"}
SRC = {"sslv": "ss.lv", "sauto": "sauto.cz", "bazos": "bazos.cz", "otomoto": "otomoto.pl", "autoplius": "autoplius.lt",
       "auto24": "auto24", "autoscout24": "autoscout24", "facebook": "FB Marketplace"}
FUEL = {"diesel": "diesel", "petrol": "petrol", "hybrid": "hybrid", "phev": "plug-in hybrid", "electric": "EV",
        "lpg": "petrol+LPG", "cng": "CNG"}


def _e(x) -> str:
    return html.escape(str(x), quote=False)


def eur(x) -> str:
    return "€" + f"{int(round(x)):,}".replace(",", " ")


class Telegram:
    def __init__(self, token=None, chat_id=None, dashboard_url=None):
        self.token = token or os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
        self.chat = chat_id or os.environ.get("TELEGRAM_CHAT_ID", "").strip()
        self.dash = dashboard_url or os.environ.get("DASHBOARD_URL", "").strip()
        self.sent = 0

    @property
    def enabled(self) -> bool:
        return bool(self.token and self.chat)

    def send(self, text: str, preview_url: str = None) -> bool:
        if not self.enabled:
            return False
        payload = {"chat_id": self.chat, "text": text, "parse_mode": "HTML", "disable_web_page_preview": preview_url is None}
        if preview_url:
            payload["link_preview_options"] = {"url": preview_url, "prefer_large_media": True, "show_above_text": True}
        try:
            r = requests.post(f"https://api.telegram.org/bot{self.token}/sendMessage", json=payload, timeout=20)
            if r.status_code != 200:
                log.warning("telegram %s: %s", r.status_code, r.text[:200])
                return False
            self.sent += 1
            return True
        except Exception as e:  # never leak the token in logs
            log.warning("telegram send failed: %s", re.sub(r"bot[0-9]+:[\w-]+", "bot***", str(e)))
            return False

    # ------------------------------------------------------------------ formatting

    def car_message(self, car: dict, ev: dict, kind_title: str) -> str:
        bits = [str(car.get("year") or "?")]
        if car.get("km"):
            bits.append(f"{round(car['km'] / 1000)}k km")
        if car.get("fuel"):
            bits.append(FUEL.get(car["fuel"], car["fuel"]))
        if car.get("engine_l"):
            bits.append(f"{car['engine_l']:.1f} L")
        if car.get("gearbox"):
            bits.append("auto" if car["gearbox"] == "auto" else "manual")
        price = eur(car["price_eur"])
        if car.get("currency") and car["currency"] != "EUR":
            price += f" ({int(car['price']):,} {car['currency']})".replace(",", " ")
        lines = [f"<b>{_e(kind_title)}</b> {FLAG.get(car['country'], car['country'])} · {_e(SRC.get(car['source'], car['source']))}",
                 f"<b>{_e(ev['label'])}</b> — {_e(' · '.join(bits))}",
                 f"Price: <b>{price}</b>" + (f"  ·  {_e(car['location'])}" if car.get("location") else "")]
        if ev.get("value"):
            lines.append(f"LV value: ~{eur(ev['value'])} ({ev['n']} comps, {ev['conf']} confidence)")
        if ev.get("profit") is not None and ev["kind"] == "import":
            lines.append(f"💰 Est. profit: <b>{'+' if ev['profit'] >= 0 else ''}{eur(ev['profit'])}</b> "
                         f"(ROI {round(ev['roi'] * 100)}%, costs {eur(sum(ev['costs'].values()))})")
        elif ev.get("discount") is not None:
            lines.append(f"💰 <b>{round(ev['discount'] * 100)}% under market</b> · resale margin ~{eur(ev['profit'])}")
        r = ev["risk"]
        icon = {"low": "🟢", "medium": "🟡", "high": "🔴"}[r["level"]]
        fam = r.get("family") or {}
        lines.append(f"{icon} Risk: {r['level']}" + (f" · {_e(fam.get('verdict'))}" if fam.get("verdict") else ""))
        top = [i for i in r["issues"] if i["due"] and i["sev"] >= 2 and i["src"] != "generic"][:2]
        for i in top:
            pre = f"If {i['label']}: " if i["certainty"] == "possible" and i.get("label") else ""
            lines.append(f"⚠️ {_e(pre + i['t'])}" + (f" ({_e(i['cost'])})" if i.get("cost") and i["cost"] != "—" else ""))
        if r["flags"].get("major"):
            lines.append(f"🚩 Ad says: {_e(', '.join(r['flags']['major']))}")
        link = f"<a href=\"{_e(car['url'])}\">Open listing</a>"
        if self.dash:
            link += f"  ·  <a href=\"{_e(self.dash)}#car={_e(car['id'])}\">Dashboard</a>"
        lines.append(link)
        return "\n".join(lines)

    def item_message(self, wl: str, it: dict) -> str:
        lines = [f"<b>🛍 {_e(wl)}</b> · ss.lv", f"{_e(it['title'][:120])}", f"Price: <b>{eur(it['price'])}</b>"]
        if it.get("median"):
            lines.append(f"Typical: ~{eur(it['median'])} ({round(it['discount'] * 100)}% under, {it['group_n']} similar ads)")
        lines.append(f"<a href=\"{_e(it['url'])}\">Open listing</a>")
        return "\n".join(lines)
