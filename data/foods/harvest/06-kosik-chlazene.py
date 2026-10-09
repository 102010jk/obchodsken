#!/usr/bin/env python3
"""Hromadný sběr Košík.cz: mléčné a chlazené (vč. vajec, sýrů, jogurtů, másla), maso a ryby,
uzeniny a lahůdky, ovoce a zelenina, pekárna a pečivo.

Postup:
  1) projde strom podkategorií od kořenů přes JSON API (`page/products/flexible`).
     Výpis kategorie = první stránka (`products.items`) + kurzor, který obsahuje ID
     zbývajících produktů (zlib+base64 seznam ID). Součet = `totalCount`.
  2) stáhne detail každého unikátního produktu (`product/<id>`), deduplikace podle ID Košíku.
  3) zapíše data/foods/raw/06-kosik-chlazene.jsonl (přepíše).

Limit: max 1 požadavek za sekundu; 429/5xx a síťové chyby -> exponenciální čekání,
po 5 neúspěšných pokusech se požadavek přeskočí. Běh je deterministický, lze spustit znovu.

Spuštění (z kořene repozitáře):  python3 data/foods/harvest/06-kosik-chlazene.py
"""
import base64
import collections
import json
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import zlib
from pathlib import Path

BASE = "https://www.kosik.cz"
API = BASE + "/api/front/"
UA = "Mozilla/5.0"
STORE = "Košík"

# kořeny: mléčné a chlazené, vejce, maso a ryby, uzeniny a lahůdky, ovoce a zelenina, pekárna a pečivo
ROOT_SLUGS = [
    "c898-mlecne-a-chlazene",
    "c935-vejce-a-drozdi",
    "c960-maso-drubez-a-ryby",
    "c1046-uzeniny-a-lahudky",
    "c985-ovoce-a-zelenina",
    "c1026-pekarna-a-cukrarna",
]
EXCLUDE = {990}  # c990-v-kvetinaci: rostliny, ne potraviny

# mapovací tabulka: podkategorie Košíku (číslo c<id>) -> kategorie FORMAT.md.
# Rozhoduje nejhlubší nalezená podkategorie v cestě ke produktu.
CATEGORY_MAP = {
    898: "MLECNE",
    935: "VEJCE",
    960: "MASO_RYBY",
    1046: "UZENINY",
    985: "OVOCE_ZELENINA",
    1026: "PECIVO",
}

OUT = Path(__file__).resolve().parents[1] / "raw" / "06-kosik-chlazene.jsonl"
MIN_INTERVAL = 1.0   # s mezi požadavky
MAX_TRIES = 5        # pokusů na jeden požadavek

REQUESTS = 0
FAILED = []
_last = 0.0


def log(*args):
    print(time.strftime("%H:%M:%S"), *args, file=sys.stderr, flush=True)


def get_json(path, params=None):
    """GET s limitem 1 req/s. 429/5xx/síťová chyba -> exponenciální čekání. 4xx se nezkouší znovu."""
    global REQUESTS, _last
    url = API + path + ("?" + urllib.parse.urlencode(params) if params else "")
    delay = 2.0
    for attempt in range(1, MAX_TRIES + 1):
        wait = _last + MIN_INTERVAL - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        _last = time.monotonic()
        REQUESTS += 1
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            if e.code != 429 and e.code < 500:
                return None
            reason = f"HTTP {e.code}"
        except (urllib.error.URLError, TimeoutError, ConnectionError, json.JSONDecodeError) as e:
            reason = repr(e)
        log(f"pokus {attempt}/{MAX_TRIES} selhal ({reason}): {url}")
        if attempt < MAX_TRIES:
            time.sleep(delay)
            delay *= 2
    FAILED.append(url)
    return None


def slugify(text):
    text = unicodedata.normalize("NFKD", text.replace("\xa0", " "))
    text = "".join(c for c in text if not unicodedata.combining(c)).lower()
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")


def cursor_ids(cursor):
    """Kurzor = zlib+base64 seznam ID produktů, které ještě nebyly načteny."""
    if not cursor:
        return []
    raw = zlib.decompress(base64.b64decode(cursor + "=" * (-len(cursor) % 4)))
    return [int(x) for x in raw.decode().split(",") if x.strip()]


def cat_id(slug):
    return int(re.match(r"c(\d+)-", slug).group(1))


# produkt id -> (cesta kategorií [id, ...], slug listu, ve kterém byl nalezen)
members = {}
visited = set()


