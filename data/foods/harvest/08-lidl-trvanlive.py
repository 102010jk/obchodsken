#!/usr/bin/env python3
"""Hromadný sběr: Lidl.cz – Spíž, Sladkosti a slané snacky, Nápoje, Víno/pivo/lihoviny (vč. vnořených podkategorií).

Výstup: data/foods/raw/08-lidl-trvanlive.jsonl (přepíše se). Spuštění z kteréhokoli adresáře:
    python3 data/foods/harvest/08-lidl-trvanlive.py            # celý sběr
    python3 data/foods/harvest/08-lidl-trvanlive.py --tree     # jen výpis stromu podkategorií

Jak Lidl stránkuje: stránka kategorie v SSR (<script id="__NUXT_DATA__">) obsahuje jen prvních ~42 produktů;
parametry ?page= ani ?offset= nové produkty nevrací. Další produkty jsou jen v jiných (vnořených) podkategoriích,
proto se procházejí všechny uzly stromu z facetu „Kategorie“ na stránkách /h/<slug>/h<id>.
Detail produktu (/p/...) dodá seznam EAN (pole eans); ians jsou interní čísla Lidlu, NEJSOU EAN.

Pravidla: jen data ze stránek Lidlu, žádné doplňování. Velikost jen z balení uvedeného v datech (basePrice nebo název).
Šetrnost: max 1 požadavek za sekundu (sdíleno se všemi dotazy), při 429/5xx exponenciální čekání, po 5 neúspěších
dotaz přeskočit. Při 403 se script ukončí bez zápisu (blokaci neobcházíme).
"""
import json
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "data/foods/raw/08-lidl-trvanlive.jsonl"

STORE = "Lidl"
BASE = "https://www.lidl.cz"
MIN_INTERVAL = 1.0      # sekund mezi požadavky, celkem přes všechny dotazy
MAX_RETRIES = 5
UA = "Mozilla/5.0"

# Kořenové podkategorie Lidlu (h-id, slug) -> kategorie FORMAT.md.
ROOTS = [
    ("h10096095", "trvanlive-potraviny", "TRVANLIVE"),   # Spíž
    ("h10096205", "sladkosti-a-slane-snacky", "SLADKOSTI"),
    ("h10071022", "napoje", "NAPOJE"),
    ("h10096268", "vino-pivo-a-lihoviny", "ALKOHOL"),
]
ROOT_CATEGORY = {h: cat for h, _, cat in ROOTS}

# Podkategorie, které nejsou potraviny (vyplní se po výpisu stromu --tree).
NONFOOD_IDS = set()

_last_request = 0.0
stats = {"requests": 0, "retries": 0, "skipped": 0}


class Blocked(Exception):
    pass


def _wait():
    global _last_request
    wait = MIN_INTERVAL - (time.monotonic() - _last_request)
    if wait > 0:
        time.sleep(wait)
    _last_request = time.monotonic()


def fetch(url, accept="text/html"):
    """GET s limitem 1 req/s; retry s exponenciálním čekáním při 429/5xx/síťové chybě. None po 5 neúspěších."""
    for attempt in range(MAX_RETRIES):
        _wait()
        stats["requests"] += 1
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": accept})
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
        time.sleep(2 ** attempt)
    stats["skipped"] += 1
    return None


# ---------- parsování SSR dat (Nuxt devalue) ----------

