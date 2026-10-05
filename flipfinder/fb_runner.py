"""Facebook Marketplace scanner — runs on YOUR Mac (Marketplace needs a logged-in account,
and logging in from GitHub's servers would get the account flagged).

  python -m flipfinder fb-login   # once: opens a browser window, you log in to Facebook
  python -m flipfinder fb-scan    # what the background job runs every few hours

It reads the listing data Facebook already sends to the page (no clicking, no messaging),
then pushes the results to your GitHub repo's `fb-data` branch so the next cloud scan
evaluates them with everything else."""
from __future__ import annotations

import base64
import json
import logging
import os
import random
import subprocess
import tempfile
import time
from typing import List

from .config import load as load_config
from .fx import FX
from .http import Fetcher
from .models import now_iso
from .sources.foreign import parse_facebook

log = logging.getLogger("flipfinder.fb")
HOME = os.path.expanduser("~/.flipfinder")
PROFILE = os.path.join(HOME, "fb-profile")
CITY_COUNTRY = {"riga": "LV", "jelgava": "LV", "liepaja": "LV", "daugavpils": "LV", "vilnius": "LT", "kaunas": "LT",
                "klaipeda": "LT", "tallinn": "EE", "tartu": "EE", "warsaw": "PL", "krakow": "PL", "gdansk": "PL",
                "bialystok": "PL", "prague": "CZ", "brno": "CZ", "berlin": "DE", "hamburg": "DE", "munich": "DE"}


def _env() -> dict:
    p = os.path.join(HOME, "env")
    out = {}
    if os.path.exists(p):
        for line in open(p, encoding="utf-8"):
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.strip().split("=", 1)
                out[k] = v.strip().strip('"')
    return out


def _remote_config() -> dict:
    """Use the config.yaml on GitHub (what you edit), fall back to the local copy."""
    local = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config.yaml")
    repo = _env().get("GITHUB_REPO")
    if repo:
        try:
            import requests
            r = requests.get(f"https://raw.githubusercontent.com/{repo}/main/config.yaml", timeout=20)
            if r.status_code == 200:
                tmp = os.path.join(HOME, "config.remote.yaml")
                with open(tmp, "w", encoding="utf-8") as f:
                    f.write(r.text)
                return load_config(tmp)
        except Exception:
            pass
    return load_config(local)


def _browser(p, headless: bool):
    os.makedirs(PROFILE, exist_ok=True)
    kw = dict(user_data_dir=PROFILE, headless=headless, viewport={"width": 1280, "height": 900},
              locale="en-US", args=["--disable-blink-features=AutomationControlled"])
    try:
        return p.chromium.launch_persistent_context(channel="chrome", **kw)
    except Exception:
        return p.chromium.launch_persistent_context(**kw)


def login():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        ctx = _browser(p, headless=False)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto("https://www.facebook.com/marketplace/")
        print("\n  → Log in to Facebook in the window that opened.")
        print("    When you can see Marketplace listings, come back here and press Enter.\n")
        input()
        ctx.close()
    print("Saved. FlipFinder will reuse this login.")


