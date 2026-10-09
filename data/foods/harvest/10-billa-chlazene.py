#!/usr/bin/env python3
"""Hromadný sběr: BILLA (billa.cz) – mléčné výrobky a sýry, vejce, maso a ryby, uzeniny a lahůdky, pečivo.

Výstup: data/foods/raw/10-billa-chlazene.jsonl (přepíše se). Spuštění z kteréhokoli adresáře:
    python3 data/foods/harvest/10-billa-chlazene.py

Zdroj: JSON API webu billa.cz
  - strom kategorií:  /api/product-discovery/categories/tree
  - produkty listové kategorie: /api/product-discovery/categories/{slug}/products?pageSize=100&page=N
    (page je 0-based, offset = page * pageSize, odpověď nese count/offset/total)
Produkty se berou přímo z výpisu (není třeba stahovat detaily), deduplikace podle SKU.
Velikost jen z názvu produktu (JSON-LD weight se nepoužívá). Pravidla 1–8 z haiku-sberac.md platí.

Šetrnost: max 1 požadavek za sekundu (sdíleno pro všechny dotazy), při 429/5xx exponenciální čekání,
po 5 neúspěších stránku přeskočit. Při 403 se script ukončí bez zápisu (blokaci neobcházíme).
"""
import json
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.request
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "data/foods/raw/10-billa-chlazene.jsonl"

STORE = "Billa"
SITE = "https://www.billa.cz"
API = f"{SITE}/api/product-discovery/categories"
PAGE_SIZE = 100
MAX_PAGES = 100
MIN_INTERVAL = 1.0      # sekund mezi požadavky
MAX_RETRIES = 5
UA = "Mozilla/5.0"

# Kořeny stromu (klíče z /categories/tree), které sbíráme.
ROOTS = {
    1207: "MLECNE",    # Chlazené, mléčné a rostlinné výrobky (včetně sýrů; vejce = Vejce a droždí, viz OVERRIDES)
    1263: "MASO_RYBY", # Maso a ryby
    1276: "UZENINY",   # Uzeniny, lahůdky a hotová jídla
    1198: "PECIVO",    # Pečivo
}
# Podstromy, které nesbíráme (nepotraviny nebo mimo zadání).
EXCLUDE = {
    1253: "majonézy, tatarské omáčky a dresinky (mimo zadání)",
    1262: "droždí (není vejce ani mléčný výrobek)",
    2956: "pomůcky na pečení (nepotraviny)",
}
# Přepisy kategorie pro podkategorie (nejbližší předek s přepisem vyhrává).
OVERRIDES = {
    1261: "VEJCE",
    1242: "SLADKOSTI",      # Tyčinky (proteinové/mléčné tyčinky)
    1291: "MASO_RYBY",      # Rybí speciality
    1278: "PECIVO", 1279: "PECIVO",  # Chlebíčky, bagety a sendviče
    2080: "PECIVO",         # Těsta (hotová jídla)
    2390: "SLADKOSTI",      # Dorty a zákusky
    2278: "SLADKOSTI",      # Dezerty (hotová jídla)
    1317: "SLADKOSTI",      # Dorty a dezerty (mražené)
    2388: "TRVANLIVE",      # Pečení (těsta, pečicí směsi, strouhanka)
    1298: "OSTATNI",        # Hotová jídla
    1302: "OSTATNI",        # Čerstvé těstoviny
    1304: "OSTATNI",        # Hotové zeleninové saláty
    1305: "OSTATNI",        # Sushi
    1647: "OSTATNI",        # Pizza
}

_last_request = 0.0
stats = {"requests": 0, "retries": 0, "skipped_pages": 0}


class Blocked(Exception):
    pass


def get_json(url):
    """GET s limitem 1 req/s a retry (exponenciálně) při 429/5xx/síťové chybě. None po 5 neúspěších."""
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
                print(f"  HTTP {e.code}, přeskakuji: {url[:100]}", file=sys.stderr)
                return None
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            print(f"  chyba sítě/JSON ({e}), zkusím znovu", file=sys.stderr)
        stats["retries"] += 1
        time.sleep(2 ** attempt)
    return None


def category_for(chain):
    """chain = [kořen, ..., list]. Nejbližší předek s přepisem vyhrává, jinak kategorie kořene."""
    for k in reversed(chain):
        if k in OVERRIDES:
            return OVERRIDES[k]
    return ROOTS[chain[0]]


