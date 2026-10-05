"""Parser tests built from real page samples captured from each site (Oct 2026).
Run:  python -m pytest -q   (or: python tests/test_parsers.py)"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flipfinder import normalize as N  # noqa: E402
from flipfinder.fx import FX  # noqa: E402
from flipfinder.sources import sslv, foreign  # noqa: E402

FX0 = FX()
HERE = os.path.dirname(__file__)


def fx(name):
    with open(os.path.join(HERE, "fixtures", name), encoding="utf-8") as f:
        return f.read()


def test_sslv_model_page():
    cars = sslv.parse_car_rows(fx("sslv_model_page.html"))
    assert len(cars) == 2
    a, b = cars
    assert a.make == "volkswagen" and a.family == "up", (a.make, a.family)
    assert a.year == 2014 and a.km == 121000 and a.price == 6400 and a.engine_l == 1.0 and a.fuel == "petrol"
    assert a.image.endswith(".800.jpg")
    assert b.fuel == "electric" and b.km == 62000 and b.price == 10500


def test_sslv_today_page():
    cars = sslv.parse_car_rows(fx("sslv_today.html"))
    assert [c.make for c in cars] == ["bmw", "volkswagen", "mercedes"]
    assert [c.family for c in cars] == ["x1", "passat", "e-class"]
    assert cars[0].fuel == "diesel" and cars[0].km == 303000 and cars[0].price == 6899
    assert cars[1].fuel == "petrol" and cars[1].engine_l == 1.4
    assert cars[2].km is None


def test_sslv_items():
    html = """<table><tr id="head_line"><td>Sludinājumi datums</td><td>Modelis</td><td>Apjoms, Gb</td><td>Stāv.</td><td>Cena</td></tr>
    <tr id="tr_9"><td class="msga2 pp0"></td><td class="msga2"></td><td class="msg2"><div class="d1"><a class="am" href="/msg/lv/electronics/x.html">Продаю iPhone 16, 128 GB</a></div></td>
    <td>iPhone 16</td><td>128</td><td>lietota</td><td>510  €</td></tr></table>"""
    items = sslv.parse_item_rows(html)
    assert items[0]["price"] == 510 and items[0]["cols"]["modelis"] == "iPhone 16"


def test_sauto():
    data = {"results": [{"category": {"id": 838}, "deal_type": "sale", "fuel_cb": {"name": "CNG + benzín"},
                         "gearbox_cb": {"name": "Manuální"}, "id": 210585317,
                         "images": [{"url": "//d19-a.sdn.cz/d_19/c_img_qC_A/kQ/6adc.jpeg"}],
                         "locality": {"district": "Brno-venkov", "region": "Jihomoravský kraj"},
                         "manufacturer_cb": {"name": "Volkswagen", "seo_name": "volkswagen"},
                         "manufacturing_date": "2013-01-01", "model_cb": {"name": "Up!", "seo_name": "up"},
                         "name": "Volkswagen Up!, VW UP 1.0mpi CNG EcoFuel Move", "premise": None, "price": 85000,
                         "price_by_agreement": False, "tachometer": 195200},
                        {"deal_type": "sale", "id": 2, "manufacturer_cb": {"name": "BMW", "seo_name": "bmw"},
                         "model_cb": {"name": "Řada 3", "seo_name": "rada-3"}, "price": 199000,
                         "in_operation_date": "2012-03-01", "tachometer": 210000, "fuel_cb": {"name": "Nafta"},
                         "gearbox_cb": {"name": "Automatická"}, "premise": {"name": "X"}}]}
    cars = foreign.parse_sauto(data)
    a, b = [c.finish(FX0) for c in cars]
    assert (a.make, a.family, a.year, a.km, a.fuel, a.gearbox) == ("volkswagen", "up", 2013, 195200, "cng", "manual")
    assert 3000 < a.price_eur < 4000 and a.url.endswith("/volkswagen/up/210585317")
    assert (b.family, b.fuel, b.gearbox, b.seller, b.year) == ("3-series", "diesel", "auto", "dealer", 2012)


def test_bazos():
    html = """<div class="inzeraty inzeratyflex"><div class="inzeratynadpis"><a href="/inzerat/224023480/volkswagen-up-10mpi-klima.php"><img src="https://www.bazos.cz/img/1t/480/224023480.jpg" class="obrazek"></a>
