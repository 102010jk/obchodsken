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
    300101025, 300101032, 300101044, 300101047, 300106015, 300106121, 300106148, 300106149,
    300106152, 300110028, 300112917, 300112943, 300112945, 300112947, 300114465, 300114669,
    300114671, 300115123, 300115125, 300115133, 300115141, 300115143, 300115155, 300115321,
    300115539, 300115543, 300115545, 300115571, 300115573, 300115575, 300115577, 300115609,
    300115623, 300115701, 300115723, 300115727, 300115731, 300115733, 300115735, 300115737,
    300115739, 300115743, 300115745, 300115809, 300116523, 300116527, 300116529, 300116663,
    300117819, 300117822, 300117825, 300121337, 300121338, 300121339, 300121345, 300121346,
    300121349, 300121350, 300121351, 300121352, 300121355, 300121356, 300121357, 300121358,
    300121359, 300121360, 300121361, 300121363, 300121364, 300121365, 300121600, 300121727,
    300122483, 300122637, 300123362, 300123366, 300123392, 300123394, 300123397, 300123404,
    300123405, 300123406, 300123407, 300123409, 300123410, 300123411, 300123412, 300123414,
    300123416, 300123418, 300123419, 300123545, 300123562, 300123844, 300123861, 300123862,
    300123892, 300123893, 300123894, 300123965, 300124014, 300124015, 300124039, 300124041,
    300124043, 300124065, 300124088, 300124852, 300124855, 300124856, 300124858,
}
# Ostatní podkategorie (včetně konzerv, omáček, koření, kaší, müsli a instantních polévek) -> TRVANLIVE.
TRVANLIVE_SUBCATS = {
    300101018, 300101036, 300101050, 300104018, 300104036, 300105060, 300105061, 300106003,
    300106006, 300106007, 300106012, 300106013, 300106019, 300106020, 300106022, 300106023,
    300106028, 300106029, 300106032, 300106033, 300106035, 300106036, 300106037, 300106038,
    300106040, 300106041, 300106042, 300106043, 300106097, 300106098, 300106106, 300106108,
    300106109, 300106112, 300106113, 300106114, 300106115, 300110019, 300110029, 300112069,
    300112159, 300112403, 300112911, 300112915, 300112919, 300112921, 300112923, 300114639,
    300114673, 300114683, 300114741, 300114745, 300114903, 300114905, 300114907, 300115069,
    300115071, 300115073, 300115097, 300115101, 300115127, 300115129, 300115131, 300115149,
    300115151, 300115153, 300115315, 300115317, 300115489, 300115611, 300115615, 300115617,
    300115625, 300115627, 300115801, 300115807, 300115811, 300115813, 300115815, 300115831,
    300116525, 300116535, 300116539, 300116665, 300116667, 300116871, 300116873, 300116875,
    300116877, 300116879, 300116881, 300116885, 300116915, 300117167, 300117179, 300117187,
    300117193, 300117849, 300118470, 300118476, 300118853, 300118856, 300118859, 300118862,
    300118916, 300118919, 300119666, 300119671, 300119676, 300119681, 300120449, 300120450,
    300120467, 300121256, 300121418, 300121423, 300121503, 300121551, 300121567, 300121581,
    300121659, 300121844, 300121845, 300121846, 300121957, 300121985, 300121986, 300121987,
    300121988, 300121989, 300121990, 300121991, 300121992, 300122006, 300122017, 300122018,
    300122019, 300122030, 300122034, 300122035, 300122036, 300122037, 300122348, 300122349,
    300122350, 300122351, 300122410, 300122444, 300122524, 300122528, 300122538, 300122583,
    300122670, 300123019, 300123027, 300123069, 300123108, 300123322, 300123328, 300123342,
    300123343, 300123348, 300123376, 300123378, 300123380, 300123401, 300123402, 300123403,
    300123420, 300123423, 300123426, 300123429, 300123430, 300123431, 300123432, 300123433,
    300123434, 300123435, 300123436, 300123440, 300123441, 300123442, 300123444, 300123445,
    300123447, 300123448, 300123449, 300123450, 300123451, 300123453, 300123456, 300123462,
    300123463, 300123464, 300123468, 300123474, 300123477, 300123478, 300123480, 300123481,
    300123483, 300123484, 300123485, 300123486, 300123487, 300123490, 300123492, 300123493,
    300123494, 300123495, 300123496, 300123497, 300123500, 300123502, 300123504, 300123505,
    300123506, 300123512, 300123513, 300123514, 300123516, 300123517, 300123519, 300123520,
    300123524, 300123526, 300123536, 300123538, 300123540, 300123541, 300123554, 300123559,
    300123574, 300123575, 300123576, 300123577, 300123578, 300123579, 300123580, 300123581,
    300123598, 300123863, 300123864, 300123865, 300123866, 300123867, 300123868, 300123913,
    300123914, 300123915, 300123916, 300123922, 300123923, 300123925, 300123926, 300123927,
    300123928, 300123933, 300124029, 300124238, 300124666, 300124670, 300124741, 300124845,
    300124847, 300124848, 300124849, 300124850, 300124853,
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
