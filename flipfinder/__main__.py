"""FlipFinder command line.

  python -m flipfinder scan                 # full run (what GitHub Actions runs every 2h)
  python -m flipfinder scan --only sauto_cz # quick test of one source
  python -m flipfinder fb-login             # Mac only: log in to Facebook once
  python -m flipfinder fb-scan              # Mac only: scan Marketplace + push to GitHub
"""
from __future__ import annotations

import argparse
import logging
import os
import sys

from .config import load as load_config


def main(argv=None):
    ap = argparse.ArgumentParser(prog="flipfinder")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("scan")
    s.add_argument("--config", default="config.yaml")
    s.add_argument("--state", default="state")
    s.add_argument("--site", default="site")
    s.add_argument("--only", default="", help="comma list: sslv,sauto_cz,bazos_cz,otomoto_pl,autoplius_lt,auto24,autoscout24_de,watchlists,fb")
    s.add_argument("--no-alerts", action="store_true")
    s.add_argument("--full", action="store_true", help="force the full ss.lv crawl")
    sub.add_parser("selftest", help="fetch 1 page from every source and report what parsed")
    sub.add_parser("fb-login")
    f = sub.add_parser("fb-scan")
    f.add_argument("--no-push", action="store_true")
    a = ap.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(message)s", datefmt="%H:%M:%S")
    if a.cmd == "scan":
        from .scan import run
        only = [x.strip() for x in a.only.split(",") if x.strip()] or None
        if only == ["fb"]:
            only = ["fb_only"]  # re-score with existing data, no network sources
        run(load_config(a.config), a.state, a.site, only=only, no_alerts=a.no_alerts, force_full=a.full)
    elif a.cmd == "selftest":
        return selftest()
    elif a.cmd == "fb-login":
        from .fb_runner import login
        login()
    elif a.cmd == "fb-scan":
        from .fb_runner import scan
        r = scan(push=not a.no_push)
        print(f"{len(r['cars'])} cars, errors: {r['errors'] or 'none'}")
    return 0


def selftest():
    import time
    from .fx import FX
    from .http import Fetcher
    from .sources import foreign, sslv
    f = Fetcher(delay=(0.3, 0.6))
    fx = FX.load(f)
    print(f"FX: {fx.source}  CZK={fx.rates.get('CZK')}  PLN={fx.rates.get('PLN')}  (client: {f.kind})\n")
    tests = [("ss.lv (today)", lambda: sslv.parse_car_rows(f.get(sslv.CARS + "today/sell/").text))]
    for key, (fn, country, label, _h) in foreign.SCANNERS.items():
        tests.append((label, lambda fn=fn: fn(f, fx, 15000, pages=1)))
    bad = 0
    for label, fn in tests:
        t0 = time.time()
        try:
            cars = [c.finish(fx) for c in fn()]
            full = sum(1 for c in cars if c.make and c.family and c.year and c.price_eur)
            ok = len(cars) > 0 and full >= len(cars) * 0.5
            bad += not ok
            ex = next((c for c in cars if c.make and c.family), None)
            sample = f"e.g. {ex.title[:40]!r} {ex.year} {ex.km} km €{ex.price_eur:.0f}" if ex else ""
            print(f"{'OK  ' if ok else 'WARN'} {label:<16} {len(cars):>3} ads, {full:>3} fully parsed  {time.time()-t0:4.1f}s  {sample}")
        except Exception as e:
            bad += 1
            print(f"FAIL {label:<16} {type(e).__name__}: {str(e)[:120]}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
