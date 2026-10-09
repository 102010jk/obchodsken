#!/usr/bin/env python3
"""Hromadný sběr: Rohlík.cz, kategorie 300106000 (Trvanlivé) – všechny stránky a všechny produkty.

Výstup: data/foods/raw/04-rohlik-trvanlive.jsonl (přepíše se). Spuštění z kteréhokoli adresáře:
    python3 data/foods/harvest/04-rohlik-trvanlive.py

Pravidla: jen data z API Rohlíku (name, brand, textualAmount, slug, images), žádné doplňování.
Šetrnost: max 1 požadavek za sekundu, při 429/5xx exponenciální čekání, po 5 neúspěších přeskočit dávku.
Při 403 se script ukončí bez zápisu (blokaci neobcházíme).
"""
import json
import os
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "data/foods/raw/04-rohlik-trvanlive.jsonl"

STORE = "Rohlík"
CATEGORY_ID = 300106000
PAGE_SIZE = 100
DETAIL_BATCH = 50
MIN_INTERVAL = 1.0          # sekund mezi požadavky (celkem, sdíleno se všemi dotazy)
MAX_RETRIES = 5
MAX_PAGES = 60
UA = "Mozilla/5.0"

API = "https://www.rohlik.cz/api/v1"
PRODUCT_URL = "https://www.rohlik.cz/{id}-{slug}"

# Podkategorie Rohlíku (mainCategoryId) -> kategorie FORMAT.md.
# Slané snacky, sladkosti, žvýkačky, lízátka, oplatky, sušenky, čokolády -> SLADKOSTI ("Sladkosti a snacky").
# Vše ostatní (těstoviny, rýže, mouka, konzervy, oleje, koření, omáčky, kaše, polévky...) -> TRVANLIVE.
SWEETS_SUBCATS = {
    300115571, 300117825, 300117819, 300123366, 300123892, 300115575, 300123405, 300115609,
    300124852, 300123893, 300106149, 300117822, 300115141, 300115727, 300123412, 300123416,
    300115543, 300115735, 300114465, 300124855, 300115573, 300115321, 300115133, 300123419,
    300115733, 300124858, 300124856, 300123407, 300106148, 300115577, 300115545, 300121346,
    300123418, 300124014, 300121352, 300115155, 300106121, 300123861, 300115743, 300121355,
    300123414, 300123410, 300123844, 300115737, 300115745, 300101044, 300101047, 300116663,
    300121345, 300123362, 300121351, 300121349, 300115539, 300101032, 300123894, 300123394,
    300115123, 300115739, 300116523, 300121338, 300116529, 300121727, 300123404, 300115623,
    300124015, 300122483, 300114669, 300122637, 300115125, 300123545, 300112943, 300123411,
    300123392, 300121357, 300115701, 300112945, 300123409,
}
TRVANLIVE_SUBCATS = {
    300123580, 300106028, 300124853, 300121503, 300123401, 300106040, 300123579, 300123402,
    300123922, 300123927, 300106108, 300123576, 300123496, 300123541, 300106043, 300123554,
    300106029, 300114639, 300106006, 300115811, 300115315, 300123448, 300123487, 300123540,
    300106007, 300106115, 300123923, 300106109, 300115127, 300121957, 300123926, 300123449,
    300123484, 300123574, 300116915, 300123578, 300123468, 300123442, 300106022, 300123481,
    300118856, 300123483, 300106112, 300123477, 300123328, 300123490, 300124029, 300123536,
    300123538, 300115151, 300123423, 300115813, 300106113, 300123485, 300114905, 300115129,
    300118859, 300123403, 300115801, 300115317, 300106038, 300123456, 300106114, 300123504,
    300123451, 300123928, 300115831, 300124670, 300115097, 300118853, 300116885, 300123519,
    300119666, 300115149, 300121418, 300123462, 300118862, 300121845, 300123444, 300106037,
    300123420, 300123913, 300106035, 300106012, 300119676, 300106019, 300115069, 300119681,
    300123517, 300123575, 300101036, 300106106, 300123494, 300123430, 300123429, 300123868,
    300123863, 300123463, 300115153, 300123520, 300123426, 300123866, 300110029, 300118470,
    300115101, 300120449, 300115611, 300115815, 300123450, 300114907, 300118919, 300121988,
    300121986, 300121985, 300123915, 300106042, 300114745, 300106023, 300123577,
}
# Podkategorie, které nejsou potraviny (drogerie, kuchyňské potřeby…). Zatím žádná nalezena.
NONFOOD_SUBCATS = set()


def category_for(sub_id):
    if sub_id in NONFOOD_SUBCATS:
        return None
    if sub_id in SWEETS_SUBCATS:
        return "SLADKOSTI"
    if sub_id not in TRVANLIVE_SUBCATS:
        print(f"  pozor: neznámá podkategorie {sub_id}, zařazeno do TRVANLIVE", file=sys.stderr)
    return "TRVANLIVE"


_last_request = 0.0
stats = {"requests": 0, "retries": 0, "skipped_batches": 0}


class Blocked(Exception):
    pass


def get_json(url):
    """GET s limitem 1 req/s a retry při 429/5xx/síťové chybě. Vrací None po 5 neúspěších."""
    global _last_request
    for attempt in range(MAX_RETRIES):
        wait = MIN_INTERVAL - (time.monotonic() - _last_request)
        if wait > 0:
            time.sleep(wait)
        _last_request = time.monotonic()
        stats["requests"] += 1
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 403:
                raise Blocked(url)
            if e.code == 429 or e.code >= 500:
                pass  # zkusíme znovu
            else:
                print(f"  HTTP {e.code}, přeskakuji: {url[:90]}", file=sys.stderr)
                return None
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            print(f"  chyba sítě/JSON ({e}), zkusím znovu", file=sys.stderr)
        stats["retries"] += 1
        time.sleep(2 ** attempt)
    return None


