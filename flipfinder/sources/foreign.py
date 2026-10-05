"""Foreign (and Baltic) car platforms. Each scanner pulls the NEWEST listings under the
price cap — a 'firehose' — so every new car on the site is checked against LV prices
without needing per-model URL mappings."""
from __future__ import annotations

import json
import logging
import re
from typing import List, Optional

from bs4 import BeautifulSoup

from .. import normalize as N
from ..models import Car

log = logging.getLogger("flipfinder.foreign")


def _next_data(html: str) -> dict:
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
    if not m:
        raise ValueError("no __NEXT_DATA__ on page (layout changed or blocked)")
    return json.loads(m.group(1))


# ===================================================================== sauto.cz (CZ)

def parse_sauto(data: dict) -> List[Car]:
    out = []
    for x in data.get("results", []):
        if x.get("deal_type") not in (None, "sale"):
            continue
        price = x.get("price")
        if not price or x.get("price_by_agreement"):
            continue
        mk = (x.get("manufacturer_cb") or {})
        md = (x.get("model_cb") or {})
        make = N.canon_make(mk.get("name") or mk.get("seo_name"))
        year = None
        for k in ("manufacturing_date", "in_operation_date"):
            if x.get(k):
                year = N.parse_int(x[k][:4])
                break
        img = None
        if x.get("images"):
            u = x["images"][0].get("url", "")
            img = ("https:" + u if u.startswith("//") else u) + "?fl=res,640,480,3|jpg,80"
        loc = x.get("locality") or {}
        car = Car(
            source="sauto", native_id=str(x["id"]), country="CZ",
            url=f"https://www.sauto.cz/osobni/detail/{mk.get('seo_name','auto')}/{md.get('seo_name','auto')}/{x['id']}",
            title=x.get("name", ""), price=float(price), currency="CZK",
            make=make, model_raw=md.get("name", ""),
            family=N.canon_family(make, md.get("name", "")) if make else None,
            year=year, km=x.get("tachometer"),
            fuel=N.canon_fuel((x.get("fuel_cb") or {}).get("name")),
            gearbox=N.canon_gearbox((x.get("gearbox_cb") or {}).get("name")),
            location=", ".join(v for v in (loc.get("district"), loc.get("region")) if v),
            seller="dealer" if x.get("premise") else "private",
            image=img, text=x.get("additional_model_name") or "",
            posted=x.get("create_date"),
        )
        out.append(car)
    return out


def scan_sauto(fetcher, fx, max_eur: float, pages: int = 4) -> List[Car]:
    max_czk = int(max_eur * fx.rates.get("CZK", 24.4))
    cars = []
    for p in range(pages):
        data = fetcher.json("https://www.sauto.cz/api/v1/items/search", params={
            "limit": 100, "offset": p * 100, "category_id": 838, "operating_lease": "false",
            "price_to": max_czk})
        got = parse_sauto(data)
        cars.extend(got)
        if len(data.get("results", [])) < 100:
            break
    return cars


# ===================================================================== bazos.cz (CZ)

_BAZOS_JUNK = re.compile(r"\b(dily|dil|na dily|kola|pneu|disky|alu kola|motor na|prevodovka|"
                         r"naraznik|svetlo|blatnik|dvere|sedacky|koupim|koupim|vymenim|hledam)\b")


def parse_bazos(html: str) -> List[Car]:
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for box in soup.select("div.inzeraty"):
        a = box.select_one("h2.nadpis a")
        if not a:
            continue
        href = a.get("href", "")
        m = re.search(r"/inzerat/(\d+)/", href)
        if not m:
            continue
        title = a.get_text(" ", strip=True)
        if _BAZOS_JUNK.search(N.norm(title)):
            continue
        price = N.parse_price((box.select_one("div.inzeratycena") or a).get_text(" ", strip=True))
        if not price or price < 15000:  # CZK; filters parts / "dohodou"
            continue
        popis = box.select_one("div.popis")
        text = popis.get_text(" ", strip=True) if popis else ""
        lok = box.select_one("div.inzeratylok")
        img = box.select_one("img.obrazek")
        car = Car(source="bazos", native_id=m.group(1), country="CZ",
                  url="https://auto.bazos.cz" + href if href.startswith("/") else href,
                  title=title, price=price, currency="CZK",
                  location=lok.get_text(" ", strip=True).split(" ")[0] if lok else "",
                  image=img.get("src") if img else None, text=text, seller="private")
        out.append(car)
    return out


