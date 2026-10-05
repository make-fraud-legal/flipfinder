"""ss.lv — Latvia's main classifieds. Used for (1) the LV market price baseline and
(2) fresh local listings, and (3) generic item watchlists (phones, laptops, ...)."""
from __future__ import annotations

import logging
import re
from typing import Iterable, List, Optional, Tuple

from bs4 import BeautifulSoup

from .. import normalize as N
from ..models import Car

log = logging.getLogger("flipfinder.sslv")
BASE = "https://www.ss.lv"
CARS = BASE + "/lv/transport/cars/"
# category pages under /cars/ that are not makes
NOT_MAKES = {"others", "exclusive-cars", "electric-cars", "retro-cars", "sport-cars", "tuned-cars",
             "exchange", "today", "today-2", "today-5", "search", "gaz", "moskvich", "vaz"}


def _soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "html.parser")


def list_makes(fetcher) -> List[Tuple[str, str, int]]:
    """[(slug, name, count)] from the cars index page."""
    soup = _soup(fetcher.get(CARS).text)
    out = []
    for a in soup.select("a.a_category"):
        href = a.get("href", "")
        m = re.fullmatch(r"/lv/transport/cars/([a-z0-9\-]+)/", href)
        if not m or m.group(1) in NOT_MAKES:
            continue
        cnt = 0
        sib = a.find_next_sibling("span", class_="category_cnt")
        if sib:
            cnt = N.parse_int(sib.get_text()) or 0
        out.append((m.group(1), a.get_text(strip=True), cnt))
    return out


def _max_page(soup) -> int:
    pages = [1]
    for a in soup.select("a.navi"):
        m = re.search(r"page(\d+)\.html", a.get("href", ""))
        if m:
            pages.append(int(m.group(1)))
    return max(pages)


def _headers(soup) -> List[str]:
    tds = soup.select("#head_line td")
    return [N.norm(td.get_text(" ", strip=True)) for td in tds]


def _engine(code: str) -> Tuple[Optional[float], Optional[str]]:
    """ss.lv list engine column: '2.0D' diesel, '2.0H' hybrid, 'E' electric, '1.6G' gas, '1.4' petrol."""
    c = (code or "").strip().upper()
    if not c or c == "-":
        return None, None
    if c == "E":
        return None, "electric"
    m = re.match(r"(\d\.\d)\s*([A-Z]*)", c)
    if not m:
        return None, None
    eng = float(m.group(1))
    suf = m.group(2)
    fuel = {"D": "diesel", "H": "hybrid", "G": "lpg", "": "petrol", "P": "petrol",
            "HD": "hybrid", "HB": "hybrid", "PH": "phev", "C": "cng"}.get(suf, None)
    return eng, fuel


def parse_car_rows(html: str, make_hint: Optional[str] = None) -> List[Car]:
    """Parse any ss.lv car list page (make page, model page, 'today' page)."""
    soup = _soup(html)
    heads = _headers(soup)
    attr_heads = heads[1:] if heads else []
    cars = []
    for tr in soup.select('tr[id^="tr_"]'):
        if not re.fullmatch(r"tr_\d+", tr.get("id", "")):
            continue
        tds = tr.find_all("td", recursive=False)
        desc_td = tr.select_one("td.msg2")
        if not desc_td:
            continue
        a = desc_td.select_one("a.am")
        if not a:
            continue
        idx = tds.index(desc_td)
        attrs = tds[idx + 1:]
        vals = {}
        for h, td in zip(attr_heads, attrs):
            vals[h] = td.get_text("\n", strip=True)
        href = a.get("href", "")
        url = BASE + href if href.startswith("/") else href
        native = tr["id"][3:]
        price_txt = vals.get("cena", "")
        price = N.parse_price(price_txt)
        if not price or "mēn" in price_txt or "men" in N.norm(price_txt).split():
            continue
        # make/model column: 'marka' (mixed pages: "Bmw\nX1") or 'modelis' (make pages: "X1")
        make, model_raw = None, ""
        if "marka" in vals:
            parts = vals["marka"].split("\n")
            make = N.canon_make(parts[0])
            model_raw = " ".join(parts[1:]) if len(parts) > 1 else ""
        elif "modelis" in vals:
            make = make_hint
            model_raw = vals["modelis"].replace("\n", " ")
        if not make:
            # derive from the url: /msg/lv/transport/cars/<make>/<model>/xxx.html
            m = re.search(r"/transport/cars/([a-z0-9\-]+)/([a-z0-9\-]+)/", href)
            if m:
                make = N.canon_make(m.group(1).replace("-", " ")) or make_hint
                model_raw = model_raw or m.group(2).replace("-", " ")
        eng, fuel = _engine(vals.get("tilpums", ""))
        img = tr.select_one("img.isfoto")
        img_url = img.get("src") if img else None
        if img_url and ".th2." in img_url:
            img_url = img_url.replace(".th2.", ".800.")
        car = Car(
            source="sslv", native_id=native, country="LV", url=url,
            title=(N.label(make, None) + " " + model_raw).strip() if make else a.get_text(" ", strip=True)[:80],
            price=price, currency="EUR", price_eur=price,
            make=make, model_raw=model_raw,
            year=N.parse_int(vals.get("gads")),
            km=N.parse_km(vals.get("nobraukums")) if vals.get("nobraukums", "-") != "-" else None,
            fuel=fuel, engine_l=eng, image=img_url,
            text=a.get_text(" ", strip=True),
        )
        car.family = N.canon_family(make, model_raw) if make else None
        cars.append(car)
    return cars