def nuxt_root(html):
    m = re.search(r'<script[^>]*id="__NUXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
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


def parse_page(html):
    """Vrátí (produkty {productId: dict}, uzly {h-id: {slug, label, count, parent}}) pro danou stránku."""
    root = nuxt_root(html)
    products, nodes = {}, {}
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
                slug, hid = m.group(1), m.group(2)
                nodes.setdefault(hid, {"slug": slug, "label": d.get("label"), "count": d.get("count")})

    walk(root, on_dict)
    return products, nodes


def product_fields(d):
    """Vybere údaje z SSR objektu produktu (vše pochází ze stránky Lidlu)."""
    kf = d.get("keyfacts") or {}
    price = d.get("price") or {}
    bp = (price.get("basePrice") or {}).get("text")
    img = d.get("image")
    if not isinstance(img, str):
        il = d.get("imageList") or []
        img = il[0] if il and isinstance(il[0], str) else None
    return {
        "pid": d["productId"],
        "name": d.get("fullTitle") or kf.get("fullTitle") or kf.get("title"),
        "url": d.get("canonicalUrl"),
        "basePrice": bp,
        "image": img,
        "online_or_store": d.get("online"),
    }


# ---------- velikost balení z dat ----------

PACK_RE = re.compile(r"^(?:(\d+)\s*x\s*)?(\d+(?:[.,]\d+)?)\s*(kg|g|ml|l)$", re.I)
NAME_PACK_RE = re.compile(r"(?:(\d+)\s*x\s*)?(\d+(?:[.,]\d+)?)\s*(kg|g|ml|l)\b", re.I)


def _pack_from(text, regex):
    m = regex.search(text)
    if not m:
        return None
    n = int(m.group(1)) if m.group(1) else 1
    val = float(m.group(2).replace(",", "."))
    unit = m.group(3).lower()
    return n * val, unit


def pack_size(basePrice, name):
    """Vrátí (value, unit) v kg/l, nebo None. Berou se jen explicitní balení (např. „0,5 l“, „3 x 80 g“)."""
    found = None
    if basePrice:
        first = re.split(r";\s|,\s", basePrice, maxsplit=1)[0].strip()
        if "=" not in first:
            found = _pack_from(first, PACK_RE)
    if found is None and name:
        found = _pack_from(name, NAME_PACK_RE)
    if found is None:
        return None
    val, unit = found
    if unit == "g":
        return round(val / 1000, 6), "kg"
    if unit == "kg":
        return round(val, 6), "kg"
    if unit == "ml":
        return round(val / 1000, 6), "l"
    return round(val, 6), "l"


def size_label(value, unit):
    if unit == "kg":
        g = round(value * 1000)
        return f"{g}g" if value < 1 else f"{value:g}kg".replace(".", "-")
    return f"{value:g}l".replace(".", "-")


def slugify(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


EAN_OK = re.compile(r"^\d{8}$|^\d{13}$")


def ean_valid(e):
    if not EAN_OK.match(e):
        return False
    d = [int(c) for c in e]
    body, check = d[:-1], d[-1]
    s = sum(x * (3 if (len(body) - i) % 2 == 1 else 1) for i, x in enumerate(body))
    return (10 - s % 10) % 10 == check


def ean_from_detail(html):
    root = nuxt_root(html)
    if root is None:
        return []
    eans = []

    def on_dict(d):
        if "productId" in d and isinstance(d.get("eans"), list):
            eans.extend(e for e in d["eans"] if isinstance(e, str))

    walk(root, on_dict)
    return sorted({e for e in eans if ean_valid(e)})


# ---------- sběr ----------

def crawl():
    """BFS přes všechny uzly stromu. Vrací (produkty {pid: info}, uzly {h-id: info})."""
    queue = []
    visited = {}
    products = {}
    for hid, slug, cat in ROOTS:
        queue.append((hid, slug, cat, None))

    while queue:
        hid, slug, cat, parent = queue.pop(0)
        if hid in visited or hid in NONFOOD_IDS:
            continue
        url = f"{BASE}/h/{slug}/{hid}"
        html = fetch(url)
        if html is None:
            visited[hid] = {"slug": slug, "cat": cat, "parent": parent, "found": 0, "count": None, "error": True}
            continue
        prods, nodes = parse_page(html)
        own_count = None
        for pid, d in prods.items():
            info = product_fields(d)
            info["cat"] = cat
            info["sources"] = [url]
            if pid in products:
                if url not in products[pid]["sources"]:
                    products[pid]["sources"].append(url)
            else:
                products[pid] = info
        # počet z facetu tohoto uzlu (pokud je v payloadu)
        visited[hid] = {"slug": slug, "cat": cat, "parent": parent, "found": len(prods), "count": own_count}
        print(f"  uzel {hid} {slug}: produktů na stránce {len(prods)}, poduzlů {len(nodes)}, celkem {len(products)}",
              file=sys.stderr)
        for chid, meta in nodes.items():
            if chid != hid and chid not in visited and chid not in NONFOOD_IDS:
                queue.append((chid, meta["slug"], cat, hid))
                visited.setdefault(chid + "_label", {"label": meta.get("label"), "count": meta.get("count")})
    return products, visited


def main():
    tree_only = "--tree" in sys.argv
    try:
        products, nodes = crawl()
    except Blocked as e:
        print(f"Blokace (403) na {e}, končím bez zápisu.", file=sys.stderr)
        sys.exit(2)
    print(f"Uzlů: {len([k for k in nodes if not k.endswith('_label')])}, produktů celkem: {len(products)}, "
          f"požadavků: {stats['requests']}, opakování: {stats['retries']}, přeskočeno: {stats['skipped']}",
          file=sys.stderr)
    if tree_only:
        for k, v in nodes.items():
            if not k.endswith("_label"):
                lab = nodes.get(k + "_label", {}).get("label")
                print(f"{k}\t{v['cat']}\tparent={v['parent']}\tfound={v['found']}\t{lab}\t{v['slug']}")
        return

    records, eans_done = [], 0
    for pid in sorted(products):
        info = products[pid]
        name = info.get("name")
        if not name:
            print(f"  produkt {pid} bez názvu, přeskakuji", file=sys.stderr)
            continue
        if info["cat"] is None:
            continue
        size = pack_size(info.get("basePrice"), name)
        url = BASE + info["url"] if info.get("url") else None
        eans = []
        if url:
            html = fetch(url)
            if html:
                eans = ean_from_detail(html)
                eans_done += 1
        sid_parts = [STORE.lower(), str(pid), slugify(name)]
        if size:
            sid_parts.append(size_label(*size))
        rec = {
            "id": "-".join(sid_parts),
            "name": name,
            "category": info["cat"],
        }
        if size:
            rec["size_value"], rec["size_unit"] = size
        if eans:
            rec["eans"] = eans
        rec["stores"] = [{"store": STORE, "receipt_name": None, "receipt_name_source": None, "url": url}]
        if info.get("image"):
            rec["image_url"] = info["image"]
        rec["sources"] = info["sources"] + ([url] if url else [])
        records.append(rec)

    ids = [r["id"] for r in records]
    assert len(ids) == len(set(ids)), "duplicitní id"
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"Zapsáno {len(records)} záznamů do {OUT}; detailů staženo {eans_done}; "
          f"požadavků celkem {stats['requests']}, přeskočeno {stats['skipped']}", file=sys.stderr)


if __name__ == "__main__":
    main()
