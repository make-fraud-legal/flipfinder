"""Offline end-to-end run with SYNTHETIC listings (no network) — used to test the
pipeline + dashboard.  python tests/demo_run.py  → writes demo_site/ (fake data!)"""
import math
import os
import random
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flipfinder import config as C  # noqa: E402
from flipfinder import scan as S  # noqa: E402
from flipfinder.fx import FX  # noqa: E402
from flipfinder.models import Car  # noqa: E402
from flipfinder.sources import foreign, sslv  # noqa: E402

random.seed(7)
FAMS = [  # make, family, model text, base price (new-ish), diesel share, engine sizes
    ("volkswagen", "golf", "Golf 6", 16000, .6, [1.4, 1.6, 2.0]), ("volkswagen", "passat", "Passat (B7)", 21000, .8, [1.6, 2.0]),
    ("volkswagen", "up", "Up!", 10500, 0, [1.0]), ("skoda", "octavia", "Octavia", 17000, .7, [1.6, 1.9, 2.0]),
    ("skoda", "fabia", "Fabia", 11000, .4, [1.2, 1.4]), ("toyota", "corolla", "Corolla", 17000, .2, [1.4, 1.6]),
    ("toyota", "avensis", "Avensis", 19000, .5, [1.8, 2.0, 2.2]), ("toyota", "rav4", "RAV4", 26000, .4, [2.0, 2.2]),
    ("bmw", "3-series", "320", 28000, .8, [2.0]), ("bmw", "5-series", "520", 36000, .85, [2.0, 3.0]),
    ("audi", "a4", "A4", 27000, .8, [2.0]), ("audi", "a6", "A6", 35000, .85, [2.0, 3.0]),
    ("mercedes", "c-class", "C220", 30000, .8, [2.1]), ("mercedes", "e-class", "E220", 38000, .85, [2.1]),
    ("ford", "focus", "Focus", 13000, .5, [1.6, 2.0]), ("opel", "astra", "Astra", 12500, .5, [1.4, 1.7]),
    ("honda", "civic", "Civic", 15000, .3, [1.8, 2.2]), ("mazda", "6", "6", 18000, .4, [2.0, 2.2]),
    ("volvo", "v70", "V70", 25000, .9, [2.4]), ("volvo", "xc90", "XC90", 40000, .9, [2.4]),
    ("nissan", "qashqai", "Qashqai", 17000, .6, [1.5, 1.6, 2.0]), ("renault", "megane", "Megane", 12000, .6, [1.5, 1.6]),
    ("hyundai", "i30", "i30", 13000, .4, [1.4, 1.6]), ("kia", "ceed", "Ceed", 13000, .4, [1.4, 1.6]),
]
WORDS = ["Servisa grāmatiņa", "1 īpašnieks", "Labā stāvoklī", "Jauna TA", "Ziemas riepas", "Kondicionieris", "Klimata kontrole"]


def price(base, year, km, diesel, now=2026):
    age = now - year + .5
    p = base * math.exp(-0.13 * age + 0.0015 * age * age) * math.exp(-0.0011 * km / 1000) * (1.07 if diesel else 1)
    return max(500, round(p * math.exp(random.gauss(0, .16)), -1))


def lv_cars(n=int(os.environ.get("DEMO_N", 4200))):
    out = []
    for i in range(n):
        mk, fam, model, base, dsh, engs = random.choice(FAMS)
        y = random.randint(2004, 2022)
        km = max(5000, int((2026 - y) * random.gauss(17500, 4500)))
        d = random.random() < dsh
        c = Car(source="sslv", native_id=str(50000000 + i), country="LV",
                url=f"https://www.ss.lv/msg/lv/transport/cars/{mk}/{fam}/demo{i}.html",
                title=f"{mk.title()} {model}", price=price(base, y, km, d), make=mk, family=fam, model_raw=model,
                year=y, km=km, fuel="diesel" if d else "petrol", engine_l=random.choice(engs),
                text=" ".join(random.sample(WORDS, 2)))
        if random.random() < .03:
            c.text += " pēc avārijas, uz detaļām"
            c.price *= .5
        out.append(c)
    return out


