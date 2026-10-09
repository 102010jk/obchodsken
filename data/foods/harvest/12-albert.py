#!/usr/bin/env python3
"""Hromadný sběr: Albert.cz – celý potravinový sortiment -> data/foods/raw/12-albert.jsonl (přepíše se).

Použití (z kteréhokoli adresáře):
    python3 data/foods/harvest/12-albert.py                  # celý sběr (síť)
    python3 data/foods/harvest/12-albert.py --cache DIR      # odpovědi API ukládá/čte z DIR (opakování bez sítě)
    python3 data/foods/harvest/12-albert.py --discover       # jen výpis kořenových kategorií z categorySearchTree

Postup: GraphQL API webu (https://www.albert.cz/api/v1/, operace z JS bundlu stránky):
  1. GetCategoryProductSearch -> categorySearchTree (ověření kořenů), volitelně --discover
  2. GetProductSearch (productSearchV2) pro každou kořenovou kategorii potravin, stránkováno po 50
     (50 je maximum, které API přijme). Produkty se deduplikují podle kódu produktu.
  3. Kategorie FORMAT.md se určuje podle URL produktu (/shop/<podkategorie 1>/<podkategorie 2>/...)
     přes MAP níže. Nepotraviny a produkty mimo MAP se vyřadí a vypíšou se ve statistice.
  4. Velikost balení jen z názvu, a to pouze když je v názvu jediná jednoznačná hodnota (500 g, 1,5 l, 10 ks).

Pravidla: jen data z API obchodu, žádné doplňování, žádné EAN (API je neposkytuje).
Šetrnost: max 1 požadavek za sekundu, při 429/5xx/síťové chybě exponenciální čekání (2, 4, 8, 16, 32 s),
po 5 neúspěších stránku přeskočit (počet přeskočených se vypíše). Blokaci (403) neobcházíme – skript skončí bez zápisu.
"""
import argparse
import hashlib
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
OUT = ROOT / "data/foods/raw/12-albert.jsonl"

STORE = "Albert"
BASE = "https://www.albert.cz"
API = BASE + "/api/v1/"
UA = "Mozilla/5.0"
MIN_INTERVAL = 1.0      # sekund mezi požadavky, celkem přes všechny dotazy
MAX_RETRIES = 5
PAGE_SIZE = 50          # API přijme nejvýš 50 (60 a 100 vrací BAD_USER_INPUT)

# Kořenové kategorie potravin (categoryCode -> název z API). Nepotravinové kořeny (drogerie, domácnost,
# mazlíčci) se nestahují vůbec. Překryvy (např. Trvale nízké) řeší deduplikace podle kódu produktu.
FOOD_ROOTS = [
    ("zeJ001", "Mléčné a chlazené"),
    ("zeL001", "Trvanlivé"),
    ("zeM001", "Nápoje"),
    ("zeB001", "Trvale nízké"),
    ("zeP001", "Péče o nejmenší"),
    ("zeN001", "Speciální výživa"),
    ("zeK001", "Uzeniny a lahůdky"),
    ("zeG001", "Ovoce a zelenina"),
    ("zeF001", "Pekárna a cukrárna"),
    ("zeJ005", "Mražené"),
    ("zeH001", "Maso a ryby"),
]

# Podkategorie obchodu (slug v URL: /shop/<seg1>/<seg2>/...) -> kategorie FORMAT.md.
# None = nepotravina / mimo zadání. Klíč (seg1, seg2); seg2 None = platí pro celou kořenovou kategorii.
MAP = {}

_last_request = 0.0
stats = {"requests": 0, "retries": 0, "failed_pages": 0, "from_cache": 0}


class Blocked(Exception):
    pass


class ApiError(Exception):
    """Chyba GraphQL (např. BAD_USER_INPUT) – nezkouší se znovu."""


QUERY_SEARCH = (
    "query GetProductSearch($lang:String$searchQuery:String$pageSize:Int$pageNumber:Int$category:String"
    "$sort:String$filterFlag:Boolean$useSpellingSuggestion:Boolean$customerSegment:String$facetsOnly:Boolean"
    "$fields:String){productSearch:productSearchV2(lang:$lang searchQuery:$searchQuery pageSize:$pageSize "
    "pageNumber:$pageNumber category:$category sort:$sort filterFlag:$filterFlag "
    "useSpellingSuggestion:$useSpellingSuggestion customerSegment:$customerSegment facetsOnly:$facetsOnly "
    "fields:$fields){products{code name url manufacturerName images{format imageType url}}"
    "pagination{totalResults pageSize currentPage}}}"
)

