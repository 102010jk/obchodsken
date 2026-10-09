#!/usr/bin/env python3
"""Hromadný sběr: Lidl.cz – Maso a drůbež, Sýry/mléčné/vejce, Pekárna, Mražené, Ryby a mořské plody,
Hotová jídla, Ovoce a zelenina, Uzeniny (vč. vnořených podkategorií).

Výstup: data/foods/raw/09-lidl-chlazene.jsonl (přepíše se). Spuštění z libovolného adresáře:
    python3 data/foods/harvest/09-lidl-chlazene.py            # celý sběr
    python3 data/foods/harvest/09-lidl-chlazene.py --tree     # jen výpis stromu podkategorií a počtů

Jak Lidl stránkuje: stránka hubu/podkategorie má v SSR (<script id="__NUXT_DATA__">) prvních 48 produktů.
Další produkty jsou na ?offset=48, 96, … (celkový počet je v atributu products-message="N produktů").
Podkategorie se berou z facetu „Kategorie“ (uzly /h/<slug>/h<id>), cenové uzly („do 50Kč“) se ignorují.
Procházejí se všechny uzly do hloubky, každý uzel se stahuje jen jednou.

Detail produktu (/p/...): EAN z pole eans v SSR datech (jen platné EAN-8/13), velikost z viditelného řádku
u „Číslo výrobku“ (balení, ne cena za jednotku), značka z JSON-LD. ians jsou interní čísla Lidlu, NEJSOU EAN.
Vážené zboží („cena za 1 kg“) nemá velikost balení → pole se vynechá.

Id = lidl-<ID produktu v Lidlu>-<slug názvu>[-velikost]; deduplikace podle ID produktu.

Pravidla: jen data ze stránek Lidlu, žádné doplňování. Vynechány: trvanlivé, sladkosti, nápoje, alkohol, káva/čaj
(dělá jiný agent) a nepotraviny.
Šetrnost: max 1 požadavek za sekundu (celkem), při 429/5xx/síťové chybě exponenciální čekání (2, 4, 8, 16, 32 s),
po 5 neúspěších dotaz přeskočit. Při 403 se skript ukončí bez zápisu (blokaci neobcházíme).
Cache detailů: ~/.cache/obchodsken/lidl-09/ (změna přes LIDL09_CACHE) – opakované spuštění nestahuje znovu.
"""
import html as htmllib
import json
import os
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.request
from collections import Counter, deque
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "data/foods/raw/09-lidl-chlazene.jsonl"
CACHE = Path(os.environ.get("LIDL09_CACHE", Path.home() / ".cache/obchodsken/lidl-09"))

STORE = "Lidl"
BASE = "https://www.lidl.cz"
UA = "Mozilla/5.0"
MIN_INTERVAL = 1.0      # sekund mezi požadavky, celkem přes všechny dotazy
MAX_RETRIES = 5
PAGE = 48               # velikost stránky výpisu Lidlu

# Kořenové huby (klíč, h-id, slug). Kategorie v sběru se určuje podle wonCategoryPrimary produktu.
ROOTS = [
    ("maso", "h10095752", "maso-a-drubez"),
    ("syry", "h10095761", "syry-mlecne-vyrobky-a-vejce"),
    ("pekarna", "h10096086", "pekarna"),
    ("mrazene", "h10071049", "mrazene-vyrobky"),
    ("ryby", "h10071050", "ryby-a-morske-plody"),
    ("hotova", "h10071020", "hotova-jidla"),
    ("ovoce", "h10071012", "ovoce-a-zelenina"),
]

# Vynechané úrovně 3 (patří jinému agentovi nebo nejsou potraviny pro tento sběr).
EXCLUDE_L3 = {"Trvanlivé potraviny", "Sladkosti a slané snacky", "Nápoje", "Víno, pivo a lihoviny",
              "Káva, čaj a kakao"}
FOOD_PREFIX = ("Světy potřeb", "Potraviny a blízké potraviny")

_last_request = 0.0
stats = {"requests": 0, "retries": 0, "skipped": 0}
unmapped = Counter()
excluded = Counter()


class Blocked(Exception):
    pass


def _wait():
    global _last_request
    wait = MIN_INTERVAL - (time.monotonic() - _last_request)
    if wait > 0:
        time.sleep(wait)
    _last_request = time.monotonic()


