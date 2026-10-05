"""One full FlipFinder run: update LV baseline, scan platforms, score deals, alert, write the dashboard."""
from __future__ import annotations

import datetime as dt
import json
import logging
import os
import shutil
import statistics as st
import time
from collections import defaultdict
from typing import Dict, List

from . import normalize as N
from .alerts import Telegram
from .deals import evaluate, personal_match
from .fx import FX
from .http import Blocked, Fetcher
from .models import Car, now_iso
from .pricing import Market
from .reliability import kb
from .sources import foreign, sslv
from .store import Store

log = logging.getLogger("flipfinder")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

LV_KEEP = ("source", "native_id", "country", "url", "title", "price", "currency", "price_eur", "make", "family",
           "model_raw", "year", "km", "fuel", "gearbox", "engine_l", "power_kw", "location", "image", "text",
           "first_seen", "last_seen", "inspection", "has_ac", "hint", "seller", "posted")


def _parse_ts(s):
    try:
        return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


def _hours_since(s) -> float:
    t = _parse_ts(s) if s else None
    if not t:
        return 1e9
    return (dt.datetime.now(dt.timezone.utc) - t).total_seconds() / 3600


def _slim(c: Car, text_len=220) -> dict:
    d = c.to_dict()
    d["text"] = (d.get("text") or "")[:text_len]
    return {k: d[k] for k in LV_KEEP if d.get(k) not in (None, "")} | {"id": c.id}


def _merge(store: Dict[str, dict], cars: List[Car], now: str) -> List[Car]:
    """Upsert; returns cars that are new or got cheaper."""
    changed = []
    for c in cars:
        old = store.get(c.id)
        d = _slim(c)
        if old:
            d["first_seen"] = old.get("first_seen", now)
            if old.get("price_eur") and c.price_eur < old["price_eur"] * 0.97:
                d["prev_price_eur"] = old["price_eur"]
                changed.append(c)
            elif old.get("prev_price_eur"):
                d["prev_price_eur"] = old["prev_price_eur"]
            for k in ("has_ac", "inspection", "location", "gearbox", "detail_checked"):
                if old.get(k) is not None and d.get(k) in (None, ""):
                    d[k] = old[k]
            if old.get("detail_checked") and old.get("text") and len(old["text"]) > len(d.get("text", "")):
                d["text"] = old["text"]
        else:
            d["first_seen"] = now
            changed.append(c)
        d["last_seen"] = now
        store[c.id] = d
        c.first_seen = d["first_seen"]
    return changed