def foreign_cars(src, country, cur, rate, factor, n=60):
    out = []
    for i in range(n):
        mk, fam, model, base, dsh, engs = random.choice(FAMS)
        y = random.randint(2006, 2021)
        km = max(5000, int((2026 - y) * random.gauss(18000, 5000)))
        d = random.random() < dsh
        p = price(base, y, km, d) * factor * math.exp(random.gauss(0, .12))
        c = Car(source=src, native_id=f"{src}{i}", country=country, url=f"https://example.com/{src}/{i}",
                title=f"{mk.title()} {model} {'TDI' if d and mk in ('volkswagen', 'skoda', 'audi') else ''}", price=round(p * rate, -1),
                currency=cur, make=mk, family=fam, model_raw=model, year=y, km=km, fuel="diesel" if d else "petrol",
                engine_l=random.choice(engs), gearbox=random.choice(["manual", "manual", "auto"]),
                location={"CZ": "Brno", "PL": "Warszawa", "DE": "Berlin", "LT": "Vilnius", "EE": "Tallinn"}[country],
                text=random.choice(["", "Motorschaden" if country == "DE" else "", "servisní kniha", "1. majitel"]))
        out.append(c)
    return out


def main():
    out = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "demo_site")
    state = os.path.join(os.path.dirname(out), "demo_state")
    shutil.rmtree(out, ignore_errors=True)
    shutil.rmtree(state, ignore_errors=True)
    LV = lv_cars()
    sslv.crawl_full = lambda f, **k: LV
    sslv.crawl_today = lambda f, **k: LV[:200]
    sslv.enrich = lambda f, c: c
    sslv.crawl_items = lambda f, url, pages=3: [
        {"id": f"sslv:i{i}", "title": f"iPhone {m} {g}GB labā stāvoklī", "price": float(p), "url": f"https://www.ss.lv/msg/i{i}.html",
         "cols": {"modelis": f"iPhone {m}", "apjoms, gb": str(g), "stav.": "lietota"}, "image": None}
        for i, (m, g, p) in enumerate([(13, 128, 330), (13, 128, 310), (13, 128, 350), (13, 128, 340), (13, 128, 210),
                                       (14, 128, 420), (14, 128, 450), (14, 128, 440), (14, 128, 430), (14, 128, 300), (15, 256, 690)])]
    FX.load = classmethod(lambda cls, f: cls())
    foreign.SCANNERS = {
        "sauto_cz": (lambda f, fx, m, pages=4: foreign_cars("sauto", "CZ", "CZK", 24.4, .86), "CZ", "sauto.cz", ""),
        "otomoto_pl": (lambda f, fx, m, pages=4: foreign_cars("otomoto", "PL", "PLN", 4.27, .84), "PL", "otomoto.pl", ""),
        "autoscout24_de": (lambda f, fx, m, pages=4: foreign_cars("autoscout24", "DE", "EUR", 1, .9), "DE", "autoscout24", ""),
        "autoplius_lt": (lambda f, fx, m, pages=4: foreign_cars("autoplius", "LT", "EUR", 1, .93), "LT", "autoplius.lt", ""),
        "bazos_cz": (lambda f, fx, m, pages=4: (_ for _ in ()).throw(RuntimeError("demo: simulated outage")), "CZ", "bazos.cz", ""),
    }
    cfg = C.load(os.path.join(os.path.dirname(out), "config.yaml"))
    os.environ.pop("TELEGRAM_BOT_TOKEN", None)
    d = S.run(cfg, state, out, no_alerts=True)
    import json as _j
    from flipfinder.models import now_iso
    fbc = foreign_cars("facebook", "LT", "EUR", 1, .8, n=12)
    for c in fbc:
        c.country = "LV" if int(c.native_id[-1]) % 2 else "LT"
        c.location = "Rīga" if c.country == "LV" else "Vilnius"
    with open(os.path.join(state, "fb_incoming.json"), "w") as f:
        _j.dump({"at": now_iso(), "cars": [c.to_dict() for c in fbc], "errors": []}, f)
    # second run to exercise state merge + "new" logic
    d = S.run(cfg, state, out, no_alerts=True)
    print("deals", len(d["deals"]), "hot", d["stats"]["hot"], "personal", len(d["personal"]), "items", len(d["items"]),
          "market", len(d["market"]))
    shutil.rmtree(state, ignore_errors=True)
    p = os.path.join(out, "data.json")
    dd = _j.load(open(p))
    dd["demo"] = True
    _j.dump(dd, open(p, "w"))


if __name__ == "__main__":
    main()