def fetch(url):
    """GET s limitem 1 req/s; při 429/5xx/síťové chybě exponenciální čekání. None po 5 neúspěších nebo 404."""
    for attempt in range(MAX_RETRIES):
        _wait()
        stats["requests"] += 1
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html"})
            with urllib.request.urlopen(req, timeout=40) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as e:
            if e.code == 403:
                raise Blocked(url)
            if e.code == 404:
                print(f"  404, přeskakuji: {url[:100]}", file=sys.stderr)
                return None
            if not (e.code == 429 or e.code >= 500):
                print(f"  HTTP {e.code}, přeskakuji: {url[:100]}", file=sys.stderr)
                return None
        except (urllib.error.URLError, TimeoutError) as e:
            print(f"  chyba sítě ({e}), zkusím znovu", file=sys.stderr)
        stats["retries"] += 1
        time.sleep(2 ** (attempt + 1))
    stats["skipped"] += 1
    print(f"  po {MAX_RETRIES} pokusech přeskočeno: {url[:100]}", file=sys.stderr)
    return None


# ---------- parsování SSR dat (Nuxt devalue) ----------

def nuxt_root(page):
    m = re.search(r'<script[^>]*id="__NUXT_DATA__"[^>]*>(.*?)</script>', page, re.S)
    if not m:
        return None
    arr = json.loads(m.group(1))
    memo = {}

    def res(idx, depth=0):
        if isinstance(idx, bool) or not isinstance(idx, int) or depth > 80:
            return idx
        if idx < 0 or idx >= len(arr):
            return None
        if idx in memo:
            return memo[idx]
        v = arr[idx]
        if isinstance(v, dict):
            out = {}
            memo[idx] = out
            for k, r in v.items():
                out[k] = res(r, depth + 1)
            return out
        if isinstance(v, list):
            if len(v) == 2 and isinstance(v[0], str) and v[0] in ("Reactive", "Ref", "EmptyRef", "ShallowRef", "ShallowReactive"):
                return res(v[1], depth + 1)
            out = []
            memo[idx] = out
            for r in v:
                out.append(res(r, depth + 1))
            return out
        return v

    return res(0)


def walk(o, fn):
    if isinstance(o, dict):
        fn(o)
        for v in o.values():
            walk(v, fn)
    elif isinstance(o, list):
        for v in o:
            walk(v, fn)


NODE_URL = re.compile(r"/q/api/category/h/([a-z0-9-]+)/(h\d+)")
PRICE_BUCKET = re.compile(r"(^do \d+\s*Kč$)|(Kč$)")


def parse_page(page):
    """Vrátí (produkty {productId: dict}, uzly {h-id: {slug, label, count}}) pro danou stránku."""
    products, nodes = {}, {}
    root = nuxt_root(page)
    if root is None:
        return products, nodes

    def on_dict(d):
        if "productId" in d and ("keyfacts" in d or "canonicalUrl" in d):
            pid = d.get("productId")
            if isinstance(pid, int) and pid not in products:
                products[pid] = d
        if isinstance(d.get("url"), str) and "label" in d:
            m = NODE_URL.search(d["url"])
            if m:
                nodes.setdefault(m.group(2), {"slug": m.group(1), "label": d.get("label"), "count": d.get("count")})

    walk(root, on_dict)
    return products, nodes


def total_count(page):
    m = re.search(r'products-message="(\d+)', page)
    return int(m.group(1)) if m else None


# ---------- sběr výpisů (stromem hubů a podkategorií) ----------

def crawl():
    """BFS přes huby a jejich podkategorie, každý uzel stránkovaný přes offset. Vrací (produkty, strom)."""
    listing = {}     # pid -> info z výpisu
    tree = []        # (hid, slug, klíč hubu, rodič, počet_z_stránky, celkem)
    visited = set()
    queue = deque((hid, slug, key, None) for key, hid, slug in ROOTS)
    while queue:
        hid, slug, key, parent = queue.popleft()
        if hid in visited:
            continue
        visited.add(hid)
        url0 = f"{BASE}/h/{slug}/{hid}"
        offset, total, nodes_here, found_here = 0, None, {}, 0
        while True:
            url = url0 if offset == 0 else f"{url0}?offset={offset}"
            page = fetch(url)
            if page is None:
                break
            if offset == 0:
                total = total_count(page)
            prods, nodes = parse_page(page)
            if offset == 0:
                nodes_here = nodes
            new = 0
            for pid, d in prods.items():
                kf = d.get("keyfacts") or {}
                if pid not in listing:
                    new += 1
                    listing[pid] = {
                        "pid": pid,
                        "path": d.get("canonicalUrl") or d.get("canonicalPath"),
                        "name": d.get("fullTitle") or kf.get("fullTitle") or kf.get("title"),
                        "won": kf.get("wonCategoryPrimary") or "",
                        "image": d.get("image") if isinstance(d.get("image"), str) else None,
                        "sources": [url],
                        "hub": key,
                    }
                elif url not in listing[pid]["sources"]:
                    listing[pid]["sources"].append(url)
            found_here += new
            offset += PAGE
            if not prods or new == 0 or total is None or offset >= total:
                break
        tree.append((hid, slug, key, parent, found_here, total))
        print(f"  uzel {hid} {slug}: celkem {total}, nových {found_here}, produktů celkem {len(listing)}",
              file=sys.stderr)
        for chid, meta in nodes_here.items():
            if chid in visited or PRICE_BUCKET.search(meta.get("label") or ""):
                continue
            queue.append((chid, meta["slug"], key, hid))
    return listing, tree


