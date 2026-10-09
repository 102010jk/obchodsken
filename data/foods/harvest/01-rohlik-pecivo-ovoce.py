#!/usr/bin/env python3
"""Hromadný sběr potravin z Rohlík.cz -> data/foods/raw/01-rohlik-pecivo-ovoce.jsonl (přepíše výstup).

Použití:
  python3 data/foods/harvest/01-rohlik-pecivo-ovoce.py              # plný sběr
  python3 data/foods/harvest/01-rohlik-pecivo-ovoce.py --discover   # jen vypíše podkategorie (pro MAP)
  python3 data/foods/harvest/01-rohlik-pecivo-ovoce.py --cache DIR  # odpovědi API ukládá/čte z DIR

Postup: výpis ID ze všech stránek 5 kategorií -> detaily po dávkách (products?products=...)
-> kategorie z mainCategoryId přes MAP -> záznamy dle FORMAT.md. Max 1 požadavek za sekundu.
"""
import argparse, hashlib, json, os, re, sys, time, unicodedata, urllib.error, urllib.request

API = "https://www.rohlik.cz/api/v1"
UA = "Mozilla/5.0"
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
OUT = os.path.join(ROOT, "data", "foods", "raw", "01-rohlik-pecivo-ovoce.jsonl")

CATEGORIES = [
    300101000,  # Pekárna a cukrárna
    300102000,  # Ovoce a zelenina
    300124876,  # Máme navařeno – hotová jídla
    300112393,  # Speciální výživa (jen potraviny)
    300110000,  # Dítě (jen dětské potraviny a nápoje)
]
DETAIL_BATCH = 40
MIN_INTERVAL = 1.0      # s mezi požadavky (sdílený web, max 1 req/s)
MAX_TRIES = 5           # po 5 neúspěších přeskočit
PAGE_LIMIT = 100

# mainCategoryId (podkategorie Rohlíku) -> kategorie FORMAT.md, None = nepotravina / mimo zadání.
# Doplňuje se z výstupu --discover.
MAP = {}

_last = [0.0]
stats = {"requests": 0, "retries": 0, "failed": 0, "from_cache": 0}


class Blocked(Exception):
    pass


def _cache_path(cache_dir, url):
    return os.path.join(cache_dir, hashlib.sha1(url.encode()).hexdigest() + ".json")


