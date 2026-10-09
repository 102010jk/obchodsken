#!/usr/bin/env python3
"""Sběr akčních potravin z kupi.cz (Lidl, Penny) -> data/foods/raw/17-kupi-lidl-penny.jsonl.

Použití:
  python3 data/foods/harvest/17-kupi-lidl-penny.py              # sběr; nové produkty přidá ke starým (sloučí podle id)
  python3 data/foods/harvest/17-kupi-lidl-penny.py --discover   # jen vypíše podkategorie (pro MAP), nic nezapisuje
  python3 data/foods/harvest/17-kupi-lidl-penny.py --cache DIR  # odpovědi stránek ukládá/čte z DIR

Postup: výpis slugů akcí ze všech kategorií (+ stránkování ?page=N) pro každý obchod
-> detail produktu /sleva/<slug> jen u nových slugů (JSON-LD Product + text "najdete v kategorii X a podkategorii Y")
-> kategorie přes MAP (podkategorie kupi -> kategorie FORMAT.md), None = nepotravina / mimo zadání.
Max 1 požadavek za sekundu, 403 = blokace (nic neobcházíme), 429/5xx = exponenciální čekání.
"""
import argparse, hashlib, html, json, os, re, sys, time, urllib.error, urllib.request
from collections import Counter

BASE = "https://www.kupi.cz"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
OUT = os.path.join(ROOT, "data", "foods", "raw", "17-kupi-lidl-penny.jsonl")

STORE_SLUGS = {"lidl": "Lidl", "penny-market": "Penny"}  # slug na kupi.cz -> název obchodu
CATEGORIES = [
    "alkohol", "konzervy", "lahudky", "maso-drubez-a-ryby", "mlecne-vyrobky-a-vejce",
    "mrazene-a-instantni-potraviny", "nealko-napoje", "ovoce-a-zelenina", "pecivo",
    "sladkosti-a-slane-snacky", "vareni-a-peceni", "zdrava-vyziva", "pro-deti",
]
# názvy obchodů z kupi.cz -> sjednocený název (ostatní se nechají, jak jsou)
STORE_NAMES = {"lidl": "Lidl", "penny": "Penny", "penny market": "Penny", "kaufland": "Kaufland",
               "albert": "Albert", "billa": "Billa", "tesco": "Tesco", "globus": "Globus",
               "norma": "Norma", "coop": "Coop", "makro": "Makro"}

# podkategorie kupi.cz (text "a podkategorii X") -> kategorie FORMAT.md; None = nepotravina / mimo zadání.
# Doplňuje se z výstupu --discover.
MAP = {}

DETAIL_LIMIT = None     # None = bez omezení
MIN_INTERVAL = 1.0      # s mezi požadavky (sdílený web, max 1 req/s)
MAX_TRIES = 5           # po 5 neúspěších přeskočit
MAX_PAGES = 60          # pojistka proti nekonečnému stránkování

_last = [0.0]
stats = {"requests": 0, "retries": 0, "failed": 0, "from_cache": 0}


class Blocked(Exception):
    pass


def _cache_path(cache_dir, url):
    return os.path.join(cache_dir, hashlib.sha1(url.encode()).hexdigest() + ".json")


def get_text(url, cache_dir=None):
    """Vrátí HTML stránky, nebo None (404 / vyčerpané pokusy). 403 = blokace -> Blocked (nic neobcházíme)."""
    if cache_dir:
        p = _cache_path(cache_dir, url)
        if os.path.exists(p):
            stats["from_cache"] += 1
            with open(p, encoding="utf-8") as f:
                return json.load(f)["html"]
    for attempt in range(MAX_TRIES):
        wait = MIN_INTERVAL - (time.monotonic() - _last[0])
        if wait > 0:
            time.sleep(wait)
        _last[0] = time.monotonic()
        stats["requests"] += 1
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html,application/xhtml+xml",
                                                       "Accept-Language": "cs-CZ,cs;q=0.9"})
            with urllib.request.urlopen(req, timeout=30) as r:
                body = r.read().decode("utf-8", "replace")
            if cache_dir:
                os.makedirs(cache_dir, exist_ok=True)
                with open(_cache_path(cache_dir, url), "w", encoding="utf-8") as f:
                    json.dump({"html": body}, f, ensure_ascii=False)
            return body
        except urllib.error.HTTPError as e:
            if e.code == 403:
                raise Blocked(f"HTTP 403 na {url}")
            if e.code == 404:
                return None
            err = f"HTTP {e.code}"
        except (urllib.error.URLError, TimeoutError) as e:
            err = type(e).__name__
        stats["retries"] += 1
        print(f"  ! {err}, pokus {attempt + 1}/{MAX_TRIES}: {url[:90]}", file=sys.stderr)
        time.sleep(min(2 ** (attempt + 1), 60))  # exponenciální ústup
    stats["failed"] += 1
    return None