def fetch_category_ids():
    ids, seen = [], set()
    for page in range(MAX_PAGES):
        url = f"{API}/categories/normal/{CATEGORY_ID}/products?limit={PAGE_SIZE}"
        if page:
            url += f"&page={page}"
        data = get_json(url)
        if data is None:
            print(f"  stránka {page} se nepodařila, končím výčet", file=sys.stderr)
            break
        page_ids = list(data.get("productIds") or [])
        if not page_ids:
            break
        new = [i for i in page_ids if i not in seen]
        seen.update(new)
        ids.extend(new)
        print(f"  stránka {page}: {len(page_ids)} ID, nových {len(new)}")
        if not new:
            break
    return ids


def fetch_details(ids):
    details = []
    for n in range(0, len(ids), DETAIL_BATCH):
        batch = ids[n:n + DETAIL_BATCH]
        q = "&".join(f"products={i}" for i in batch)
        data = get_json(f"{API}/products?{q}")
        if not isinstance(data, list):
            stats["skipped_batches"] += 1
            print(f"  dávka {n // DETAIL_BATCH} přeskočena", file=sys.stderr)
            continue
        details.extend(data)
    return details


def slugify(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


SIZE_RE = re.compile(r"^\s*(\d+(?:[.,]\d+)?)\s*(g|kg|ml|l|ks)\s*$")


def size_of(text, weighted):
    """Vrací (value, unit) nebo (None, None). Vážené zboží a 'cca' se nepřevádí."""
    if weighted or not text or "cca" in text.lower():
        return None, None
    m = SIZE_RE.match(text.replace("×", "x"))
    if not m:
        return None, None
    v = float(m.group(1).replace(",", "."))
    u = m.group(2)
    if u == "g":
        return round(v / 1000, 6), "kg"
    if u == "kg":
        return v, "kg"
    if u == "ml":
        return round(v / 1000, 6), "l"
    if u == "l":
        return v, "l"
    if u == "ks" and v >= 1 and v == int(v):
        return int(v), "ks"
    return None, None


SLUG_OK = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


def build_record(p):
    if p.get("archived"):
        return None
    name = (p.get("name") or "").strip()
    if not name:
        return None
    sub = p.get("mainCategoryId")
    cat = category_for(sub)
    if cat is None:
        return None
    pid = p["id"]
    slug = p.get("slug") or ""
    if not SLUG_OK.match(slug):
        slug = slugify(name)
    url = PRODUCT_URL.format(id=pid, slug=p.get("slug") or slug)
    rec = {"id": f"rohlik-{pid}-{slug}", "name": name}
    if p.get("brand"):
        rec["brand"] = p["brand"].strip()
    rec["category"] = cat
    sv, su = size_of(p.get("textualAmount"), p.get("weightedItem"))
    if sv is not None:
        rec["size_value"] = sv
        rec["size_unit"] = su
    rec["stores"] = [{"store": STORE, "receipt_name": None, "receipt_name_source": None, "url": url}]
    images = p.get("images") or []
    if images:
        rec["image_url"] = images[0]
    rec["sources"] = [url]
    return rec


def main():
    # Volitelná cache (HARVEST_CACHE=cesta.json): při existenci se nic nestahuje z webu.
    cache = Path(os.environ["HARVEST_CACHE"]) if os.environ.get("HARVEST_CACHE") else None
    if cache and cache.exists():
        saved = json.loads(cache.read_text(encoding="utf-8"))
        ids, details = saved["ids"], saved["details"]
        print(f"načteno z cache {cache}: {len(ids)} ID, {len(details)} detailů")
    else:
        print("1) výčet ID z kategorie", CATEGORY_ID)
        try:
            ids = fetch_category_ids()
            print(f"   celkem ID: {len(ids)}")
            print("2) detaily po dávkách po", DETAIL_BATCH)
            details = fetch_details(ids)
        except Blocked as e:
            print(f"Web vrací 403 ({e}). Končím bez zápisu, blokaci neobcházím.", file=sys.stderr)
            return 2
        if cache:
            cache.write_text(json.dumps({"ids": ids, "details": details}, ensure_ascii=False), encoding="utf-8")

    if os.environ.get("HARVEST_SUBCAT_DUMP"):
        dump = {}
        for p in details:
            d = dump.setdefault(str(p.get("mainCategoryId")), {"count": 0, "samples": []})
            d["count"] += 1
            if len(d["samples"]) < 4:
                d["samples"].append(p.get("name"))
        Path(os.environ["HARVEST_SUBCAT_DUMP"]).write_text(
            json.dumps(dump, ensure_ascii=False, indent=1), encoding="utf-8")

    records, seen_ids, skipped = [], set(), 0
    for p in details:
        rec = build_record(p)
        if rec is None:
            skipped += 1
            continue
        if rec["id"] in seen_ids:
            continue
        seen_ids.add(rec["id"])
        records.append(rec)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUT.with_suffix(".jsonl.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    tmp.replace(OUT)

    print(f"zapsáno záznamů: {len(records)} do {OUT}")
    print(f"vyřazeno (archivované/nepotravinové/prázdné): {skipped}")
    print(f"požadavků: {stats['requests']}, opakovaných: {stats['retries']}, "
          f"přeskočených dávek: {stats['skipped_batches']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