def get_json(url, cache_dir=None):
    """Vrátí JSON, nebo None (404 / vyčerpané pokusy). 403 = blokace -> Blocked (nic neobcházíme)."""
    if cache_dir:
        p = _cache_path(cache_dir, url)
        if os.path.exists(p):
            stats["from_cache"] += 1
            with open(p, encoding="utf-8") as f:
                return json.load(f)
    for attempt in range(MAX_TRIES):
        wait = MIN_INTERVAL - (time.monotonic() - _last[0])
        if wait > 0:
            time.sleep(wait)
        _last[0] = time.monotonic()
        stats["requests"] += 1
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=30) as r:
                data = json.loads(r.read().decode("utf-8"))
            if cache_dir:
                os.makedirs(cache_dir, exist_ok=True)
                with open(_cache_path(cache_dir, url), "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False)
            return data
        except urllib.error.HTTPError as e:
            if e.code == 403:
                raise Blocked(f"HTTP 403 na {url}")
            if e.code == 404:
                return None
            err = f"HTTP {e.code}"
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            err = type(e).__name__
        stats["retries"] += 1
        print(f"  ! {err}, pokus {attempt + 1}/{MAX_TRIES}: {url[:90]}", file=sys.stderr)
        time.sleep(min(2 ** (attempt + 1), 60))  # exponenciální ústup
    stats["failed"] += 1
    return None


def list_category(cat, cache_dir):
    ids, seen = [], set()
    for page in range(500):
        d = get_json(f"{API}/categories/normal/{cat}/products?limit={PAGE_LIMIT}&page={page}", cache_dir)
        if not d:
            break
        new = [i for i in d.get("productIds") or [] if i not in seen]
        if not new:  # prázdná stránka nebo samé duplicity -> konec
            break
        seen.update(new)
        ids.extend(new)
    print(f"kategorie {cat}: {len(ids)} ID ({page} stránek)", file=sys.stderr)
    return ids


def fetch_details(ids, cache_dir):
    out = {}
    for i in range(0, len(ids), DETAIL_BATCH):
        chunk = ids[i:i + DETAIL_BATCH]
        q = "&".join(f"products={x}" for x in chunk)
        d = get_json(f"{API}/products?{q}", cache_dir)
        if d is None:
            continue
        for p in d:
            out[p["id"]] = p
    return out


def category_name(mc, cache_dir):
    d = get_json(f"{API}/categories/normal/{mc}", cache_dir)
    return (d or {}).get("name")


def slug(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def parse_size(p):
    """Velikost z textualAmount; vážené zboží nebo 'cca' v názvu -> None."""
    if p.get("weightedItem") or "cca" in p["name"].lower() or "cca" in (p.get("textualAmount") or "").lower():
        return None, None
    t = (p.get("textualAmount") or "").strip().lower().replace(",", ".")
    m = re.fullmatch(r"(\d+)\s*[x×]\s*(\d+(?:\.\d+)?)\s*(g|kg|ml|l)", t)  # 2 x 250 g -> celkem
    if m:
        v, u = int(m.group(1)) * float(m.group(2)), m.group(3)
    else:
        m = re.fullmatch(r"(\d+(?:\.\d+)?)\s*(g|kg|ml|l|ks)", t)
        if not m:
            return None, None
        v, u = float(m.group(1)), m.group(2)
    if u == "g":
        v, u = v / 1000, "kg"
    elif u == "ml":
        v, u = v / 1000, "l"
    if u == "ks" and not float(v).is_integer():
        return None, None
    v = round(v, 3)
    return (int(v) if float(v).is_integer() else v), u


def build_record(p, category):
    url = f"https://www.rohlik.cz/{p['id']}-{p['slug']}"
    rec = {"id": f"rohlik-{p['id']}-{slug(p['slug'])}", "name": p["name"]}
    brand = p.get("brand")
    if brand and brand not in ("None", "-"):
        rec["brand"] = brand
    rec["category"] = category
    sv, su = parse_size(p)
    if sv is not None:
        rec["size_value"], rec["size_unit"] = sv, su
    rec["stores"] = [{"store": "Rohlík", "receipt_name": None, "receipt_name_source": None, "url": url}]
    if p.get("images"):
        rec["image_url"] = p["images"][0]
    rec["sources"] = [url]
    return rec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--discover", action="store_true", help="vypíše názvy všech podkategorií, nic nezapisuje")
    ap.add_argument("--cache", metavar="DIR", help="cache odpovědí API")
    args = ap.parse_args()

    ids = []
    for cat in CATEGORIES:
        for i in list_category(cat, args.cache):
            if i not in ids:
                ids.append(i)
    print(f"celkem unikátních ID: {len(ids)}", file=sys.stderr)

    details = fetch_details(ids, args.cache)
    print(f"detaily: {len(details)} produktů", file=sys.stderr)

    skipped = {"archived_or_type": 0, "non_food": 0, "unmapped": 0}
    by_mc, rows = {}, []
    for pid in ids:
        p = details.get(pid)
        if p is None:
            continue
        if p.get("archived") or p.get("type") != "PRODUCT":
            skipped["archived_or_type"] += 1
            continue
        mc = p.get("mainCategoryId")
        by_mc[mc] = by_mc.get(mc, 0) + 1
        if args.discover or mc not in MAP:
            skipped["unmapped"] += 1
            continue
        if MAP[mc] is None:
            skipped["non_food"] += 1
            continue
        rows.append(build_record(p, MAP[mc]))

    if args.discover:
        print("\nmainCategoryId | počet | název (Rohlík)", file=sys.stderr)
        for mc, n in sorted(by_mc.items(), key=lambda x: (x[0] or 0)):
            print(f"{mc} | {n} | {category_name(mc, args.cache)}", file=sys.stderr)
        print(f"\nrequestů: {stats['requests']}, selhání: {stats['failed']}", file=sys.stderr)
        return

    ids_out = [r["id"] for r in rows]
    if len(ids_out) != len(set(ids_out)):
        sys.exit("CHYBA: duplicitní id")
    tmp = OUT + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    os.replace(tmp, OUT)

    unmapped_names = {mc: category_name(mc, args.cache) for mc in by_mc if mc not in MAP}
    if unmapped_names:
        print(f"nezmapované podkategorie (přeskočeny): {unmapped_names}", file=sys.stderr)
    print(f"zapsáno {len(rows)} záznamů -> {OUT}", file=sys.stderr)
    print(f"přeskočeno: {skipped}", file=sys.stderr)
    print(f"požadavků: {stats['requests']}, opakování: {stats['retries']}, "
          f"selhané (přeskočeno): {stats['failed']}, z cache: {stats['from_cache']}", file=sys.stderr)


if __name__ == "__main__":
    try:
        main()
    except Blocked as e:
        sys.exit(f"ZASTAVENO: {e}. Blokaci neobcházím, výstup nebyl přepsán.")