def walk(slug, path):
    cid = cat_id(slug)
    if cid in visited or cid in EXCLUDE:
        return
    visited.add(cid)
    d = get_json("page/products/flexible", {"slug": slug, "limit": 30})
    if d is None:
        log(f"kategorie {slug} přeskočena (chyba)")
        return
    here = path + [cid]
    prods = d.get("products") or {}
    ids = [p["id"] for p in prods.get("items") or []]
    try:
        ids += cursor_ids(prods.get("cursor"))
    except (ValueError, zlib.error) as e:
        log(f"kurzor {slug} nejde dekódovat: {e!r}")
    ids = list(dict.fromkeys(ids))
    total = prods.get("totalCount") or 0
    if len(ids) != total:
        log(f"POZOR {slug}: nalezeno {len(ids)} ID, totalCount={total}")
    for pid in ids:
        members.setdefault(pid, (here, slug))
    log(f"{slug}: produktů {len(ids)}, podkategorií {len(d.get('subCategories') or [])}")
    for sub in d.get("subCategories") or []:
        walk(sub["url"].strip("/"), here)


def category_of(path):
    for cid in reversed(path):
        if cid in CATEGORY_MAP:
            return CATEGORY_MAP[cid]
    return None


UNITS = {"g": ("kg", 0.001), "kg": ("kg", 1.0), "ml": ("l", 0.001), "l": ("l", 1.0), "ks": ("ks", 1.0)}


def size_of(pq):
    """Velikost balení -> (size_value, size_unit). Vícebalení s prefixem a neznámé jednotky vynechá."""
    if not pq or pq.get("prefix") or not pq.get("value") or pq.get("unit") not in UNITS:
        return None, None
    unit, mult = UNITS[pq["unit"]]
    value = round(pq["value"] * mult, 4)
    return (int(value) if float(value).is_integer() else value), unit


def ean_ok(code):
    if not re.fullmatch(r"\d{8}|\d{13}", code):
        return False
    digits = [int(c) for c in code]
    body, check = digits[:-1], digits[-1]
    s = sum(x * (3 if (len(body) - i) % 2 == 1 else 1) for i, x in enumerate(body))
    return (10 - s % 10) % 10 == check


def eans_of(product):
    """EAN jen z parametrů/údajů dodavatele u produktu, a jen pokud má správnou kontrolní číslici."""
    det = product.get("detail") or {}
    pairs = []
    for group in det.get("parameterGroups") or []:
        for item in group.get("items") or []:
            pairs.append((str(item.get("title", "")), str(item.get("value", ""))))
    for info in det.get("supplierInfo") or []:
        pairs.append((str(info.get("title", "")), str(info.get("value", ""))))
    found = []
    for title, value in pairs:
        if re.search(r"ean|gtin|čárov|carov", title, re.I):
            for num in re.findall(r"\d{8,13}", value):
                if ean_ok(num) and num not in found:
                    found.append(num)
    return found


def record(pid, product, leaf_slug, category):
    name = product["name"].replace("\xa0", " ").strip()
    size_value, size_unit = size_of(product.get("productQuantity"))
    rec = {"id": f"kosik-{pid}-{slugify(name)[:90].strip('-')}", "name": name}
    brand = (product.get("brand") or {}).get("name")
    if brand:
        rec["brand"] = brand
    rec["category"] = category
    if size_value is not None:
        rec["size_value"], rec["size_unit"] = size_value, size_unit
    eans = eans_of(product)
    if eans:
        rec["eans"] = eans
    rec["stores"] = [{"store": STORE, "receipt_name": None, "receipt_name_source": None,
                      "url": BASE + product["url"]}]
    if product.get("image"):
        rec["image_url"] = product["image"].replace("WIDTHxHEIGHT", "500x500")
    rec["sources"] = [f"{BASE}/{leaf_slug}"]
    return rec


def main():
    for slug in ROOT_SLUGS:
        walk(slug, [])
    log(f"strom hotov: kategorií {len(visited)}, unikátních produktů {len(members)}, požadavků {REQUESTS}")

    records, skipped = [], collections.Counter()
    for n, pid in enumerate(members, 1):
        path, leaf_slug = members[pid]
        category = category_of(path)
        if category is None:
            skipped["bez kategorie"] += 1
            continue
        try:
            d = get_json(f"product/{pid}")
        except Exception as e:  # neočekávané chyby nesmí shodit celý běh
            log(f"produkt {pid}: {e!r}")
            d = None
        product = (d or {}).get("product")
        if not product:
            skipped["detail nedostupný"] += 1
            continue
        det = product.get("detail") or {}
        if (product.get("vendorId") != 1 or product.get("marketplaceVendor")
                or product.get("blacklisted") or det.get("unlisted")):
            skipped["marketplace/nedostupné"] += 1
            continue
        records.append(record(pid, product, leaf_slug, category))
        if n % 100 == 0:
            log(f"detaily {n}/{len(members)}, požadavků {REQUESTS}, záznamů {len(records)}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    log(f"zapsáno {len(records)} záznamů do {OUT}")
    log(f"přeskočeno: {dict(skipped)}")
    log(f"požadavků celkem: {REQUESTS}, neúspěšných URL: {len(FAILED)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