SIZE = re.compile(r"(?<![\d,.])(\d+(?:[.,]\d+)?)\s*(kg|g|ml|l|L)(?![a-zA-Z])")


def size_from_name(name):
    ms = SIZE.findall(name)
    if not ms:
        return None, None
    num, unit = ms[-1]
    v = float(num.replace(",", "."))
    unit = unit.lower()
    if unit == "g":
        return round(v / 1000, 3), "kg"
    if unit == "ml":
        return round(v / 1000, 3), "l"
    return v, unit


def slugify(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def fetch_category(slug):
    items, offset = [], 0
    for page in range(MAX_PAGES):
        url = f"{API}/{slug}/products?pageSize={PAGE_SIZE}&page={page}"
        data = get_json(url)
        if data is None:
            stats["skipped_pages"] += 1
            print(f"  {slug}: stránka {page} přeskočena", file=sys.stderr)
            break
        results = data.get("results") or []
        items.extend(results)
        offset = (data.get("offset") or 0) + len(results)
        total = data.get("total") or 0
        if not results or offset >= total:
            break
    return items


def build_record(p, category):
    name = re.sub(r"\s+", " ", (p.get("name") or p.get("descriptionShort") or "")).strip()
    slug = p.get("slug")
    sku = p.get("sku")
    url = f"{SITE}/produkt/{slug}"
    rec = {"id": f"billa-{slugify(sku or '')}-{slugify(name)}", "name": name}
    brand = ((p.get("brand") or {}).get("name") or "").strip()
    if brand:
        rec["brand"] = brand
    rec["category"] = category
    sv, su = size_from_name(name)
    if sv is not None:
        rec["size_value"], rec["size_unit"] = sv, su
    rec["stores"] = [{"store": STORE, "receipt_name": None, "receipt_name_source": None, "url": url}]
    if p.get("images"):
        rec["image_url"] = p["images"][0]
    rec["sources"] = [url]
    return rec, sku


def main():
    tree = get_json(f"{API}/tree")
    if not isinstance(tree, list):
        print("strom kategorií se nepodařilo stáhnout, končím bez zápisu", file=sys.stderr)
        return 1

    leaves = []

    def visit(node, chain):
        """Sbírá listy pod kořeny z ROOTS (mimo EXCLUDE) spolu s řetězcem předků."""
        key = int(node["key"])  # klíče v API jsou řetězce
        chain = chain + [key]
        if key in EXCLUDE:
            return
        kids = node.get("children") or []
        if not kids:
            leaves.append((node, chain))
            return
        for c in kids:
            visit(c, chain)

    for root in tree:
        if int(root["key"]) in ROOTS:
            visit(root, [])
    print(f"listových kategorií: {len(leaves)}")

    by_sku = {}
    dup = 0
    for leaf, chain in leaves:
        cat = category_for(chain)
        items = fetch_category(leaf["slug"])
        new = 0
        for p in items:
            if not p.get("published", True):
                continue
            sku = p.get("sku")
            if not sku:
                continue
            if sku in by_sku:
                dup += 1
                continue
            rec, _ = build_record(p, cat)
            by_sku[sku] = rec
            new += 1
        print(f"  {leaf['name']} [{leaf['slug']}] -> {cat}: {len(items)} položek, nových {new}")

    records = list(by_sku.values())
    # related: stejný název bez velikosti (různé gramáže / balení) -> navzájem příbuzné
    groups = defaultdict(list)
    for r in records:
        base = SIZE.sub("", r["name"]).strip().lower()
        groups[(r.get("brand", ""), slugify(base))].append(r["id"])
    for r in records:
        base = SIZE.sub("", r["name"]).strip().lower()
        others = [i for i in groups[(r.get("brand", ""), slugify(base))] if i != r["id"]]
        if others:
            r["related"] = others

    tmp = OUT.with_suffix(".jsonl.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    tmp.replace(OUT)
    print(f"zapsáno {len(records)} záznamů do {OUT}; duplicit podle SKU přeskočeno {dup}")
    print(f"požadavků {stats['requests']}, opakování {stats['retries']}, přeskočených stránek {stats['skipped_pages']}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Blocked as e:
        print(f"HTTP 403 – blokace, končím bez zápisu: {e}", file=sys.stderr)
        sys.exit(2)