def jsonld(page):
    out = []
    for s in re.findall(r'<script type="application/ld\+json">(.*?)</script>', page, re.S):
        try:
            d = json.loads(s)
        except json.JSONDecodeError:
            continue
        out.extend(d if isinstance(d, list) else [d])
    return out


def plain_text(page):
    page = re.sub(r"(?s)<script.*?</script>|<style.*?</style>", " ", page)
    page = re.sub(r"<[^>]+>", " ", page)
    return re.sub(r"\s+", " ", html.unescape(page))


def listing_slugs(page):
    slugs = []
    for d in jsonld(page):
        if d.get("@type") != "ItemList":
            continue
        for item in d.get("itemListElement") or []:
            m = re.fullmatch(r"https://www\.kupi\.cz/sleva/([^/?#]+)", item.get("url") or "")
            if m:
                slugs.append(m.group(1))
    return slugs


def crawl_listing(store_slug, cat, cache_dir):
    slugs, seen = [], set()
    for page in range(1, MAX_PAGES + 1):
        url = f"{BASE}/slevy/{cat}/{store_slug}" + ("" if page == 1 else f"?page={page}")
        h = get_text(url, cache_dir)
        if h is None:
            break
        new = [s for s in listing_slugs(h) if s not in seen]
        if not new:  # prázdná stránka nebo samé duplicity -> konec
            break
        seen.update(new)
        slugs.extend(new)
    return slugs


def norm_store(name):
    name = (name or "").strip()
    return STORE_NAMES.get(name.lower(), name)


def offer_stores(prod):
    """Názvy obchodů z offers[].offeredBy (offers může být AggregateOffer s vnořeným seznamem, nebo seznam)."""
    offers = prod.get("offers") or []
    if isinstance(offers, dict):
        offers = offers.get("offers") or [offers]
    names = []
    for o in offers:
        ob = o.get("offeredBy")
        if isinstance(ob, dict):
            ob = ob.get("name")
        if ob:
            n = norm_store(ob)
            if n not in names:
                names.append(n)
    return names


def norm_size(num, unit):
    v, u = float(num.replace(",", ".")), unit.lower()
    if u == "g":
        v, u = v / 1000, "kg"
    elif u == "ml":
        v, u = v / 1000, "l"
    elif u == "cl":
        v, u = v / 100, "l"
    if v <= 0 or (u == "ks" and not float(v).is_integer()):
        return None
    v = round(v, 3)
    return (int(v) if float(v).is_integer() else v), u


SIZE_RE = r"(\d+(?:[.,]\d+)?)\s*(kg|g|ml|cl|l|ks)(?!\w)"


def find_size(name, text):
    """Velikost jen když je v textu stránky (u názvu nebo v nabídce) jednoznačná; jinak None."""
    cands = set()
    for m in re.finditer(re.escape(name) + r"\s*/?\s*" + SIZE_RE, text, re.I):
        s = norm_size(m.group(1), m.group(2))
        if s:
            cands.add(s)
    if not cands:
        m = re.search(r"(\d+(?:[.,]\d+)?)\s*(kg|g|ml|cl|l)\s*$", name, re.I)
        if m and norm_size(m.group(1), m.group(2)):
            cands.add(norm_size(m.group(1), m.group(2)))
    return cands.pop() if len(cands) == 1 else None


def parse_product(slug, h):
    prods = [d for d in jsonld(h) if d.get("@type") == "Product"]
    if not prods:
        return None
    p = prods[0]
    name = (p.get("name") or "").strip()
    text = plain_text(h)
    m = re.search(r"najdete v kategorii (.+?) a podkategorii (.+?)\s*\.", text)
    brand = p.get("brand")
    if isinstance(brand, dict):
        brand = brand.get("name")
    image = p.get("image")
    if isinstance(image, list):
        image = image[0] if image else None
    return {
        "name": name,
        "brand": brand.strip() if isinstance(brand, str) and brand.strip() else None,
        "image": image if isinstance(image, str) else None,
        "stores": offer_stores(p),
        "subcat": m.group(2).strip() if m else None,
        "size": find_size(name, text) if name else None,
    }