def scan_bazos(fetcher, fx, max_eur: float, pages: int = 8) -> List[Car]:
    max_czk = int(max_eur * fx.rates.get("CZK", 24.4))
    cars = []
    for p in range(pages):
        url = "https://auto.bazos.cz/" + (f"{p * 20}/" if p else "")
        cars.extend(parse_bazos(fetcher.get(url, params={"cenaod": 20000, "cenado": max_czk}).text))
    return cars


# ===================================================================== otomoto.pl (PL)

def parse_otomoto(html: str) -> List[Car]:
    nd = _next_data(html)
    us = nd.get("props", {}).get("pageProps", {}).get("urqlState", {}) or {}
    search = None
    for v in us.values():
        d = v.get("data") if isinstance(v, dict) else None
        if d and "advertSearch" in d:
            search = json.loads(d)["advertSearch"]
            break
    if not search:
        raise ValueError("otomoto: advertSearch missing from page data")
    out = []
    for e in search.get("edges", []):
        n = e.get("node") or {}
        params = {p.get("key"): p for p in n.get("parameters", [])}
        pv = lambda k: (params.get(k) or {}).get("value")  # noqa: E731
        pd = lambda k: (params.get(k) or {}).get("displayValue")  # noqa: E731
        amt = ((n.get("price") or {}).get("amount") or {})
        price = N.parse_price(amt.get("units") or amt.get("value"))
        if not price:
            continue
        make = N.canon_make(pd("make") or pv("make"))
        model_raw = (pd("model") or pv("model") or "").replace("seria-", "seria ").replace("klasa-", "klasa ")
        loc = n.get("location") or {}
        cc = N.parse_int(pv("engine_capacity"))
        thumb = (n.get("thumbnail") or {})
        car = Car(source="otomoto", native_id=str(n.get("id")), country="PL", url=n.get("url", ""),
                  title=n.get("title", ""), price=price, currency=amt.get("currencyCode") or "PLN",
                  make=make, model_raw=model_raw,
                  family=N.canon_family(make, model_raw) if make else None,
                  year=N.parse_int(pv("year")), km=N.parse_int(pv("mileage")),
                  fuel=N.canon_fuel(pv("fuel_type")), gearbox=N.canon_gearbox(pv("gearbox")),
                  engine_l=round(cc / 1000, 1) if cc else None,
                  power_kw=int(N.parse_int(pv("engine_power")) * 0.7355) if pv("engine_power") else None,
                  location=", ".join(x for x in ((loc.get("city") or {}).get("name"), (loc.get("region") or {}).get("name")) if x),
                  seller="dealer" if n.get("sellerLink") and (n["sellerLink"].get("websiteUrl") or "") else "private",
                  image=thumb.get("x2") or thumb.get("x1"), text=n.get("shortDescription") or "",
                  posted=n.get("createdAt"))
        out.append(car)
    return out


def scan_otomoto(fetcher, fx, max_eur: float, pages: int = 8) -> List[Car]:
    max_pln = int(max_eur * fx.rates.get("PLN", 4.27))
    cars = []
    for p in range(1, pages + 1):
        html = fetcher.get("https://www.otomoto.pl/osobowe", params={
            "search[order]": "created_at_first:desc", "search[filter_float_price:to]": max_pln,
            "search[filter_float_price:from]": 2500, "page": p}).text
        cars.extend(parse_otomoto(html))
    return cars


# ===================================================================== autoplius.lt (LT)

def parse_autoplius(html: str) -> List[Car]:
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for a in soup.select("a.announcement-item"):
        href = a.get("href", "")
        m = re.search(r"-(\d+)\.html", href)
        if not m:
            continue
        title_el = a.select_one(".announcement-title")
        title = title_el.get_text(" ", strip=True) if title_el else ""
        price_el = a.select_one(".announcement-pricing-info strong") or a.select_one(".announcement-pricing-info")
        price = N.parse_price(price_el.get_text(" ", strip=True)) if price_el else None
        if not price:
            continue
        params = [s.get_text(" ", strip=True) for s in a.select(".announcement-parameters span")]
        year = km = eng = fuel = gear = None
        city = ""
        for ptxt in params:
            t = ptxt.strip().rstrip(",")
            if re.fullmatch(r"(19|20)\d\d(-\d\d)?", t):
                year = int(t[:4])
            elif re.search(r"\bkm\b", t):
                km = N.parse_int(t)
            elif re.search(r"\bl\.", t) or "kW" in t:
                eng = N.engine_from_text(t)
            elif N.canon_gearbox(t) and len(t) < 20:
                gear = gear or N.canon_gearbox(t)
            elif N.canon_fuel(t) and len(t) < 25:
                fuel = fuel or N.canon_fuel(t)
        if params:
            city = params[-1] if not re.search(r"\d", params[-1]) else ""
        make, rest = N.find_make_in_text(title)
        img = a.select_one("img.js-gallery-main-photo") or a.select_one("img")
        car = Car(source="autoplius", native_id=m.group(1), country="LT", url=href,
                  title=title, price=price, currency="EUR", make=make, model_raw=rest,
                  family=N.canon_family(make, rest) if make else None,
                  year=year, km=km, fuel=fuel, gearbox=gear, engine_l=eng, location=city,
                  image=img.get("src") if img else None, text=" ".join(params))
        out.append(car)
    return out