# ---------- mapování kategorie (podle wonCategoryPrimary produktu v Lidlu) ----------

def map_category(won, hub_key):
    """Vrátí kategorii FORMAT.md, nebo None (vynechat). Nepotravina/jiný agent → None + počítadlo."""
    parts = [p.strip() for p in won.split("/")]
    if len(parts) < 3 or tuple(parts[:2]) != FOOD_PREFIX:
        excluded["nepotravina / bez kategorie"] += 1
        return None
    l3 = parts[2]
    l4 = parts[3] if len(parts) > 3 else ""
    if l3 in EXCLUDE_L3:
        excluded[f"jiný agent: {l3}"] += 1
        return None
    if any(p.startswith("Mražen") for p in parts[2:]):
        return "MRAZENE"
    if l3 in ("Maso a drůbež", "Ryby a mořské plody"):
        return "MASO_RYBY"
    if "Uzenin" in l3 or "Uzenin" in l4 or "Lahůdk" in l3:
        return "UZENINY"
    if l3 == "Ovoce a zelenina":
        return "OVOCE_ZELENINA"
    if l3.startswith("Pekár") or l3.startswith("Pečiv"):
        return "PECIVO"
    if l3 == "Sýry, mléčné výrobky a vejce":
        return "VEJCE" if l4 == "Vejce" else "MLECNE"
    if l3 == "Hotová jídla":
        return "OSTATNI"
    unmapped[f"{l3} / {l4}"] += 1
    return None


# ---------- detail produktu ----------

EAN_OK = re.compile(r"^\d{8}$|^\d{13}$")


def ean_valid(e):
    if not EAN_OK.match(e):
        return False
    d = [int(c) for c in e]
    body, check = d[:-1], d[-1]
    s = sum(x * (3 if (len(body) - i) % 2 == 1 else 1) for i, x in enumerate(body))
    return (10 - s % 10) % 10 == check


SIZE_OK = re.compile(r"^(\d+(?:[.,]\d+)?)\s?(g|kg|ml|l|ks)$")


def size_from_line(line):
    """Balení z řádku typu „500 g“, „1 kg“, „6 ks“, „250 g, 100 g = 18,96 Kč“. Multipacky a ceny za jednotku ne."""
    if re.search(r" x |/|a další|cena|kus", line, re.I):
        return None
    first = re.split(r"[;,]", line)[0].strip()
    m = SIZE_OK.match(first)
    if not m:
        return None
    v = float(m.group(1).replace(",", "."))
    u = m.group(2)
    if u == "g":
        return round(v / 1000, 6), "kg"
    if u == "ml":
        return round(v / 1000, 6), "l"
    return round(v, 6), u


def visible_lines(page):
    m = re.search(r"<body", page)
    body = page[m.start():] if m else page
    body = re.sub(r"<script.*?</script>|<style.*?</style>", "", body, flags=re.S)
    text = htmllib.unescape(re.sub(r"<[^>]+>", "\n", body))
    return [l.strip() for l in text.split("\n") if l.strip()]


def size_from_page(page):
    lines = visible_lines(page)
    idx = next((i for i, l in enumerate(lines) if l.startswith("Číslo výrobku")), None)
    if idx is None:
        return None
    for j in range(idx - 1, max(0, idx - 12) - 1, -1):
        s = size_from_line(lines[j])
        if s:
            return s
    return None


def ld_product(page):
    for m in re.finditer(r'<script type="application/ld\+json"[^>]*>(.*?)</script>', page, re.S):
        try:
            o = json.loads(m.group(1))
        except ValueError:
            continue
        if isinstance(o, dict) and o.get("@type") == "Product":
            return o
    return {}


def caps_brand(name):
    skip = {"BIO", "DR.", "XL", "XXL", "M", "L", "NEW", "TOP"}
    out = []
    for t in name.split():
        core = t.strip(".,&-/")
        if len(core) >= 2 and core.isupper() and t not in skip and core not in skip:
            out.append(t)
        else:
            break
    return " ".join(out) if out else None