def build_record(slug, info):
    rec = {"id": f"kupi-{slug}", "name": info["name"]}
    if info["brand"]:
        rec["brand"] = info["brand"]
    rec["category"] = MAP[info["subcat"]]
    if info["size"]:
        rec["size_value"], rec["size_unit"] = info["size"]
    rec["stores"] = [{"store": s, "receipt_name": None, "receipt_name_source": None, "url": None}
                     for s in info["stores"]]
    if info["image"]:
        rec["image_url"] = info["image"]
    rec["sources"] = [f"{BASE}/sleva/{slug}"]
    return rec


def load_existing(path):
    recs = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    r = json.loads(line)
                    recs[r["id"]] = r
    return recs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--discover", action="store_true", help="vypíše podkategorie a počty, nic nezapisuje")
    ap.add_argument("--cache", metavar="DIR", help="cache odpovědí stránek")
    args = ap.parse_args()

    # 1) výpis akcí: slug -> obchody, kde je v akci (podle listingu)
    membership, order = {}, []
    for store_slug, store_name in STORE_SLUGS.items():
        for cat in CATEGORIES:
            slugs = crawl_listing(store_slug, cat, args.cache)
            print(f"{store_name} / {cat}: {len(slugs)} akcí", file=sys.stderr)
            for s in slugs:
                if not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", s):
                    continue  # id musí být slug; nestandardní URL přeskočit
                if s not in membership:
                    membership[s] = []
                    order.append(s)
                if store_name not in membership[s]:
                    membership[s].append(store_name)
    print(f"unikátních produktů v akci: {len(order)}", file=sys.stderr)

    # 2) detaily: u --discover všechny, jinak jen nové (produkty, které už máme, znovu nestahujeme)
    existing = {} if args.discover else load_existing(OUT)
    todo = [s for s in order if args.discover or f"kupi-{s}" not in existing]
    if DETAIL_LIMIT:
        todo = todo[:DETAIL_LIMIT]
    details = {}
    for i, s in enumerate(todo, 1):
        h = get_text(f"{BASE}/sleva/{s}", args.cache)
        if h is None:
            continue
        info = parse_product(s, h)
        if info:
            details[s] = info
        if i % 50 == 0:
            print(f"  detaily {i}/{len(todo)}", file=sys.stderr)

    if args.discover:
        cnt = Counter(d["subcat"] for d in details.values())
        print("\npodkategorie | počet | mapováno na | příklad", file=sys.stderr)
        for sub, n in cnt.most_common():
            ex = next(d["name"] for d in details.values() if d["subcat"] == sub)
            print(f"{sub!r} | {n} | {MAP.get(sub, 'NEZMAPOVÁNO') if sub else '-'} | {ex}", file=sys.stderr)
        print(f"\nproduktů s detailem: {len(details)}, požadavků: {stats['requests']}, "
              f"selhání: {stats['failed']}", file=sys.stderr)
        return

    # 3) sloučení: staré záznamy dostanou případné nové obchody z výpisu, nové se přidají
    skipped = Counter()
    for s in order:
        key = f"kupi-{s}"
        if key in existing:
            rec = existing[key]
            have = {x["store"] for x in rec["stores"]}
            for st in membership[s]:
                if st not in have:
                    rec["stores"].append({"store": st, "receipt_name": None, "receipt_name_source": None, "url": None})
            continue
        info = details.get(s)
        if info is None:
            skipped["bez detailu"] += 1
            continue
        if not info["stores"]:
            skipped["bez obchodu v offers"] += 1
            continue
        if info["subcat"] not in MAP or MAP[info["subcat"]] is None:
            skipped[f"nezmapováno/nepotravina: {info['subcat']}"] += 1
            continue
        for st in membership[s]:
            if st not in info["stores"]:
                info["stores"].append(st)
        existing[key] = build_record(s, info)

    rows = list(existing.values())
    ids = [r["id"] for r in rows]
    if len(ids) != len(set(ids)):
        sys.exit("CHYBA: duplicitní id")
    tmp = OUT + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    os.replace(tmp, OUT)

    print(f"zapsáno {len(rows)} záznamů -> {OUT}", file=sys.stderr)
    print(f"přeskočeno: {dict(skipped)}", file=sys.stderr)
    print(f"požadavků: {stats['requests']}, opakování: {stats['retries']}, "
          f"selhané (přeskočeno): {stats['failed']}, z cache: {stats['from_cache']}", file=sys.stderr)


if __name__ == "__main__":
    try:
        main()
    except Blocked as e:
        sys.exit(f"ZASTAVENO: {e}. Blokaci neobcházím, výstup nebyl přepsán.")