def scan_autoplius(fetcher, fx, max_eur: float, pages: int = 8) -> List[Car]:
    cars = []
    for p in range(1, pages + 1):
        html = fetcher.get("https://en.autoplius.lt/ads/used-cars", params={
            "order_by": 3, "order_direction": "DESC", "sell_price_to": int(max_eur),
            "sell_price_from": 500, "page_nr": p}).text
        got = parse_autoplius(html)
        if not got:
            break
        cars.extend(got)
    return cars


# ===================================================================== auto24 (EE + LV, shared inventory)

def parse_auto24(html: str, base: str = "https://www.auto24.lv") -> List[Car]:
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for row in soup.select("div.result-row"):
        a = row.select_one("a.main")
        if not a:
            continue
        href = a.get("href", "")
        m = re.search(r"/(\d+)(?:$|[?#])", href)
        if not m:
            continue
        spans = a.find_all("span")
        make_txt = spans[0].get_text(" ", strip=True) if spans else ""
        model_el = a.select_one(".model")
        model_raw = model_el.get_text(" ", strip=True) if model_el else ""
        eng_el = a.select_one(".engine")
        eng_txt = eng_el.get_text(" ", strip=True) if eng_el else ""
        price_el = row.select_one(".finance .price") or row.select_one(".price")
        price = N.parse_price(price_el.get_text(" ", strip=True)) if price_el else None
        if not price:
            continue
        ex = row.select_one(".extra")
        g = lambda sel: (ex.select_one(sel).get_text(" ", strip=True) if ex and ex.select_one(sel) else "")  # noqa: E731
        make = N.canon_make(make_txt)
        img = row.select_one("img.thumb")
        car = Car(source="auto24", native_id=m.group(1), country="EE",
                  url=base + href if href.startswith("/") else href,
                  title=a.get_text(" ", strip=True), price=price, currency="EUR",
                  make=make, model_raw=model_raw,
                  family=N.canon_family(make, model_raw) if make else None,
                  year=N.parse_int(g(".year")), km=N.parse_int(g(".mileage")),
                  fuel=N.canon_fuel(g(".fuel")), gearbox=N.canon_gearbox(g(".transmission")),
                  engine_l=N.engine_from_text(eng_txt), power_kw=N.power_kw_from_text(eng_txt),
                  image=img.get("src") if img else None,
                  text="VAT" if "VAT" in (price_el.parent.get_text() if price_el else "") else "")
        out.append(car)
    return out


def scan_auto24(fetcher, fx, max_eur: float, pages: int = 4) -> List[Car]:
    cars = []
    base = "https://www.auto24.lv"
    for p in range(pages):
        html = fetcher.get(base + "/kasutatud/nimekiri.php", params={
            "bn": 2, "a": 100, "ae": 1, "af": 100, "g1": 500, "g2": int(max_eur),
            "otsi": "search", "ak": p * 100}).text
        got = parse_auto24(html, base)
        if not got:
            break
        cars.extend(got)
    return cars


# ===================================================================== autoscout24 (DE)

def parse_autoscout24(html: str) -> List[Car]:
    pp = _next_data(html).get("props", {}).get("pageProps", {})
    out = []
    for l in pp.get("listings", []) or []:
        v = l.get("vehicle") or {}
        tr = l.get("tracking") or {}
        price = (l.get("price") or {}).get("priceRaw") or N.parse_price(tr.get("price"))
        if not price:
            continue
        make = N.canon_make(v.get("make"))
        model_raw = v.get("modelGroup") or v.get("model") or ""
        fr = tr.get("firstRegistration") or ""
        loc = l.get("location") or {}
        imgs = l.get("images") or []
        url = l.get("url", "")
        slug_words = url.rsplit("/", 1)[-1].replace("-", " ")
        car = Car(source="autoscout24", native_id=str(l.get("id")), country=loc.get("countryCode") or "DE",
                  url="https://www.autoscout24.com" + url if url.startswith("/") else url,
                  title=" ".join(x for x in (v.get("make"), v.get("model"), v.get("modelVersionInput")) if x),
                  price=float(price), currency="EUR", make=make,
                  model_raw=f"{v.get('model') or ''} {model_raw}",
                  family=(N.canon_family(make, model_raw) or N.canon_family(make, v.get("model"))) if make else None,
                  year=N.year_from_text(fr), km=N.parse_int(tr.get("mileage")),
                  fuel=N.canon_fuel(v.get("fuel")), gearbox=N.canon_gearbox(v.get("transmission")),
                  engine_l=N.engine_from_text(v.get("engineDisplacementInCCM")),
                  location=" ".join(x for x in (loc.get("zip"), loc.get("city")) if x),
                  seller=(l.get("seller") or {}).get("type", "").lower() or None,
                  image=imgs[0].replace("/250x188.webp", "/480x360.webp") if imgs else None,
                  text=slug_words, hint=(tr.get("priceLabel") or "").strip() or None)
        out.append(car)
    return out


