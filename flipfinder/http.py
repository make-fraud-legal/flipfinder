"""Polite HTTP client. Uses curl_cffi (real Chrome TLS fingerprint) when available,
falls back to requests. Detects bot walls so a blocked source is reported, not silently empty."""
from __future__ import annotations

import logging
import random
import time
from typing import Optional
from urllib.parse import urlparse

log = logging.getLogger("flipfinder.http")

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36")
BASE_HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/json;q=0.8,*/*;q=0.7",
    "Accept-Language": "en-US,en;q=0.9,lv;q=0.8",
}

BLOCK_MARKERS = ("cf-chl", "Just a moment...", "challenge-platform", "captcha-delivery",
                 "Access Denied", "px-captcha", "Attention Required!", "_Incapsula_Resource")


class Blocked(Exception):
    pass


class Fetcher:
    def __init__(self, delay=(0.7, 1.6), timeout=25):
        self.delay = delay
        self.timeout = timeout
        self._last = {}
        self.requests = 0
        try:
            from curl_cffi import requests as creq  # type: ignore
            self.s = creq.Session(impersonate="chrome")
            self.kind = "curl_cffi"
        except Exception:  # pragma: no cover - fallback path
            import requests
            self.s = requests.Session()
            self.kind = "requests"
        self.s.headers.update(BASE_HEADERS)

    def _wait(self, host: str):
        lo, hi = self.delay
        last = self._last.get(host, 0)
        gap = random.uniform(lo, hi)
        dt = time.time() - last
        if dt < gap:
            time.sleep(gap - dt)
        self._last[host] = time.time()

    def get(self, url: str, params: Optional[dict] = None, headers: Optional[dict] = None,
            retries: int = 2, check_block: bool = True):
        host = urlparse(url).netloc
        err = None
        for attempt in range(retries + 1):
            self._wait(host)
            try:
                r = self.s.get(url, params=params, headers=headers or {}, timeout=self.timeout,
                               allow_redirects=True)
                self.requests += 1
            except Exception as e:  # network error
                err = e
                time.sleep(2 + attempt * 3)
                continue
            body = r.text or ""
            if check_block and (r.status_code in (403, 429, 503) or
                                (len(body) < 60000 and any(m in body for m in BLOCK_MARKERS))):
                err = Blocked(f"{host} answered {r.status_code} (bot protection)")
                if r.status_code == 429:
                    time.sleep(10 + attempt * 10)
                    continue
                raise err
            if r.status_code >= 500:
                err = RuntimeError(f"{host} HTTP {r.status_code}")
                time.sleep(3 + attempt * 4)
                continue
            if r.status_code == 404:
                raise FileNotFoundError(url)
            return r
        raise err if err else RuntimeError(f"failed {url}")

    def json(self, url: str, params: Optional[dict] = None, headers: Optional[dict] = None):
        h = {"Accept": "application/json"}
        h.update(headers or {})
        return self.get(url, params=params, headers=h).json()