def product_detail(pid, listing_item):
    """Detail z cache, nebo ze stránky /p/. None při neúspěchu."""
    cache_file = CACHE / "p" / f"{pid}.json"
    try:
        if cache_file.exists():
            return json.loads(cache_file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    page = fetch(BASE + listing_item["path"])
    if page is None:
        return None
    ld = ld_product(page)
    eans, erp = [], None
    root = nuxt_root(page)
    if root is not None:
        def on_dict(d):
            nonlocal erp
            if d.get("productId") == pid:
                if isinstance(d.get("eans"), list):
                    eans.extend(e for e in d["eans"] if isinstance(e, str))
                erp = d.get("erpNumber") or erp
        walk(root, on_dict)
    brand = None
    b = ld.get("brand")
    if isinstance(b, dict) and b.get("name"):
        brand = b["name"]
    name = ld.get("name") or listing_item["name"]
    if not brand:
        brand = caps_brand(name or "")
    img = ld.get("image")
    if isinstance(img, list):
        img = img[0] if img else None
    rec = {
        "name": name,
        "brand": brand,
        "image": img if isinstance(img, str) else listing_item.get("image"),
        "size": size_from_page(page),
        "eans": sorted({e for e in eans if ean_valid(e)}),
        "erp": erp,
    }
    try:
        CACHE.joinpath("p").mkdir(parents=True, exist_ok=True)
        cache_file.write_text(json.dumps(rec, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass
    return rec


# ---------- zápis ----------

def slugify(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def size_label(value, unit):
    if unit == "kg":
        return f"{round(value * 1000)}g" if value < 1 else f"{value:g}kg".replace(".", "-")
    if unit == "l":
        return f"{round(value * 1000)}ml" if value < 1 else f"{value:g}l".replace(".", "-")
    return f"{value:g}{unit}"


def build_record(pid, item, cat, det):
    name = det["name"] or item["name"]
    brand = det["brand"]
    if brand and name and not name.lower().startswith(brand.lower()):
        name = f"{brand} {name}"
    slug = slugify(name)[:60].strip("-")
    size = det["size"]
    suffix = ""
    if size:
        suffix = "-" + size_label(*size)
    rec = {"id": f"{STORE.lower()}-{pid}-{slug}{suffix}", "name": name}
    if brand:
        rec["brand"] = brand
    rec["category"] = cat
    if size:
        v = size[0]
        rec["size_value"] = int(v) if float(v).is_integer() else v
        rec["size_unit"] = size[1]
    if det["eans"]:
        rec["eans"] = det["eans"]
    url = BASE + item["path"]
    rec["stores"] = [{"store": STORE, "receipt_name": None, "receipt_name_source": None, "url": url}]
    if det["image"]:
        rec["image_url"] = det["image"]
    rec["sources"] = [url] + [s for s in item["sources"] if s != url][:2]
    return rec


def main():
    tree_only = "--tree" in sys.argv
    try:
        listing, tree = crawl()
    except Blocked as e:
        print(f"Blokace (403) na {e}, končím bez zápisu.", file=sys.stderr)
        return 2

    print("\nStrom (uzel, slug, hub, rodič, nových z uzlu, celkem na uzlu):", file=sys.stderr)
    for row in tree:
        print("  ", row, file=sys.stderr)
    cats = Counter(" / ".join(p.strip() for p in it["won"].split("/")[2:4]) for it in listing.values())
    print(f"\nUnikátních produktů ve výpisech: {len(listing)}", file=sys.stderr)
    print("Úrovně 3/4 (počet):", file=sys.stderr)
    for k, n in cats.most_common():
        print(f"  {n:5d}  {k}", file=sys.stderr)
    if tree_only:
        return 0

    records, seen_ids, skipped_detail = [], set(), 0
    for pid, item in listing.items():
        cat = map_category(item["won"], item["hub"])
        if cat is None:
            continue
        det = product_detail(pid, item)
        if det is None:
            skipped_detail += 1
            continue
        rec = build_record(pid, item, cat, det)
        if rec["id"] in seen_ids:
            continue
        seen_ids.add(rec["id"])
        records.append(rec)
        if stats["requests"] % 100 == 0:
            print(f"  zpracováno {len(records)} záznamů, požadavků {stats['requests']}", file=sys.stderr)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"\nZapsáno {len(records)} záznamů do {OUT}", file=sys.stderr)
    print(f"Požadavků: {stats['requests']} (opakování {stats['retries']}, přeskočeno {stats['skipped']}), "
          f"detail nešel stáhnout: {skipped_detail}", file=sys.stderr)
    print(f"Vynecháno: {dict(excluded)}", file=sys.stderr)
    if unmapped:
        print(f"Nezařazené úrovně (nezapsáno, je třeba doplnit mapování): {dict(unmapped)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