<h2 class="nadpis"><a href="/inzerat/224023480/volkswagen-up-10mpi-klima.php">Volkswagen Up 1.0Mpi Klima</a></h2><div class="popis">Nabízím k prodeji Volkswagen up s benzínovým motorem 1.0 Mpi o výkonu 55kw. Datum první registrace 13.3.2012. Najeto má 116800km se SERVISNÍ knížkou</div></div>
<div class="inzeratycena"><b><span translate="no">  84 000 Kč</span></b></div><div class="inzeratylok">Hradec Králové<br>503 32</div></div>
<div class="inzeraty"><h2 class="nadpis"><a href="/inzerat/1/x.php">Alu kola 15 Škoda</a></h2><div class="inzeratycena">3 000 Kč</div></div>"""
    cars = [c.finish(FX0) for c in foreign.parse_bazos(html)]
    assert len(cars) == 1
    c = cars[0]
    assert (c.make, c.family, c.year, c.km, c.price) == ("volkswagen", "up", 2012, 116800, 84000), (c.make, c.family, c.year, c.km)
    assert c.fuel == "petrol" and c.power_kw == 55


def test_otomoto():
    edge = {"node": {"id": "6150709028", "title": "Volkswagen up! 1.0 black", "createdAt": "2026-09-21T13:38:06Z",
                     "shortDescription": "SalonPolska*Klima", "url": "https://www.otomoto.pl/osobowe/oferta/volkswagen-up-ID6IfKok.html",
                     "location": {"city": {"name": "Wągrowiec"}, "region": {"name": "Wielkopolskie"}},
                     "price": {"amount": {"units": 19900, "value": "19900", "currencyCode": "PLN"}},
                     "sellerLink": {"name": "Auto Komis AMAG", "websiteUrl": "https://AMAG.otomoto.pl"},
                     "parameters": [{"key": "make", "displayValue": "Volkswagen", "value": "volkswagen"},
                                    {"key": "fuel_type", "displayValue": "Benzyna", "value": "petrol"},
                                    {"key": "gearbox", "displayValue": "Manualna", "value": "manual"},
                                    {"key": "mileage", "displayValue": "103000 km", "value": "103000"},
                                    {"key": "engine_capacity", "displayValue": "999 cm3", "value": "999"},
                                    {"key": "engine_power", "displayValue": "75 KM", "value": "75"},
                                    {"key": "model", "displayValue": "up!", "value": "up"},
                                    {"key": "year", "displayValue": "2012", "value": "2012"}],
                     "thumbnail": {"x2": "https://ireland.apollo.olxcdn.com/v1/files/a/image;s=640x480"}}}
    edge2 = json.loads(json.dumps(edge))
    edge2["node"]["id"] = "2"
    edge2["node"]["parameters"][0]["value"] = "bmw"
    edge2["node"]["parameters"][0]["displayValue"] = "BMW"
    edge2["node"]["parameters"][6] = {"key": "model", "displayValue": "Seria 3", "value": "seria-3"}
    nd = {"props": {"pageProps": {"urqlState": {"k": {"data": json.dumps({"advertSearch": {"totalCount": 2, "edges": [edge, edge2]}})}}}}}
    html = '<html><script id="__NEXT_DATA__" type="application/json">' + json.dumps(nd) + "</script></html>"
    a, b = [c.finish(FX0) for c in foreign.parse_otomoto(html)]
    assert (a.make, a.family, a.year, a.km, a.fuel, a.gearbox, a.engine_l) == ("volkswagen", "up", 2012, 103000, "petrol", "manual", 1.0)
    assert a.currency == "PLN" and 4000 < a.price_eur < 5200
    assert b.make == "bmw" and b.family == "3-series"


def test_autoplius():
    html = """<a href="https://en.autoplius.lt/ads/volkswagen-up-1-0-l-hatchback-2013-petrol-gas-32522652.html" class="announcement-item is-enhanced">