def scan_autoscout24(fetcher, fx, max_eur: float, pages: int = 10, country: str = "D") -> List[Car]:
    cars = []
    for p in range(1, pages + 1):
        html = fetcher.get("https://www.autoscout24.com/lst", params={
            "atype": "C", "cy": country, "desc": 1, "sort": "age", "ustate": "U",
            "pricefrom": 1000, "priceto": int(max_eur), "page": p}).text
        got = parse_autoscout24(html)
        if not got:
            break
        cars.extend(got)
    return cars


# ===================================================================== Facebook payload (parsed here,
# collected on the user's Mac by fb_runner.py because Marketplace needs a login)

def _walk(obj):
    if isinstance(obj, dict):
        yield obj
        for v in obj.values():
            yield from _walk(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _walk(v)


FB_COUNTRY = {"latvia": "LV", "lithuania": "LT", "estonia": "EE", "poland": "PL", "czech": "CZ",
              "germany": "DE", "finland": "FI", "sweden": "SE"}


def parse_facebook(payloads, default_country: str = "LV") -> List[Car]:
    """payloads: list of decoded JSON objects (page script blobs / GraphQL responses)."""
    out, seen = [], set()
    for p in payloads:
        for d in _walk(p):
            if "marketplace_listing_title" not in d or not d.get("id"):
                continue
            if d.get("is_sold") or d.get("is_pending") or d.get("is_hidden"):
                continue
            lid = str(d["id"])
            if lid in seen:
                continue
            lp = d.get("listing_price") or {}
            price = N.parse_price(lp.get("amount"))
            fa = lp.get("formatted_amount") or ""
            cur = "EUR"
            for code in ("CZK", "PLN", "EUR", "SEK", "NOK", "DKK", "USD", "GBP"):
                if code in fa:
                    cur = code
            if "Kč" in fa:
                cur = "CZK"
            if "zł" in fa:
                cur = "PLN"
            if not price or price < 200:
                continue
            title = d.get("marketplace_listing_title") or ""
            subs = " ".join((s or {}).get("subtitle", "") for s in (d.get("custom_sub_titles_with_rendering_flags") or []))
            rg = (d.get("location") or {}).get("reverse_geocode") or {}
            loc = rg.get("city") or ((rg.get("city_page") or {}).get("display_name")) or ""
            country = default_country
            disp = ((rg.get("city_page") or {}).get("display_name") or "").lower()
            for word, cc in FB_COUNTRY.items():
                if word in disp:
                    country = cc
            img = ((d.get("primary_listing_photo") or {}).get("image") or {}).get("uri")
            posted = None
            if d.get("creation_time"):
                import datetime as _dt
                posted = _dt.datetime.fromtimestamp(int(d["creation_time"]), _dt.timezone.utc).isoformat()
            seen.add(lid)
            out.append(Car(source="facebook", native_id=lid, country=country,
                           url=f"https://www.facebook.com/marketplace/item/{lid}/",
                           title=title, price=price, currency=cur, km=N.parse_km(subs) if subs.strip() else None,
                           location=loc, image=img, text=subs.strip(), posted=posted))
    return out


SCANNERS = {
    # key: (function, country, label, home url)
    "sauto_cz": (scan_sauto, "CZ", "sauto.cz", "https://www.sauto.cz"),
    "bazos_cz": (scan_bazos, "CZ", "bazos.cz", "https://auto.bazos.cz"),
    "otomoto_pl": (scan_otomoto, "PL", "otomoto.pl", "https://www.otomoto.pl"),
    "autoplius_lt": (scan_autoplius, "LT", "autoplius.lt", "https://autoplius.lt"),
    "auto24": (scan_auto24, "EE", "auto24 (LV/EE)", "https://www.auto24.lv"),
    "autoscout24_de": (scan_autoscout24, "DE", "autoscout24.de", "https://www.autoscout24.de"),
}