QUERY_TREE = (
    "query GetCategoryProductSearch($lang:String$searchQuery:String$pageSize:Int$pageNumber:Int$category:String"
    "$sort:String$filterFlag:Boolean$customerSegment:String$plainChildCategories:Boolean$facetsOnly:Boolean"
    "$fields:String){categoryProductSearch:categoryProductSearchV2(lang:$lang searchQuery:$searchQuery "
    "pageSize:$pageSize pageNumber:$pageNumber category:$category sort:$sort filterFlag:$filterFlag "
    "customerSegment:$customerSegment plainChildCategories:$plainChildCategories facetsOnly:$facetsOnly "
    "fields:$fields){pagination{totalResults} categorySearchTree{categoryDataList{categoryCode "
    "categoryData{facetData{count name}subCategories}}level}}}"
)


def _cache_path(cache_dir, key):
    return os.path.join(cache_dir, hashlib.sha1(key.encode()).hexdigest() + ".json")


def _wait():
    global _last_request
    wait = MIN_INTERVAL - (time.monotonic() - _last_request)
    if wait > 0:
        time.sleep(wait)
    _last_request = time.monotonic()


def gql(op, query, variables, cache_dir=None):
    """Vrátí `data` z GraphQL odpovědi. Při 429/5xx/síťové chybě opakuje s exponenciálním čekáním."""
    key = op + json.dumps(variables, sort_keys=True, ensure_ascii=False)
    if cache_dir:
        p = _cache_path(cache_dir, key)
        if os.path.exists(p):
            stats["from_cache"] += 1
            with open(p, encoding="utf-8") as f:
                return json.load(f)
    body = json.dumps({"operationName": op, "query": query, "variables": variables}, ensure_ascii=False).encode()
    headers = {
        "User-Agent": UA,
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Referer": BASE + "/",
        "X-APOLLO-OPERATION-NAME": op,
    }
    for attempt in range(MAX_RETRIES):
        _wait()
        stats["requests"] += 1
        try:
            req = urllib.request.Request(API, data=body, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=60) as r:
                payload = json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 403:
                raise Blocked(f"HTTP 403 u {op} – blokace, neobcházíme")
            if e.code == 400:
                raise ApiError(f"HTTP 400 u {op}: {e.read()[:200]!r}")
            if e.code == 429 or e.code >= 500:
                err = f"HTTP {e.code}"
            else:
                raise ApiError(f"HTTP {e.code} u {op}")
        except (urllib.error.URLError, TimeoutError, ConnectionError, json.JSONDecodeError) as e:
            err = f"síť/JSON: {e}"
        else:
            if payload.get("errors"):
                raise ApiError(f"GraphQL chyba u {op}: {payload['errors'][0].get('message')}")
            if cache_dir:
                os.makedirs(cache_dir, exist_ok=True)
                with open(_cache_path(cache_dir, key), "w", encoding="utf-8") as f:
                    json.dump(payload["data"], f, ensure_ascii=False)
            return payload["data"]
        stats["retries"] += 1
        delay = 2 ** (attempt + 1)
        print(f"  {err}, čekám {delay} s (pokus {attempt + 1}/{MAX_RETRIES})", file=sys.stderr)
        time.sleep(delay)
    raise ApiError(f"{op}: {MAX_RETRIES} neúspěšných pokusů")


def discover(cache_dir=None):
    """Vypíše kořenové kategorie z categorySearchTree (kontrola kódů v FOOD_ROOTS)."""
    d = gql("GetCategoryProductSearch", QUERY_TREE, {
        "lang": "cs", "searchQuery": "", "pageSize": 1, "pageNumber": 0, "category": None,
        "fields": "FULL", "facetsOnly": False, "plainChildCategories": True,
    }, cache_dir)
    tree = d["categoryProductSearch"]["categorySearchTree"]
    roots = tree[0]["categoryDataList"] if tree else []
    for c in roots:
        f = c["categoryData"]["facetData"]
        print(f"{c['categoryCode']} | {f['name']} | {f['count']} | podkategorií: {len(c['categoryData']['subCategories'])}")
    return roots


def fetch_root(code, name, cache_dir):
    """Stránkuje všechny produkty kořenové kategorie. Vrací dict kód -> produkt (dedup uvnitř kořene)."""
    out = {}
    page = 0
    total = None
    while True:
        try:
            d = gql("GetProductSearch", QUERY_SEARCH, {
                "lang": "cs", "searchQuery": None, "pageSize": PAGE_SIZE, "pageNumber": page,
                "category": code, "fields": "FULL", "facetsOnly": False, "useSpellingSuggestion": False,
            }, cache_dir)
        except ApiError as e:
            print(f"  {code} strana {page}: přeskočeno ({e})", file=sys.stderr)
            stats["failed_pages"] += 1
            page += 1
            if total is not None and page * PAGE_SIZE >= total:
                break
            continue
        ps = d["productSearch"]
        if total is None:
            total = ps["pagination"]["totalResults"]
            print(f"{code} {name}: {total} produktů", file=sys.stderr)
        products = ps["products"] or []
        for p in products:
            out.setdefault(p["code"], p)
        page += 1
        if not products or page * PAGE_SIZE >= total:
            break
    return out