def run(config: dict, state_dir: str, site_dir: str, only: List[str] = None, no_alerts: bool = False,
        force_full: bool = False) -> dict:
    t0 = time.time()
    store = Store(state_dir)
    meta = store.load("meta.json", {})
    health = meta.get("health", {})
    fetcher = Fetcher()
    fx = FX.load(fetcher)
    now = now_iso()
    cfg = config
    budget = cfg["budget"]
    tg = Telegram()

    def mark(src, ok, n=0, err=None, secs=0.0):
        h = health.get(src, {})
        h.update({"ok": ok, "n": n, "err": (str(err)[:200] if err else None), "secs": round(secs, 1), "at": now})
        if ok:
            h["last_ok"] = now
        health[src] = h

    # ------------------------------------------------------------- 1. LV baseline (ss.lv)
    lv = store.load("lv_cars.json.gz", {})
    fresh_local: List[Car] = []
    want = lambda k: (not only) or (k in only)  # noqa: E731
    if want("sslv"):
        full_due = force_full or _hours_since(meta.get("last_full_crawl")) >= cfg["sslv"]["full_crawl_every_hours"] or len(lv) < 3000
        s0 = time.time()
        try:
            if full_due:
                cars = [c.finish(fx) for c in sslv.crawl_full(fetcher)]
                ids = {c.id for c in cars}
                gone = [k for k in lv if k not in ids]
                fresh_local = _merge(lv, cars, now)
                for k in gone:  # sold / removed -> drop, but remember how long it was listed
                    old = lv.pop(k)
                    dom = (_parse_ts(old.get("last_seen", now)) - _parse_ts(old.get("first_seen", now))).days \
                        if old.get("first_seen") and old.get("last_seen") else None
                    if dom is not None and old.get("make") and old.get("family"):
                        meta.setdefault("dom", {}).setdefault(f"{old['make']}|{old['family']}", []).append(dom)
                for k, v in meta.get("dom", {}).items():
                    meta["dom"][k] = v[-200:]
                meta["last_full_crawl"] = now
                if not meta.get("seed_done_at"):
                    # very first crawl: these ads aren't "new", they were already there
                    meta["seed_done_at"] = now
                    for d in lv.values():
                        d["seed"] = True
            else:
                cars = [c.finish(fx) for c in sslv.crawl_today(fetcher)]
                fresh_local = _merge(lv, cars, now)
            mark("sslv", True, len(cars), secs=time.time() - s0)
        except Exception as e:
            log.exception("ss.lv failed")
            mark("sslv", False, 0, e, time.time() - s0)
    lv_cars = [Car.from_dict(d) for d in lv.values()]
    market = Market(lv_cars)
    log.info("LV market: %d listings, %d model families with a price model", len(lv_cars), len(market.models))

    # ------------------------------------------------------------- 2. other platforms (newest listings)
    fstore = store.load("foreign.json.gz", {})
    fresh_foreign: List[Car] = []
    for key, (fn, country, label, _home) in foreign.SCANNERS.items():
        if not cfg["markets"].get(key) or not want(key):
            continue
        s0 = time.time()
        try:
            got = fn(fetcher, fx, budget["max_buy_eur"], pages=cfg["pages"].get(key, 4))
            got = [c.finish(fx) for c in got]
            got = [c for c in got if budget["min_buy_eur"] <= c.price_eur <= budget["max_buy_eur"]]
            if key == "auto24":
                for c in got:  # auto24 is shared LV/EE inventory; treat LV-registered stock as local
                    c.country = "EE"
            fresh_foreign += _merge(fstore, got, now)
            mark(key, True, len(got), secs=time.time() - s0)
            log.info("%-14s %4d cars (%.0fs)", label, len(got), time.time() - s0)
        except Blocked as e:
            mark(key, False, 0, f"blocked: {e}", time.time() - s0)
            log.warning("%s blocked: %s", label, e)
        except Exception as e:
            mark(key, False, 0, e, time.time() - s0)
            log.warning("%s failed: %s", label, e)

    # Facebook listings pushed from the user's Mac (fb_runner.py)
    fb_in = store.load("fb_incoming.json", {})
    if fb_in.get("cars") and fb_in.get("at") != meta.get("fb_at"):
        fb_cars = [Car.from_dict(d).finish(fx) for d in fb_in["cars"]]
        fb_cars = [c for c in fb_cars if budget["min_buy_eur"] <= c.price_eur <= budget["max_buy_eur"]]
        fresh_foreign += _merge(fstore, fb_cars, fb_in.get("at") or now)
        n_fb = sum(1 for c in fb_cars if c.source == "facebook")
        mark("facebook", n_fb > 0, n_fb, err=("; ".join(fb_in.get("errors") or []) or None), secs=0)
        for src in {c.source for c in fb_cars if c.source != "facebook"}:
            mark("mac:" + src, True, sum(1 for c in fb_cars if c.source == src), secs=0)
        health["facebook"]["at"] = fb_in.get("at", now)
        meta["fb_at"] = fb_in.get("at")
    elif cfg["markets"].get("facebook"):
        health.setdefault("facebook", {"ok": None, "n": 0, "err": "waiting for your Mac (run 'Setup Facebook Scanner')", "at": None})
    try:
        os.remove(os.path.join(state_dir, "fb_incoming.json"))  # lives on the fb-data branch, not in state
    except OSError:
        pass

    # forget foreign listings not seen for 6 days
    for k in [k for k, v in fstore.items() if _hours_since(v.get("last_seen")) > 144]:
        fstore.pop(k)

    # ------------------------------------------------------------- 3. evaluate
    def is_new(c: Car, d: dict) -> bool:
        return (not d.get("seed") and _hours_since(c.first_seen) <= 72) or bool(d.get("prev_price_eur"))

    active = [Car.from_dict(v) for v in fstore.values() if _hours_since(v.get("last_seen")) <= 96]
    deals = []
    for c in active:
        ev = evaluate(c, market, cfg)
        if ev and ev.get("value") is not None:
            deals.append((c, ev))
    lv_evals = []
    for c in lv_cars:
        if not (budget["min_buy_eur"] <= c.price_eur <= budget["max_buy_eur"]):
            continue
        ev = evaluate(c, market, cfg)
        if ev and ev.get("value") is not None:
            ev["new"] = is_new(c, lv.get(c.id, {}))
            lv_evals.append((c, ev))
    # local: best-value LV ads (any age) for the dashboard; only new/cheaper ones can alert
    local_best = sorted(lv_evals, key=lambda x: -x[1]["score"])[:180]
    for c, ev in local_best:
        if not ev["new"]:
            ev["hot"] = False
    deals += local_best
    deals.sort(key=lambda x: -x[1]["score"])

    # personal car hunt runs over ALL of the LV market, not just new ads
    personal = []
    if cfg["my_car"].get("enabled"):
        countries = cfg["my_car"].get("countries", ["LV"])
        pool = lv_evals + [(c, ev) for c, ev in deals if c.source != "sslv" and c.country in countries]
        for c, ev in pool:
            pm = personal_match(c, ev, cfg)
            if pm:
                if c.source == "sslv" and not ev.get("new"):
                    pm["ping"] = False
                personal.append((c, ev, pm))
        personal.sort(key=lambda x: -x[2]["score"])
        # pull detail pages (A/C, gearbox, location) for the top ss.lv matches we haven't checked
        checked = 0
        for c, ev, pm in personal[:40]:
            d = lv.get(c.id)
            if c.source != "sslv" or not d or d.get("detail_checked") or checked >= 15:
                continue
            sslv.enrich(fetcher, c)
            checked += 1
            d.update({"detail_checked": True, "has_ac": c.has_ac, "gearbox": c.gearbox, "location": c.location,
                      "inspection": c.inspection, "text": (c.text or "")[:600], "km": c.km})
        # re-score after enrichment (A/C may now be known False)
        rescored = []
        for c, ev, pm in personal:
            d = lv.get(c.id)
            if d and d.get("detail_checked"):
                c = Car.from_dict(d)
                was_new, ping = ev.get("new"), pm["ping"]
                ev = evaluate(c, market, cfg)
                ev["new"] = was_new
                pm = personal_match(c, ev, cfg)
                if pm:
                    pm["ping"] = pm["ping"] and ping
            if pm:
                rescored.append((c, ev, pm))
        personal = sorted(rescored, key=lambda x: -x[2]["score"])[:80]

    # ------------------------------------------------------------- 4. item watchlists
    istore = store.load("items.json.gz", {})
    item_hits = []
    for wl in cfg.get("watchlists") or []:
        key = "wl:" + wl["name"]
        if not want("watchlists"):
            break
        s0 = time.time()
        try:
            items = sslv.crawl_items(fetcher, wl["url"], pages=3)
            inc = [N.strip_accents(x.lower()) for x in wl.get("include", [])]
            exc = [N.strip_accents(x.lower()) for x in wl.get("exclude", [])]
            kept = []
            for it in items:
                blob = N.strip_accents((it["title"] + " " + " ".join(it["cols"].values())).lower())
                if inc and not any(w in blob for w in inc):
                    continue
                if any(w in blob for w in exc):
                    continue
                gkey = wl["name"] + "|" + "|".join(N.norm(v) for k, v in sorted(it["cols"].items()) if k not in ("stav", "stav."))
                old = istore.get(it["id"], {})
                istore[it["id"]] = {"wl": wl["name"], "g": gkey, "price": it["price"], "title": it["title"][:160],
                                    "url": it["url"], "image": it.get("image"), "cols": it["cols"],
                                    "first_seen": old.get("first_seen", now), "last_seen": now}
                kept.append(it["id"])
            mark(key, True, len(kept), secs=time.time() - s0)
        except Exception as e:
            mark(key, False, 0, e, time.time() - s0)
    for k in [k for k, v in istore.items() if _hours_since(v.get("last_seen")) > 24 * 30]:
        istore.pop(k)
    groups = defaultdict(list)
    for v in istore.values():
        groups[v["g"]].append(v["price"])
    wl_by_name = {w["name"]: w for w in cfg.get("watchlists") or []}
    for iid, v in istore.items():
        if _hours_since(v["last_seen"]) > 30 or v["wl"] not in wl_by_name:
            continue
        w = wl_by_name[v["wl"]]
        prices = groups[v["g"]]
        med = st.median(prices) if len(prices) >= 5 else None
        disc = (1 - v["price"] / med) if med else None
        hit = v["price"] <= w.get("alert_below_eur", 0) or (disc is not None and disc * 100 >= w.get("alert_discount_pct", 101))
        item_hits.append({"id": iid, **{k: v[k] for k in ("wl", "price", "title", "url", "image", "cols", "first_seen")},
                          "median": round(med) if med else None, "discount": round(disc, 3) if disc is not None else None,
                          "group_n": len(prices), "hit": bool(hit)})
    item_hits.sort(key=lambda x: (not x["hit"], -(x["discount"] or -1)))

    # ------------------------------------------------------------- 5. alerts
    alerted = store.load("alerted.json", {})
    first_run = not meta.get("runs")
    if tg.enabled and not no_alerts and not first_run:
        budget_left = cfg["alerts"]["max_per_run"]
        queue = []
        for c, ev in deals:
            if ev["hot"] and (ev["kind"] == "import" or ev.get("new")):
                queue.append(("flip" if ev["kind"] == "import" else "local", c, ev))
        for c, ev, pm in personal:
            if pm["ping"]:
                queue.append(("mine", c, ev))
        for kind, c, ev in queue:
            if budget_left <= 0:
                break
            prev = alerted.get(c.id)
            if prev and c.price_eur > prev.get("price", 0) * 0.95:
                continue
            title = {"flip": "🔥 Import flip", "local": "💎 Underpriced in LV", "mine": "🚗 Match for your car hunt"}[kind]
            if prev:
                title = "📉 Price drop · " + title
            if tg.send(tg.car_message(c.to_dict() | {"id": c.id}, ev, title), preview_url=c.url):
                alerted[c.id] = {"price": c.price_eur, "at": now}
                budget_left -= 1
        for it in item_hits:
            if budget_left <= 0:
                break
            if not it["hit"] or _hours_since(it["first_seen"]) > 30:
                continue
            prev = alerted.get(it["id"])
            if prev and it["price"] > prev.get("price", 0) * 0.95:
                continue
            if tg.send(tg.item_message(it["wl"], it), preview_url=it["url"]):
                alerted[it["id"]] = {"price": it["price"], "at": now}
                budget_left -= 1
    elif first_run and tg.enabled and not no_alerts:
        tg.send("✅ <b>FlipFinder is live.</b> First scan done — I'll ping you here when I spot a deal."
                + (f"\n<a href=\"{tg.dash}\">Open dashboard</a>" if tg.dash else ""))
    for k in [k for k, v in alerted.items() if _hours_since(v.get("at")) > 24 * 45]:
        alerted.pop(k)

    # ------------------------------------------------------------- 6. dashboard data
    def pack(c: Car, ev: dict, extra=None, comps=False) -> dict:
        d = c.to_dict()
        d.pop("native_id", None)
        d["text"] = (d.get("text") or "")[:400]
        old = lv.get(c.id) or fstore.get(c.id) or {}
        if old.get("prev_price_eur"):
            d["prev_price_eur"] = old["prev_price_eur"]
        e = {k: ev.get(k) for k in ("kind", "costs", "landed", "value", "value_low", "value_high", "conf", "n", "sale",
                                    "profit", "roi", "discount", "score", "hot", "label", "new")}
        e["risk"] = ev["risk"]
        if comps:
            m = market.model_for(c)
            e["comps"] = m.comps(c) if m else []
        d["ev"] = e
        if extra:
            d.update(extra)
        return {k: v for k, v in d.items() if v not in (None, "")}

    out_deals = [pack(c, ev, comps=True) for c, ev in deals[:350]]
    out_personal = [pack(c, ev, {"mine": pm}, comps=True) for c, ev, pm in personal]
    hist = meta.setdefault("market_hist", {})
    today = dt.date.today().isoformat()
    summary = market.summary()
    for row in summary:
        h = hist.setdefault(row["key"], [])
        if not h or h[-1][0] != today:
            h.append([today, row["median"], row["n"]])
        hist[row["key"]] = h[-120:]
        row["trend"] = hist[row["key"]][-60:]
        dom = meta.get("dom", {}).get(row["key"])
        if dom and len(dom) >= 5:
            row["days_on_market"] = round(st.median(dom))
    meta["runs"] = meta.get("runs", 0) + 1
    meta["health"] = health
    meta["last_run"] = now
    data = {
        "generated": now, "run": meta["runs"], "fx": {"source": fx.source, "CZK": round(fx.rates.get("CZK", 0), 3), "PLN": round(fx.rates.get("PLN", 0), 3)},
        "health": health, "repo": os.environ.get("GITHUB_REPOSITORY"),
        "config": {k: cfg[k] for k in ("budget", "costs", "alerts", "my_car", "markets")},
        "stats": {"lv_listings": len(lv_cars), "lv_models": len(market.models), "foreign_tracked": len(fstore),
                  "deals": len(deals), "hot": sum(1 for _, e in deals if e["hot"]), "telegram": tg.enabled,
                  "alerts_sent": tg.sent, "secs": round(time.time() - t0)},
        "deals": out_deals, "personal": out_personal, "items": item_hits[:200],
        "watchlists": [{"name": w["name"], "url": w["url"]} for w in cfg.get("watchlists") or []],
        "market": summary,
    }
    os.makedirs(site_dir, exist_ok=True)
    with open(os.path.join(site_dir, "data.json"), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    with open(os.path.join(site_dir, "lv_market.json"), "w", encoding="utf-8") as f:
        json.dump(market.export_points(), f, ensure_ascii=False, separators=(",", ":"))
    kbx = json.loads(json.dumps(kb()))
    for key, e in kbx["families"].items():
        mk, fam = key.split("|", 1)
        e["label"] = N.label(mk, fam)
    with open(os.path.join(site_dir, "reliability.json"), "w", encoding="utf-8") as f:
        json.dump(kbx, f, ensure_ascii=False, separators=(",", ":"))
    web = os.path.join(ROOT, "web")
    for name in os.listdir(web):
        shutil.copy(os.path.join(web, name), os.path.join(site_dir, name))

    # ------------------------------------------------------------- 7. persist
    store.save("lv_cars.json.gz", lv)
    store.save("foreign.json.gz", fstore)
    store.save("items.json.gz", istore)
    store.save("alerted.json", alerted)
    store.save("meta.json", meta)
    log.info("done in %.0fs: %d deals (%d hot), %d personal, %d item ads, %d requests, %d alerts",
             time.time() - t0, len(deals), data["stats"]["hot"], len(personal), len(item_hits), fetcher.requests, tg.sent)
    return data