<div class="announcement-media"><img class="js-gallery-main-photo" src="https://autoplius-img.dgn.lt/ann_25_415214960/x.jpg"></div>
<div class="announcement-body"><div class="announcement-title"> Volkswagen Up </div><div class="announcement-title-parameters"><div class="announcement-parameters "> <span>2013-10</span> <span>Hatchback</span> </div></div>
<div class="announcement-pricing-info"><strong> 2 600 € </strong></div>
<div class="announcement-parameters-block"><div class="announcement-parameters "> <span> Petrol / LPG </span> <span>Manual</span> <span> 1.0 l., 44 kW </span> <span>236 759 km</span> <span>Vilnius</span> </div></div></div></a>"""
    c = foreign.parse_autoplius(html)[0].finish(FX0)
    assert (c.make, c.family, c.year, c.km, c.price, c.gearbox, c.engine_l, c.location) == \
        ("volkswagen", "up", 2013, 236759, 2600, "manual", 1.0, "Vilnius"), c
    assert c.fuel == "lpg"


def test_auto24():
    html = """<div class="result-row item-odd"><div class="thumbnail"><a href="/lietoti/4344114" class="small-image"><img class="thumb" src="https://img13.img-bcg.eu/h32/1edd03/s1/v2/206545751.jpg"></a></div>