def crawl_make(fetcher, slug: str, max_pages: int = 200) -> List[Car]:
    first_url = f"{CARS}{slug}/sell/"
    r = fetcher.get(first_url)
    soup = _soup(r.text)
    make = N.canon_make(slug.replace("-", " "))
    cars = parse_car_rows(r.text, make_hint=make)
    last = min(_max_page(soup), max_pages)
    for p in range(2, last + 1):
        try:
            html = fetcher.get(f"{CARS}{slug}/sell/page{p}.html").text
        except FileNotFoundError:
            break
        rows = parse_car_rows(html, make_hint=make)
        if not rows:
            break
        cars.extend(rows)
    return cars


def crawl_full(fetcher, max_pages_per_make: int = 200) -> List[Car]:
    """Every 'sell' car ad on ss.lv (≈25-30k ads, ≈1000 pages). Used once a day."""
    out: List[Car] = []
    for slug, name, cnt in list_makes(fetcher):
        try:
            got = crawl_make(fetcher, slug, max_pages_per_make)
            out.extend(got)
            log.info("ss.lv %-14s %5d ads", name, len(got))
        except Exception as e:  # keep going on one bad make
            log.warning("ss.lv make %s failed: %s", slug, e)
    # dedupe (an ad can appear on two pages if the list shifts while crawling)
    seen, uniq = set(), []
    for c in out:
        if c.native_id not in seen:
            seen.add(c.native_id)
            uniq.append(c)
    return uniq


def crawl_today(fetcher, max_pages: int = 60) -> List[Car]:
    url = CARS + "today/sell/"
    r = fetcher.get(url)
    soup = _soup(r.text)
    cars = parse_car_rows(r.text)
    last = min(_max_page(soup), max_pages)
    for p in range(2, last + 1):
        rows = parse_car_rows(fetcher.get(f"{url}page{p}.html").text)
        if not rows:
            break
        cars.extend(rows)
    return cars


def parse_detail(html: str) -> dict:
    """Extra fields from an ad page: gearbox, exact km, inspection, region, AC, full text."""
    soup = _soup(html)
    out = {}

    def tdo(i):
        el = soup.select_one(f"#tdo_{i}")
        return el.get_text(" ", strip=True) if el else None

    out["model"] = tdo(31)
    out["year"] = N.year_from_text(tdo(18) or "")
    eng = tdo(15) or ""
    out["engine_l"] = N.engine_from_text(eng)
    out["fuel"] = N.canon_fuel(eng)
    out["gearbox"] = N.canon_gearbox(tdo(35) or "")
    out["km"] = N.parse_int(tdo(16))
    out["inspection"] = tdo(223)
    for td in soup.select("td.ads_contacts_name"):
        if "Vieta" in td.get_text():
            nxt = td.find_next_sibling("td")
            if nxt:
                out["location"] = nxt.get_text(" ", strip=True)
    msg = soup.select_one("#msg_div_msg")
    txt = msg.get_text(" ", strip=True) if msg else ""
    out["text"] = txt[:1500]
    page_txt = N.strip_accents(soup.get_text(" ", strip=True)).lower()
    out["has_ac"] = bool(re.search(r"kondicionier|klimata kontrol|klimat|кондиционер|климат|\bac\b|a/c", page_txt))
    return out


def enrich(fetcher, car: Car) -> Car:
    try:
        d = parse_detail(fetcher.get(car.url).text)
    except Exception as e:
        log.debug("detail failed %s: %s", car.url, e)
        return car
    car.gearbox = car.gearbox or d.get("gearbox")
    car.km = d.get("km") or car.km
    car.inspection = d.get("inspection")
    car.location = d.get("location") or car.location
    if d.get("text"):
        car.text = d["text"]
    car.has_ac = d.get("has_ac")
    return car


# ------------------------------------------------------------------ item watchlists

def parse_item_rows(html: str) -> List[dict]:
    """Generic ss.lv list parser for any category: returns title, price, url, attribute columns."""
    soup = _soup(html)
    heads = _headers(soup)
    attr_heads = heads[1:] if heads else []
    items = []
    for tr in soup.select('tr[id^="tr_"]'):
        if not re.fullmatch(r"tr_\d+", tr.get("id", "")):
            continue
        desc_td = tr.select_one("td.msg2")
        a = desc_td.select_one("a.am") if desc_td else None
        if not a:
            continue
        tds = tr.find_all("td", recursive=False)
        attrs = tds[tds.index(desc_td) + 1:]
        cols = {}
        for h, td in zip(attr_heads, attrs):
            cols[h or f"c{len(cols)}"] = td.get_text(" ", strip=True)
        price_txt = cols.pop("cena", None) or (attrs[-1].get_text(" ", strip=True) if attrs else "")
        price = N.parse_price(price_txt)
        if price is None or "mēn" in (price_txt or ""):
            continue
        img = tr.select_one("img.isfoto")
        href = a.get("href", "")
        items.append({
            "id": "sslv:" + tr["id"][3:],
            "title": a.get_text(" ", strip=True)[:160],
            "price": price,
            "url": BASE + href if href.startswith("/") else href,
            "cols": cols,
            "image": (img.get("src") or "").replace(".th2.", ".800.") if img else None,
        })
    return items


def crawl_items(fetcher, url: str, pages: int = 3) -> List[dict]:
    if not url.endswith("/") and not url.endswith(".html"):
        url += "/"
    r = fetcher.get(url)
    out = parse_item_rows(r.text)
    last = min(_max_page(_soup(r.text)), pages)
    base = url if url.endswith("/") else url.rsplit("/", 1)[0] + "/"
    for p in range(2, last + 1):
        try:
            out.extend(parse_item_rows(fetcher.get(f"{base}page{p}.html").text))
        except FileNotFoundError:
            break
    return out