def _collect_city(page, city: str, max_eur: float, scrolls: int, fx: FX) -> List[dict]:
    payloads = []

    def on_response(resp):
        if "/api/graphql" in resp.url:
            try:
                txt = resp.text()
            except Exception:
                return
            for line in txt.splitlines():
                line = line.strip()
                if line.startswith("{") and "marketplace_listing_title" in line:
                    try:
                        payloads.append(json.loads(line))
                    except Exception:
                        pass

    page.on("response", on_response)
    country = CITY_COUNTRY.get(city, "LV")
    cur_rate = {"CZ": fx.rates.get("CZK", 24.4), "PL": fx.rates.get("PLN", 4.27)}.get(country, 1.0)
    url = (f"https://www.facebook.com/marketplace/{city}/vehicles?maxPrice={int(max_eur * cur_rate)}"
           f"&minPrice={int(500 * cur_rate)}&sortBy=creation_time_descend&exact=false")
    page.goto(url, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(3500)
    if "/login" in page.url:
        raise RuntimeError("Facebook session expired — run 'python -m flipfinder fb-login' again")
    for blob in page.eval_on_selector_all('script[type="application/json"]', "els => els.map(e => e.textContent)"):
        if "marketplace_listing_title" in blob:
            try:
                payloads.append(json.loads(blob))
            except Exception:
                pass
    for _ in range(scrolls):
        page.mouse.wheel(0, random.randint(2500, 4000))
        page.wait_for_timeout(random.randint(1800, 3200))
    page.remove_listener("response", on_response)
    cars = parse_facebook(payloads, default_country=country)
    out = []
    for c in cars:
        c.finish(fx)
        if c.make and c.year and c.price_eur <= max_eur:
            out.append(c.to_dict())
    return out


def scan(push: bool = True) -> dict:
    from playwright.sync_api import sync_playwright
    cfg = _remote_config()
    fb = cfg["facebook"]
    fx = FX.load(Fetcher())
    allcars, errors = [], []
    with sync_playwright() as p:
        ctx = _browser(p, headless=True)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        for city in fb["cities"]:
            try:
                got = _collect_city(page, city, fb["max_price_eur"], fb.get("scrolls_per_city", 4), fx)
                allcars += got
                log.info("FB %-10s %3d cars", city, len(got))
            except Exception as e:
                errors.append(f"{city}: {e}")
                log.warning("FB %s failed: %s", city, e)
                if "expired" in str(e):
                    break
            time.sleep(random.uniform(4, 9))
        ctx.close()
    # platforms that block GitHub's servers can be scanned from the Mac instead
    from .sources.foreign import SCANNERS
    f = Fetcher()
    for key in cfg.get("mac_sources") or []:
        if key not in SCANNERS:
            continue
        fn = SCANNERS[key][0]
        try:
            got = [c.finish(fx) for c in fn(f, fx, cfg["budget"]["max_buy_eur"], pages=cfg["pages"].get(key, 4))]
            allcars += [c.to_dict() for c in got if c.make and c.year]
            log.info("Mac %-12s %3d cars", key, len(got))
        except Exception as e:
            errors.append(f"{key}: {e}")
    seen, uniq = set(), []
    for c in allcars:
        if c["id"] not in seen:
            seen.add(c["id"])
            uniq.append(c)
    result = {"at": now_iso(), "cars": uniq, "errors": errors}
    os.makedirs(HOME, exist_ok=True)
    with open(os.path.join(HOME, "fb_last.json"), "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False)
    if push:
        _push(result)
    return result


def _push(result: dict):
    env = _env()
    token, repo = env.get("GITHUB_TOKEN"), env.get("GITHUB_REPO")
    if not token or not repo:
        log.warning("No GitHub token/repo in ~/.flipfinder/env — FB results saved locally only")
        return
    d = tempfile.mkdtemp()
    with open(os.path.join(d, "fb_incoming.json"), "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False)
    auth = base64.b64encode(f"x-access-token:{token}".encode()).decode()
    git = ["git", "-C", d, "-c", "user.name=flipfinder-mac", "-c", "user.email=flipfinder@localhost"]
    subprocess.run(git[:3] + ["init", "-q", "-b", "fb-data"], check=True)
    subprocess.run(git + ["add", "-A"], check=True)
    subprocess.run(git + ["commit", "-qm", f"fb {result['at']}"], check=True)
    subprocess.run(git[:3] + ["-c", f"http.extraHeader=Authorization: Basic {auth}", "push", "-qf",
                              f"https://github.com/{repo}.git", "fb-data"], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    # kick a cloud scan so FB deals are scored + alerted right away
    try:
        import requests
        requests.post(f"https://api.github.com/repos/{repo}/actions/workflows/scan.yml/dispatches",
                      headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
                      json={"ref": "main", "inputs": {"only": "fb"}}, timeout=20)
    except Exception:
        pass
    log.info("pushed %d FB cars to %s (fb-data)", len(result["cars"]), repo)