<div class="description"><div class="title"><a href="/lietoti/4344114" class="main"><span>Volkswagen</span> <span class="model">Up</span> <span class="engine">1.0 44kW</span></a></div>
<div class="finance"><span class="pv"><span class="price">4590 €</span></span></div>
<div class="extra"> <span class="year">2014</span><span class="mileage">79&nbsp;277&nbsp;km</span><span class="fuel sm-none">Benzīns</span><span class="transmission sm-none">Mehāniskā</span><span class="bodytype">Hečbeks</span></div></div></div>"""
    c = foreign.parse_auto24(html)[0].finish(FX0)
    assert (c.make, c.family, c.year, c.km, c.price, c.fuel, c.gearbox, c.engine_l, c.power_kw) == \
        ("volkswagen", "up", 2014, 79277, 4590, "petrol", "manual", 1.0, 44), c


def test_autoscout24():
    l = {"id": "7d04", "price": {"priceRaw": 1300}, "url": "/offers/volkswagen-up-move-gasoline-red-cat_ma74mo19750-7d04",
         "vehicle": {"make": "Volkswagen", "model": "up!", "modelGroup": "Up", "modelVersionInput": "move", "transmission": "Manual",
                     "fuel": "Gasoline", "engineDisplacementInCCM": "999 cc"},
         "location": {"countryCode": "DE", "zip": "01968", "city": "Senftenberg"},
         "seller": {"type": "Dealer"}, "images": ["https://prod.pictures.autoscout24.net/listing-images/x.jpg/250x188.webp"],
         "tracking": {"firstRegistration": "11-2013", "mileage": "216526", "price": "1300", "priceLabel": "toolow-price "}}
    l2 = json.loads(json.dumps(l))
    l2["id"] = "2"
    l2["vehicle"].update({"make": "Mercedes-Benz", "model": "C 220", "modelGroup": "C-Class", "fuel": "Diesel", "transmission": "Automatic"})
    nd = {"props": {"pageProps": {"listings": [l, l2]}}}
    html = '<script id="__NEXT_DATA__" type="application/json">' + json.dumps(nd) + "</script>"
    a, b = [c.finish(FX0) for c in foreign.parse_autoscout24(html)]
    assert (a.make, a.family, a.year, a.km, a.fuel, a.gearbox, a.engine_l, a.hint) == \
        ("volkswagen", "up", 2013, 216526, "petrol", "manual", 1.0, "toolow-price")
    assert (b.make, b.family, b.fuel, b.gearbox) == ("mercedes", "c-class", "diesel", "auto")


def test_facebook():
    payload = {"data": {"x": [{"__typename": "GroupCommerceProductItem", "id": "1070411522567191",
                               "primary_listing_photo": {"image": {"uri": "https://scontent/x.jpg"}},
                               "creation_time": 1791196742,
                               "listing_price": {"amount": "1700.00", "formatted_amount": "1 700 €"},
                               "location": {"reverse_geocode": {"city": "Tukums", "city_page": {"display_name": "Тукумс"}}},
                               "is_sold": False, "marketplace_listing_title": "2005 Subaru 2.5 B\\G  Outback",
                               "custom_sub_titles_with_rendering_flags": [{"subtitle": "385 тыс. км"}]},
                              {"id": "2", "marketplace_listing_title": "Skoda Octavia 1.9 TDI",
                               "listing_price": {"amount": "92000.00", "formatted_amount": "92 000 CZK"},
                               "location": {"reverse_geocode": {"city": "Cestlice", "city_page": {"display_name": "Cestlice, Hlavní Město Praha, Czech Republic"}}},
                               "custom_sub_titles_with_rendering_flags": [{"subtitle": "150K km"}]}]}}
    a, b = [c.finish(FX0) for c in foreign.parse_facebook([payload], "LV")]
    assert (a.make, a.family, a.year, a.km, a.price, a.country) == ("subaru", "outback", 2005, 385000, 1700, "LV"), a
    assert (b.make, b.family, b.km, b.currency, b.country, b.fuel) == ("skoda", "octavia", 150000, "CZK", "CZ", "diesel")


def test_normalize_families():
    cases = [("bmw", "320d", "3-series"), ("bmw", "Řada 5", "5-series"), ("bmw", "seria 1", "1-series"),
             ("bmw", "X5", "x5"), ("mercedes", "C200", "c-class"), ("mercedes", "Třída E", "e-class"),
             ("mercedes", "klasa a", "a-class"), ("mercedes", "ML320", "ml"), ("mercedes", "GLK 220", "glk"),
             ("volkswagen", "Golf 6", "golf"), ("volkswagen", "Passat (B7)", "passat"), ("volkswagen", "Up!", "up"),
             ("volkswagen", "Golf Plus", "golf-plus"), ("toyota", "RAV 4", "rav4"), ("toyota", "Corolla Verso", "corolla-verso"),
             ("honda", "CR-V", "cr-v"), ("mazda", "6", "6"), ("mazda", "CX-5", "cx-5"), ("skoda", "Octavia Combi", "octavia"),
             ("audi", "A4 Allroad", "a4"), ("volvo", "XC90", "xc90"), ("volvo", "V70", "v70"), ("ford", "Grand C-Max", "c-max"),
             ("kia", "Cee'd", "ceed"), ("hyundai", "i30", "i30"), ("peugeot", "308", "308"), ("lexus", "IS 220d", "is")]
    for make, txt, want in cases:
        got = N.canon_family(make, txt)
        assert got == want, (make, txt, got, want)
    assert N.canon_make("Mercedes-Benz") == "mercedes" and N.canon_make("Škoda") == "skoda" and N.canon_make("VW") == "volkswagen"
    assert N.parse_km("303 tūkst.") == 303000 and N.parse_km("385 тыс. км") == 385000 and N.parse_km("150K km") == 150000
    assert N.parse_price("6,899 €") == 6899 and N.parse_price("  84 000 Kč") == 84000 and N.parse_price("€9500 inc. VAT") == 9500


if __name__ == "__main__":
    fails = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("ok  ", name)
            except Exception as e:  # noqa
                fails += 1
                print("FAIL", name, repr(e))
    sys.exit(1 if fails else 0)