def slug(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def seg_keys(url):
    """/shop/<seg1>/<seg2>/... -> (seg1, seg2). Vrací (None, None), pokud URL nemá očekávaný tvar."""
    parts = [x for x in (url or "").split("/") if x]
    if len(parts) >= 2 and parts[0] == "shop":
        seg2 = parts[2] if len(parts) > 2 and parts[2] != "p" else None
        return parts[1], seg2
    return None, None


def category_of(url):
    seg1, seg2 = seg_keys(url)
    if (seg1, seg2) in MAP:
        return MAP[(seg1, seg2)], (seg1, seg2)
    if (seg1, None) in MAP:
        return MAP[(seg1, None)], (seg1, None)
    return None, (seg1, seg2)


SIZE_RE = re.compile(r"(?<![\w,.])(\d+(?:[.,]\d+)?)\s?(kg|g|ml|cl|l|ks)(?![\w])", re.IGNORECASE)
MULTIPACK_RE = re.compile(r"\d\s*[x×]\s*\d", re.IGNORECASE)


def parse_size(name):
    """Velikost z názvu jen když je jednoznačná (jedna hodnota, žádný násobek 'N x')."""
    if MULTIPACK_RE.search(name):
        return None, None
    found = {(float(m.group(1).replace(",", ".")), m.group(2).lower()) for m in SIZE_RE.finditer(name)}
    if len(found) != 1:
        return None, None
    v, u = found.pop()
    if u == "g":
        return round(v / 1000, 6), "kg"
    if u == "kg":
        return round(v, 6), "kg"
    if u == "ml":
        return round(v / 1000, 6), "l"
    if u == "cl":
        return round(v / 100, 6), "l"
    if u == "l":
        return round(v, 6), "l"
    if u == "ks":
        return int(v) if v == int(v) else round(v, 6), "ks"
    return None, None


def build_record(p, category):
    url = BASE + p["url"]
    brand = (p.get("manufacturerName") or "").strip()
    if not brand or brand.lower() == p["name"].lower():
        brand = None
    imgs = {i["format"]: i["url"] for i in (p.get("images") or []) if i.get("url")}
    img = imgs.get("zoom") or next(iter(imgs.values()), None)
    rec = {"id": f"{STORE.lower()}-{p['code']}-{slug(p['name'])}", "name": p["name"]}
    if brand:
        rec["brand"] = brand
    rec["category"] = category
    size_value, size_unit = parse_size(p["name"])
    if size_value is not None:
        rec["size_value"] = size_value
        rec["size_unit"] = size_unit
    rec["stores"] = [{"store": STORE, "receipt_name": None, "receipt_name_source": None, "url": url}]
    if img:
        rec["image_url"] = BASE + img if img.startswith("/") else img
    rec["sources"] = [url, API]
    return rec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", metavar="DIR", help="cache odpovědí API (opakování bez sítě)")
    ap.add_argument("--discover", action="store_true", help="jen výpis kořenových kategorií")
    args = ap.parse_args()

    if args.discover:
        discover(args.cache)
        return 0

    products = {}
    by_root = {}
    for code, name in FOOD_ROOTS:
        got = fetch_root(code, name, args.cache)
        by_root[code] = len(got)
        for k, v in got.items():
            products.setdefault(k, v)

    stats_cat = {}
    skipped = {}
    unmapped = {}
    rows = []
    for code, p in products.items():
        category, key = category_of(p["url"])
        if category is None:
            if key in MAP:
                skipped[key] = skipped.get(key, 0) + 1
            else:
                unmapped[key] = unmapped.get(key, 0) + 1
            continue
        stats_cat[category] = stats_cat.get(category, 0) + 1
        rows.append(build_record(p, category))

    rows.sort(key=lambda r: r["id"])
    print(f"Unikátních produktů z API: {len(products)} (po kořenech: {by_root})", file=sys.stderr)
    print(f"Podle kategorie: {dict(sorted(stats_cat.items()))}", file=sys.stderr)
    print(f"Vyřazeno (nepotraviny z MAP): {sum(skipped.values())} – {skipped}", file=sys.stderr)
    print(f"Nezařazeno do MAP: {sum(unmapped.values())} – {unmapped}", file=sys.stderr)
    if not rows:
        print("Nic k zápisu – výstup nepřepsán.", file=sys.stderr)
        return 1
    OUT.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUT.with_suffix(".jsonl.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    os.replace(tmp, OUT)

    print(f"\nZápis: {len(rows)} záznamů -> {OUT}", file=sys.stderr)
    print(f"Požadavky: {stats['requests']}, opakování: {stats['retries']}, "
          f"přeskočené stránky: {stats['failed_pages']}, z cache: {stats['from_cache']}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Blocked as e:
        print(f"Zastaveno: {e}. Výstup nebyl zapsán.", file=sys.stderr)
        sys.exit(2)
