"""Turn messy listing text from 8 different sites into one canonical shape.

make  -> "volkswagen", "mercedes", "bmw", ...
family-> "golf", "3-series", "c-class", "up", ...
fuel  -> petrol | diesel | hybrid | phev | electric | lpg | cng
gearbox -> manual | auto
"""
from __future__ import annotations

import re
import unicodedata
from typing import Optional, Tuple

# ---------------------------------------------------------------- text utils


_SPECIAL = str.maketrans({"ł": "l", "Ł": "L", "ø": "o", "Ø": "O", "ß": "ss", "đ": "d", "æ": "ae", "œ": "oe"})


def strip_accents(s: str) -> str:
    s = unicodedata.normalize("NFKD", s.translate(_SPECIAL))
    return "".join(c for c in s if not unicodedata.combining(c))


def norm(s: Optional[str]) -> str:
    """lowercase, no diacritics, punctuation -> spaces, single spaced."""
    if not s:
        return ""
    s = strip_accents(str(s)).lower()
    s = s.replace("!", " ").replace("'", "")
    s = re.sub(r"[^a-z0-9а-яё\-\.\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def parse_int(s) -> Optional[int]:
    if s is None:
        return None
    if isinstance(s, (int, float)):
        return int(s)
    digits = re.sub(r"[^\d]", "", str(s))
    return int(digits) if digits else None


def parse_price(s) -> Optional[float]:
    """'6,899 €' / '84 000 Kč' / '2 600 €' / '19900' -> float."""
    if s is None:
        return None
    if isinstance(s, (int, float)):
        return float(s)
    t = str(s).replace("\xa0", " ")
    m = re.search(r"\d[\d\s.,]*", t)
    if not m:
        return None
    num = m.group(0).strip()
    # thousands separators: "6,899" "6.899" "6 899"; decimals are rare for these prices
    num = re.sub(r"[\s,.](?=\d{3}(\D|$))", "", num)
    num = num.replace(",", ".").replace(" ", "")
    try:
        return float(num)
    except ValueError:
        return None


def parse_km(s) -> Optional[int]:
    """'303 tūkst.' / '216,526 km' / '150K km' / '150 тыс. км' / '79 277 km'."""
    if s is None:
        return None
    if isinstance(s, (int, float)):
        return int(s)
    t = strip_accents(str(s)).lower().replace("\xa0", " ")
    m = re.search(r"(\d[\d\s.,]*)\s*(k|tukst|tys|tis|tuh|тыс|thousand|tkm)?", t)
    if not m:
        return None
    num = re.sub(r"[^\d.,]", "", m.group(1))
    mult = 1000 if (m.group(2) or "тыс" in t or "tukst" in t) else 1
    if mult == 1000:
        num = num.replace(",", ".")
        try:
            return int(float(num) * 1000)
        except ValueError:
            return None
    v = parse_int(num)
    if v is not None and v < 1000 and ("km" in t or "км" in t) and "k" in t.split("km")[0][-2:]:
        v *= 1000
    return v


# ---------------------------------------------------------------- makes

MAKE_ALIASES = {
    "vw": "volkswagen", "volkswagen": "volkswagen", "volkswagen-vw": "volkswagen",
    "mercedes": "mercedes", "mercedes-benz": "mercedes", "mercedesbenz": "mercedes", "mb": "mercedes",
    "mercedes benz": "mercedes", "merc": "mercedes",
    "skoda": "skoda", "bmw": "bmw", "audi": "audi", "toyota": "toyota", "volvo": "volvo",
    "opel": "opel", "vauxhall": "opel", "ford": "ford", "honda": "honda", "mazda": "mazda",
    "nissan": "nissan", "hyundai": "hyundai", "kia": "kia", "renault": "renault",
    "peugeot": "peugeot", "citroen": "citroen", "ds": "citroen", "seat": "seat", "cupra": "cupra",
    "subaru": "subaru", "lexus": "lexus", "mitsubishi": "mitsubishi", "dacia": "dacia",
    "suzuki": "suzuki", "fiat": "fiat", "mini": "mini", "tesla": "tesla", "porsche": "porsche",
    "jaguar": "jaguar", "land rover": "land-rover", "land-rover": "land-rover", "landrover": "land-rover",
    "range rover": "land-rover", "jeep": "jeep", "chevrolet": "chevrolet", "chrysler": "chrysler",
    "dodge": "dodge", "alfa romeo": "alfa-romeo", "alfa-romeo": "alfa-romeo", "alfa": "alfa-romeo",
    "smart": "smart", "ssangyong": "ssangyong", "kgm": "ssangyong", "saab": "saab", "lancia": "lancia",
    "infiniti": "infiniti", "chevy": "chevrolet", "byd": "byd", "mg": "mg", "polestar": "polestar",
}
# longest first so "land rover" wins over "land"
_MAKE_KEYS = sorted(MAKE_ALIASES, key=len, reverse=True)


def canon_make(s: Optional[str]) -> Optional[str]:
    t = norm(s).replace(".", " ").strip()
    if not t:
        return None
    if t in MAKE_ALIASES:
        return MAKE_ALIASES[t]
    for k in _MAKE_KEYS:
        if t == k or t.startswith(k + " ") or t.startswith(k + "-"):
            return MAKE_ALIASES[k]
    return None


MODEL_TO_MAKE = {
    "octavia": "skoda", "fabia": "skoda", "superb": "skoda", "yeti": "skoda", "kodiaq": "skoda", "karoq": "skoda",
    "kamiq": "skoda", "roomster": "skoda", "citigo": "skoda", "enyaq": "skoda",
    "golf": "volkswagen", "passat": "volkswagen", "polo": "volkswagen", "touran": "volkswagen", "tiguan": "volkswagen",
    "sharan": "volkswagen", "touareg": "volkswagen", "caddy": "volkswagen", "transporter": "volkswagen",
    "multivan": "volkswagen", "caravelle": "volkswagen", "arteon": "volkswagen", "jetta": "volkswagen", "scirocco": "volkswagen",
    "leon": "seat", "ibiza": "seat", "alhambra": "seat", "ateca": "seat", "tarraco": "seat",
    "corolla": "toyota", "auris": "toyota", "avensis": "toyota", "yaris": "toyota", "rav4": "toyota", "prius": "toyota",
    "aygo": "toyota", "hilux": "toyota", "mondeo": "ford", "fiesta": "ford", "focus": "ford", "kuga": "ford",
    "galaxy": "ford", "astra": "opel", "insignia": "opel", "corsa": "opel", "zafira": "opel", "vectra": "opel",
    "meriva": "opel", "mokka": "opel", "civic": "honda", "accord": "honda", "qashqai": "nissan", "x-trail": "nissan",
    "xtrail": "nissan", "micra": "nissan", "juke": "nissan", "megane": "renault", "clio": "renault", "scenic": "renault",
    "laguna": "renault", "kangoo": "renault", "captur": "renault", "berlingo": "citroen", "tucson": "hyundai",
    "ix35": "hyundai", "i30": "hyundai", "ceed": "kia", "sportage": "kia", "sorento": "kia", "picanto": "kia",
    "outlander": "mitsubishi", "lancer": "mitsubishi", "pajero": "mitsubishi", "forester": "subaru", "outback": "subaru",
    "impreza": "subaru", "duster": "dacia", "logan": "dacia", "sandero": "dacia", "xc90": "volvo", "xc60": "volvo",
    "xc70": "volvo", "v70": "volvo", "v60": "volvo", "v40": "volvo", "v50": "volvo", "s60": "volvo", "s80": "volvo",
}


def guess_make_from_model(text: str) -> Tuple[Optional[str], str]:
    t = norm(text)
    for w in t.split()[:5]:
        w2 = w.strip("-.")
        if w2 in MODEL_TO_MAKE:
            return MODEL_TO_MAKE[w2], t[t.index(w):]
    return None, t


def find_make_in_text(text: str) -> Tuple[Optional[str], str]:
    """Find a make anywhere near the start of free text. Returns (make, rest_after_make)."""
    t = " " + norm(text) + " "
    best = None
    for k in _MAKE_KEYS:
        m = re.search(r"[\s(]" + re.escape(k) + r"[\s\-]", t)
        if m and (best is None or m.start() < best[0]):
            best = (m.start(), k, m.end())
    if not best or best[0] > 40:
        return guess_make_from_model(text)
    return MAKE_ALIASES[best[1]], t[best[2]:].strip()


# ---------------------------------------------------------------- families

# Per make: ordered list of (family_key, [regex]) applied to the normalized model text.
# Anything not listed falls back to the first word of the model text.
FAMILY_RULES = {
    "volkswagen": [
        ("golf-plus", [r"golf\s*plus"]), ("golf-sportsvan", [r"sportsvan"]),
        ("golf", [r"\bgolf\b"]), ("passat-cc", [r"passat\s*cc", r"^cc\b"]),
        ("passat", [r"\bpassat\b"]), ("up", [r"^e?-?\s*up\b", r"\bup\b"]),
        ("beetle", [r"beetle", r"kafer", r"brouk"]),
        ("transporter", [r"\bt[3-7]\b", r"transporter", r"caravelle", r"multivan"]),
        ("id3", [r"\bid\.?\s*3\b"]), ("id4", [r"\bid\.?\s*4\b"]),
        ("t-roc", [r"t\s*-?\s*roc"]), ("t-cross", [r"t\s*-?\s*cross"]),
    ],
    "skoda": [("octavia", [r"octavia"]), ("fabia", [r"fabia"]), ("superb", [r"superb"]),
              ("citigo", [r"citigo"]), ("roomster", [r"roomster"])],
    "seat": [("leon", [r"leon"]), ("ibiza", [r"ibiza"]), ("mii", [r"\bmii\b"])],
    "audi": [
        ("rs", [r"^rs\s*\d", r"\brs\s*q?\d\b"]), ("s-models", [r"^s\d\b"]),
        ("a1", [r"\ba\s*1\b"]), ("a3", [r"\ba\s*3\b"]), ("a4", [r"\ba\s*4\b"]), ("a5", [r"\ba\s*5\b"]),
        ("a6", [r"\ba\s*6\b"]), ("a7", [r"\ba\s*7\b"]), ("a8", [r"\ba\s*8\b"]),
        ("q2", [r"\bq\s*2\b"]), ("q3", [r"\bq\s*3\b"]), ("q5", [r"\bq\s*5\b"]), ("q7", [r"\bq\s*7\b"]),
        ("q8", [r"\bq\s*8\b"]), ("tt", [r"\btt\b"]), ("e-tron", [r"e\s*-?\s*tron"]),
    ],
    "bmw": [
        ("i3", [r"\bi\s*3\b"]), ("i4", [r"\bi\s*4\b"]), ("ix", [r"\bix\d?\b"]),
        ("m-models", [r"^m\s*\d\b", r"\bm[2-8]\b"]),
        ("x1", [r"\bx\s*1\b"]), ("x2", [r"\bx\s*2\b"]), ("x3", [r"\bx\s*3\b"]), ("x4", [r"\bx\s*4\b"]),
        ("x5", [r"\bx\s*5\b"]), ("x6", [r"\bx\s*6\b"]), ("x7", [r"\bx\s*7\b"]),
        ("1-series", [r"\b1\d\d[a-z]{0,3}\b", r"\b1\s*(er|series|seria|serie|serija|rada)\b", r"(seria|rada|serie|serija)\s*-?\s*1\b"]),
        ("2-series", [r"\b2\d\d[a-z]{0,3}\b", r"\b2\s*(er|series|seria|serie|serija|rada)\b", r"(seria|rada|serie|serija)\s*-?\s*2\b"]),
        ("3-series", [r"\b3\d\d[a-z]{0,3}\b", r"\b3\s*(er|series|seria|serie|serija|rada)\b", r"(seria|rada|serie|serija)\s*-?\s*3\b", r"\bgt\s*3"]),
        ("4-series", [r"\b4\d\d[a-z]{0,3}\b", r"\b4\s*(er|series|seria|serie|serija|rada)\b", r"(seria|rada|serie|serija)\s*-?\s*4\b"]),
        ("5-series", [r"\b5\d\d[a-z]{0,3}\b", r"\b5\s*(er|series|seria|serie|serija|rada)\b", r"(seria|rada|serie|serija)\s*-?\s*5\b"]),
        ("6-series", [r"\b6\d\d[a-z]{0,3}\b", r"\b6\s*(er|series|seria|serie|serija|rada)\b", r"(seria|rada|serie|serija)\s*-?\s*6\b"]),
        ("7-series", [r"\b7\d\d[a-z]{0,3}\b", r"\b7\s*(er|series|seria|serie|serija|rada)\b", r"(seria|rada|serie|serija)\s*-?\s*7\b"]),
    ],
    "mercedes": [
        ("sprinter", [r"sprinter"]), ("vito", [r"\bvito\b", r"viano"]), ("v-class", [r"^v\s*\d{3}\b", r"\bv\s*-?\s*(klase|class|klasse|trida|klasa)"]),
        ("cla", [r"\bcla(?!ss)\s*\d{0,3}[a-z]{0,4}\b"]), ("cls", [r"\bcls\s*\d{0,3}[a-z]{0,4}\b"]), ("clk", [r"\bclk\s*\d{0,3}[a-z]{0,4}\b"]), ("slk", [r"\bsl[kc]\s*\d{0,3}[a-z]{0,4}\b"]),
        ("gla", [r"\bgla\s*\d{0,3}[a-z]{0,4}\b"]), ("glb", [r"\bglb\s*\d{0,3}[a-z]{0,4}\b"]), ("glc", [r"\bglc\s*\d{0,3}[a-z]{0,4}\b"]), ("glk", [r"\bglk\s*\d{0,3}[a-z]{0,4}\b"]),
        ("gle", [r"\bgle\s*\d{0,3}[a-z]{0,4}\b"]), ("gls", [r"\bgls\s*\d{0,3}[a-z]{0,4}\b"]), ("gl", [r"\bgl\s*\d{0,3}[a-z]{0,4}\b"]), ("ml", [r"\bml\s*\d{0,3}[a-z]{0,4}\b", r"\bm\s*-?\s*(klase|class|klasse|trida|klasa)"]),
        ("sl", [r"\bsl\s*\d{0,3}\b"]), ("g-class", [r"^g\s*\d{2,3}", r"\bg\s*-?\s*(klase|class|klasse|trida|klasa)"]),
        ("a-class", [r"^a\s*\d{2,3}", r"\ba\s*-?\s*(klase|class|klasse|trida|klasa)\b", r"(trida|klasa|klase)\s*a\b"]),
        ("b-class", [r"^b\s*\d{2,3}", r"\bb\s*-?\s*(klase|class|klasse|trida|klasa)\b", r"(trida|klasa|klase)\s*b\b"]),
        ("c-class", [r"^c\s*\d{2,3}", r"\bc\s*-?\s*(klase|class|klasse|trida|klasa)\b", r"(trida|klasa|klase)\s*c\b"]),
        ("e-class", [r"^e\s*\d{2,3}", r"\be\s*-?\s*(klase|class|klasse|trida|klasa)\b", r"(trida|klasa|klase)\s*e\b"]),
        ("s-class", [r"^s\s*\d{2,3}", r"\bs\s*-?\s*(klase|class|klasse|trida|klasa)\b", r"(trida|klasa|klase)\s*s\b"]),
    ],
    "toyota": [
        ("land-cruiser", [r"land\s*-?\s*cruiser"]), ("corolla-verso", [r"corolla\s*verso"]),
        ("corolla", [r"corolla"]), ("auris", [r"auris"]), ("avensis", [r"avensis"]),
        ("yaris", [r"yaris"]), ("rav4", [r"rav\s*-?\s*4"]), ("prius", [r"prius"]), ("aygo", [r"aygo"]),
        ("c-hr", [r"c\s*-?\s*hr\b"]), ("verso", [r"verso"]), ("hilux", [r"hilux"]),
    ],
    "honda": [("cr-v", [r"cr\s*-?\s*v\b"]), ("hr-v", [r"hr\s*-?\s*v\b"]), ("civic", [r"civic"]),
              ("accord", [r"accord"]), ("jazz", [r"jazz", r"\bfit\b"])],
    "mazda": [("cx-3", [r"cx\s*-?\s*3"]), ("cx-30", [r"cx\s*-?\s*30"]), ("cx-5", [r"cx\s*-?\s*5"]),
              ("cx-7", [r"cx\s*-?\s*7"]), ("mx-5", [r"mx\s*-?\s*5"]),
              ("2", [r"^(mazda\s*)?2\b"]), ("3", [r"^(mazda\s*)?3\b"]), ("5", [r"^(mazda\s*)?5\b"]),
              ("6", [r"^(mazda\s*)?6\b"])],
    "ford": [("c-max", [r"c\s*-?\s*max"]), ("s-max", [r"s\s*-?\s*max"]), ("b-max", [r"b\s*-?\s*max"]),
             ("focus", [r"focus"]), ("mondeo", [r"mondeo"]), ("fiesta", [r"fiesta"]),
             ("galaxy", [r"galaxy"]), ("kuga", [r"kuga"]), ("transit", [r"transit"])],
    "opel": [("astra", [r"astra"]), ("insignia", [r"insignia"]), ("corsa", [r"corsa"]),
             ("zafira", [r"zafira"]), ("vectra", [r"vectra"]), ("meriva", [r"meriva"]),
             ("mokka", [r"mokka"]), ("vivaro", [r"vivaro"])],
    "nissan": [("x-trail", [r"x\s*-?\s*trail"]), ("qashqai", [r"qashqai"]), ("note", [r"\bnote\b"]),
               ("micra", [r"micra"]), ("leaf", [r"\bleaf\b"]), ("juke", [r"juke"]), ("navara", [r"navara"])],
    "hyundai": [("i10", [r"\bi\s*10\b"]), ("i20", [r"\bi\s*20\b"]), ("i30", [r"\bi\s*30\b"]),
                ("i40", [r"\bi\s*40\b"]), ("ix35", [r"ix\s*35"]), ("ix20", [r"ix\s*20"]),
                ("tucson", [r"tucson"]), ("santa-fe", [r"santa\s*-?\s*fe"]), ("kona", [r"kona"])],
    "kia": [("ceed", [r"cee\s*-?\s*d", r"\bceed\b", r"pro\s*-?\s*cee"]), ("sportage", [r"sportage"]),
            ("rio", [r"\brio\b"]), ("picanto", [r"picanto"]), ("sorento", [r"sorento"]),
            ("niro", [r"niro"]), ("venga", [r"venga"]), ("optima", [r"optima"])],
    "renault": [("megane", [r"megane"]), ("clio", [r"clio"]), ("scenic", [r"scenic"]),
                ("laguna", [r"laguna"]), ("kangoo", [r"kangoo"]), ("captur", [r"captur"]), ("zoe", [r"\bzoe\b"])],
    "peugeot": [], "citroen": [("c4-picasso", [r"c4\s*(grand\s*)?picasso", r"c4\s*spacetourer"]),
                               ("berlingo", [r"berlingo"])],
    "volvo": [("xc90", [r"xc\s*-?\s*90"]), ("xc70", [r"xc\s*-?\s*70"]), ("xc60", [r"xc\s*-?\s*60"]),
              ("xc40", [r"xc\s*-?\s*40"]), ("v40", [r"\bv\s*40\b"]), ("v50", [r"\bv\s*50\b"]),
              ("v60", [r"\bv\s*60\b"]), ("v70", [r"\bv\s*70\b"]), ("v90", [r"\bv\s*90\b"]),
              ("s40", [r"\bs\s*40\b"]), ("s60", [r"\bs\s*60\b"]), ("s80", [r"\bs\s*80\b"]), ("s90", [r"\bs\s*90\b"]),
              ("c30", [r"\bc\s*30\b"])],
    "subaru": [("forester", [r"forester"]), ("outback", [r"outback"]), ("legacy", [r"legacy"]),
               ("impreza", [r"impreza"]), ("xv", [r"\bxv\b", r"crosstrek"])],
    "lexus": [("is", [r"^is\b", r"\bis\s*\d{3}"]), ("rx", [r"^rx\b", r"\brx\s*\d{3}"]),
              ("nx", [r"^nx\b", r"\bnx\s*\d{3}"]), ("gs", [r"^gs\b", r"\bgs\s*\d{3}"]), ("ct", [r"^ct\b", r"ct\s*200"])],
    "mitsubishi": [("outlander", [r"outlander"]), ("lancer", [r"lancer"]), ("asx", [r"\basx\b"]),
                   ("pajero", [r"pajero"]), ("colt", [r"colt"]), ("l200", [r"l\s*200"])],
    "land-rover": [("range-rover-sport", [r"range\s*rover\s*sport", r"^sport\b"]),
                   ("range-rover-evoque", [r"evoque"]), ("range-rover-velar", [r"velar"]),
                   ("range-rover", [r"range\s*rover", r"^rover\b"]), ("discovery", [r"discovery"]),
                   ("freelander", [r"freelander"]), ("defender", [r"defender"])],
    "tesla": [("model-3", [r"model\s*3", r"^3\b"]), ("model-s", [r"model\s*s", r"^s\b"]),
              ("model-y", [r"model\s*y", r"^y\b"]), ("model-x", [r"model\s*x", r"^x\b"])],
    "mini": [("countryman", [r"countryman"]), ("clubman", [r"clubman"]), ("cooper", [r"cooper", r"\bone\b", r"hatch", r"^mini\b"])],
    "fiat": [("500", [r"^500\b(?!\s*x|l)"]), ("500x", [r"500\s*x"]), ("500l", [r"500\s*l"]),
             ("punto", [r"punto"]), ("doblo", [r"doblo"]), ("panda", [r"panda"]), ("ducato", [r"ducato"])],
    "dacia": [("duster", [r"duster"]), ("logan", [r"logan"]), ("sandero", [r"sandero"]), ("dokker", [r"dokker"])],
    "suzuki": [("vitara", [r"vitara"]), ("swift", [r"swift"]), ("sx4", [r"sx\s*-?\s*4"]), ("jimny", [r"jimny"])],
}

# words that are never a model family
_STOP = {"new", "nauja", "jauna", "used", "auto", "car", "the", "a", "el", "e", "sale", "pardod", "prodam"}


def canon_family(make: Optional[str], model_text: Optional[str]) -> Optional[str]:
    if not make:
        return None
    t = norm(model_text)
    # drop the make name if repeated inside the model text
    for k, v in MAKE_ALIASES.items():
        if v == make and t.startswith(k + " "):
            t = t[len(k) + 1:]
    t = t.strip(" -.")
    if not t:
        return None
    for fam, pats in FAMILY_RULES.get(make, []):
        for p in pats:
            if re.search(p, t):
                return fam
    first = re.split(r"[\s(]", t)[0].strip("-.")
    if first in _STOP or not first:
        return None
    # "golf-4" style -> "golf"
    first = re.sub(r"-\d+$", "", first)
    if re.fullmatch(r"\d\.\d", first):  # engine size, not a model
        return None
    return first[:20]


FAMILY_LABELS = {
    "3-series": "3 Series", "1-series": "1 Series", "2-series": "2 Series", "4-series": "4 Series",
    "5-series": "5 Series", "6-series": "6 Series", "7-series": "7 Series", "m-models": "M models",
    "a-class": "A-Class", "b-class": "B-Class", "c-class": "C-Class", "e-class": "E-Class",
    "s-class": "S-Class", "g-class": "G-Class", "v-class": "V-Class", "ml": "ML", "up": "up!",
    "rav4": "RAV4", "cr-v": "CR-V", "hr-v": "HR-V", "cx-5": "CX-5", "x-trail": "X-Trail",
    "c-max": "C-Max", "s-max": "S-Max", "id3": "ID.3", "id4": "ID.4", "s-models": "S models",
    "rs": "RS models", "land-cruiser": "Land Cruiser", "model-3": "Model 3", "model-s": "Model S",
    "model-y": "Model Y", "range-rover": "Range Rover", "range-rover-sport": "Range Rover Sport",
    "golf-plus": "Golf Plus", "passat-cc": "Passat CC", "c4-picasso": "C4 Picasso",
    "i10": "i10", "i20": "i20", "i30": "i30", "i40": "i40", "ix35": "ix35", "ix20": "ix20", "i3": "i3", "i4": "i4",
    "ix": "iX", "e-tron": "e-tron", "mii": "Mii", "t-roc": "T-Roc", "t-cross": "T-Cross", "c-hr": "C-HR",
    "golf-sportsvan": "Golf Sportsvan", "corolla-verso": "Corolla Verso", "santa-fe": "Santa Fe",
}
MAKE_LABELS = {"volkswagen": "VW", "mercedes": "Mercedes", "bmw": "BMW", "land-rover": "Land Rover",
               "alfa-romeo": "Alfa Romeo", "mini": "MINI", "ds": "DS"}


def label(make: Optional[str], family: Optional[str]) -> str:
    m = MAKE_LABELS.get(make or "", (make or "?").replace("-", " ").title())
    if not family:
        return m
    f = FAMILY_LABELS.get(family)
    if not f:
        f = family.upper() if (len(family) <= 3 or re.search(r"\d", family)) else family.replace("-", " ").title()
    return f"{m} {f}"


# ---------------------------------------------------------------- fuel / gearbox

FUEL_WORDS = [
    ("phev", [r"plug\s*-?\s*in", r"phev", r"\be-?hybrid\b.*plug", r"pievienojam"]),
    ("hybrid", [r"hybrid", r"hibrid", r"hybryd", r"гибрид", r"\bhev\b"]),
    ("electric", [r"electric", r"elektr", r"\bev\b", r"электро", r"elektryczn", r"\bbev\b"]),
    ("cng", [r"\bcng\b"]),
    ("lpg", [r"\blpg\b", r"gaze", r"\bgas\b", r"\bgaz\b", r"autogas", r"газ", r"\bdujos\b", r"gaas"]),
    ("diesel", [r"diesel", r"dizel", r"dyzel", r"nafta", r"дизел", r"\btdi\b", r"\bcdi\b", r"\bhdi\b",
                r"\bdci\b", r"\bcdti\b", r"\bcrdi\b", r"\bd-?4d\b", r"\btdci\b", r"\bjtd", r"multijet", r"\bd\b"]),
    ("petrol", [r"petrol", r"benzin", r"benzyn", r"бензин", r"gasoline", r"\bbensiin\b", r"\btsi\b", r"\btfsi\b",
                r"\bmpi\b", r"\bfsi\b", r"vtec", r"ecoboost", r"puretech", r"\btce\b", r"\bp\b", r"\bb\b"]),
]


def canon_fuel(s: Optional[str]) -> Optional[str]:
    t = norm(s)
    if not t:
        return None
    short = len(t) <= 3  # single-letter codes (auto24 "D"/"P", ss.lv "2.0D") only for short input
    for fuel, pats in FUEL_WORDS:
        for p in pats:
            if not short and re.fullmatch(r"\\b\w\\b", p):
                continue
            if re.search(p, t):
                return fuel
    return None


def canon_gearbox(s: Optional[str]) -> Optional[str]:
    t = norm(s)
    if not t:
        return None
    if len(t) <= 2:
        return {"a": "auto", "m": "manual"}.get(t)
    if re.search(r"auto|automat|dsg|cvt|tiptronic|steptronic|s-?tronic|automatyczn|automatin|automaatn|semi|robot|автомат", t):
        return "auto"
    if re.search(r"manu|mehan|mechan|schalt|rankin|\bman\b|механ", t):
        return "manual"
    return None


def engine_from_text(s: Optional[str]) -> Optional[float]:
    """'1.9 TDI' / '1,6 l.' / '999 cm3' / '2.0D' -> litres."""
    if not s:
        return None
    t = str(s).lower().replace(",", ".")
    m = re.search(r"\b(\d{3,4})\s*(cm3|ccm|cc|cm³|см)", t)
    if m:
        v = int(m.group(1)) / 1000
        return round(v, 1)
    m = re.search(r"(?<![\d.])([0-6]\.\d)(?!\d)", t)
    if m:
        v = float(m.group(1))
        if 0.6 <= v <= 6.8:
            return v
    return None


def power_kw_from_text(s: Optional[str]) -> Optional[int]:
    if not s:
        return None
    t = str(s).lower()
    m = re.search(r"(\d{2,3})\s*kw", t)
    if m:
        return int(m.group(1))
    m = re.search(r"(\d{2,3})\s*(km|hp|ps|zs|к\.?с)\b", t)
    if m:
        return int(int(m.group(1)) * 0.7355)
    return None


def year_from_text(s: Optional[str]) -> Optional[int]:
    if not s:
        return None
    for m in re.finditer(r"(?<!\d)(19[89]\d|20[0-3]\d)(?!\d)", str(s)):
        y = int(m.group(1))
        if 1985 <= y <= 2027:
            return y
    return None


def km_from_text(s: Optional[str]) -> Optional[int]:
    """Find mileage inside free text: 'najeto 116800km', 'przebieg 150 000 km', '150 tkm'."""
    if not s:
        return None
    t = strip_accents(str(s)).lower().replace("\xa0", " ")
    m = re.search(r"(\d{1,3}(?:[ .,]?\d{3})+|\d{4,6})\s*(km|км)\b", t)
    if m:
        v = parse_int(m.group(1))
        if v and 500 <= v <= 900000:
            return v
    m = re.search(r"(\d{2,3})\s*(tkm|tis\.?\s*km|tys\.?\s*km|tukst\.?\s*km|k\s*km|тыс\.?\s*км)", t)
    if m:
        return int(m.group(1)) * 1000
    return None
