#!/usr/bin/env python3
"""Hromadný sběr potravin Globus.cz -> data/foods/raw/14-globus.jsonl

Zdroje (jen web obchodu):
  1. Sitemapa (sitemap.xml -> sitemaps/01-sitemap.xml): produktové stránky celé nabídky
     /globus/hypermarket/cela-nabidka/p/<slug>-<vanr>. Z každé stránky se vytáhne produkt
     z __NUXT_DATA__ (název, značka, velikost, EAN, fotka, kategorie z placements).
  2. Akční nabídka: JSON API /api/v1/gsoa/actionOffers/houses/4005/actionProductsCatalog
     (pobočka Praha-Čakovice, gsoaId 4005), stránkování page/pageSize=100.

Limity: max 1 požadavek za sekundu; 429/5xx/síť -> exponenciální čekání (4, 8, 16, 32, 64 s),
po 5 neúspěšných pokusech se stránka přeskočí (příští běh ji zkusí znovu). 403 zastaví běh.

Cache (průběžná, navazuje se na ni): data/foods/harvest/cache/14-globus/
  products.jsonl  jeden řádek na URL stránky (status ok / nohp / 404)
  akce.json       poslední stažení akční nabídky
  urls.txt        URL produktových stránek ze sitemapy
  unmapped.txt    (dept, kategorie) bez mapování + počty vyřazených

Použití:
  python3 data/foods/harvest/14-globus.py               # stáhne, co chybí, a zapíše výstup
  python3 data/foods/harvest/14-globus.py --build       # jen přepíše výstup z cache
  python3 data/foods/harvest/14-globus.py --limit 100   # test: nejvýš 100 nových stránek
  python3 data/foods/harvest/14-globus.py --refresh-sitemap
"""
import argparse, datetime, json, os, re, subprocess, sys, time, unicodedata
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
CACHE = os.path.join(HERE, "cache", "14-globus")
OUT = os.path.join(ROOT, "data", "foods", "raw", "14-globus.jsonl")
PRODUCTS = os.path.join(CACHE, "products.jsonl")
AKCE = os.path.join(CACHE, "akce.json")
URLS = os.path.join(CACHE, "urls.txt")
UNMAPPED = os.path.join(CACHE, "unmapped.txt")
LOG = os.path.join(CACHE, "harvest.log")

UA = "Mozilla/5.0"
MIN_GAP = 1.0          # sekund mezi požadavky (max 1 req/s)
HOUSE = 4005           # Praha-Čakovice
AKCE_URL = "https://www.globus.cz/globus/hypermarket/akcni-nabidka/"
SITEMAP_INDEX = "https://www.globus.cz/sitemap.xml"
PRODUCT_MARK = "/globus/hypermarket/cela-nabidka/p/"
AKCE_API = "https://www.globus.cz/api/v1/gsoa/actionOffers/houses/%d/actionProductsCatalog?page=%d&pageSize=100" % (HOUSE, 0)


class Stop(Exception):
    pass


def log(msg):
    line = "%s %s" % (datetime.datetime.now().strftime("%H:%M:%S"), msg)
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


# ---------- síť ----------
_last = [0.0]


def throttle():
    wait = MIN_GAP - (time.monotonic() - _last[0])
    if wait > 0:
        time.sleep(wait)
    _last[0] = time.monotonic()


def fetch(url, accept="text/html"):
    """Vrátí (200, text) nebo (404, None) nebo (None, None) po 5 neúspěšných opakováních."""
    body_path = os.path.join(CACHE, "_body.tmp")
    for attempt in range(6):  # 1 pokus + 5 opakování
        throttle()
        r = subprocess.run(["curl", "-sS", "-L", "-A", UA, "-H", "Accept: " + accept,
                            "-o", body_path, "-w", "%{http_code}", url],
                           capture_output=True, text=True)
        code = r.stdout.strip() if r.returncode == 0 else "000"
        if code == "200":
            with open(body_path, encoding="utf-8") as f:
                return 200, f.read()
        if code == "404":
            return 404, None
        if code == "403":
            raise Stop("403 na %s - web blokuje, neobcházím" % url)
        if attempt < 5:
            wait = min(300, 2 ** (attempt + 2))
            log("  %s pro %s, pokus %d, čekám %d s" % (code, url, attempt + 1, wait))
            time.sleep(wait)
    log("  VZDÁNO po 5 opakováních: %s" % url)
    return None, None


# ---------- NUXT / JSON ----------
def unflatten(d):
    memo = {}

    def rev(i):
        if isinstance(i, bool) or not isinstance(i, int) or i < 0 or i >= len(d):
            return i
        if i in memo:
            return memo[i]
        v = d[i]
        if isinstance(v, dict):
            r = {}
            memo[i] = r
            for k, x in v.items():
                r[k] = rev(x)
            return r
        if isinstance(v, list):
            r = []
            memo[i] = r
            for x in v:
                r.append(rev(x))
            return r
        memo[i] = v
        return v
    return rev(0)


def find_product(node, vanr_hint=None):
    """Najde objekt produktu (klíč 'product-<vanr>' s položkou vanr)."""
    found = []

    def walk(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if isinstance(k, str) and k.startswith("product-") and isinstance(v, dict) and "vanr" in v:
                    found.append(v)
                else:
                    walk(v)
        elif isinstance(o, list):
            for x in o:
                walk(x)
    walk(node)
    if not found:
        return None
    if vanr_hint:
        for p in found:
            if p.get("vanr") == vanr_hint:
                return p
    return found[0]


def product_from_html(html, url):
    m = re.search(r'<script[^>]*id="__NUXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
    if not m:
        return None
    hint = re.search(r"-(\d{11,})$", url)
    return find_product(unflatten(json.loads(m.group(1))), hint.group(1) if hint else None)


def slim(p, url):
    pit = p.get("productInHouse") or {}
    return {
        "vanr": p.get("vanr"),
        "name": (p.get("name") or "").strip(),
        "brand": (p.get("brand") or {}).get("name"),
        "size": p.get("sellUnitSizeText"),
        "ean": p.get("ean") or [],
        "img": p.get("imgDetail"),
        "placements": [{k: x.get(k) for k in ("department", "category", "subcategory")}
                       for x in (pit.get("placements") or [])],
        "cats": p.get("productCategories") or [],
        "url": url,
    }


# ---------- sběr ----------
def load_urls():
    if not os.path.exists(URLS):
        return None
    with open(URLS, encoding="utf-8") as f:
        return [l.strip() for l in f if l.strip()]


def fetch_urls(refresh=False):
    urls = None if refresh else load_urls()
    if urls is not None:
        return urls
    status, idx = fetch(SITEMAP_INDEX, accept="application/xml")
    if status != 200:
        raise Stop("nelze stáhnout sitemap.xml (%s)" % status)
    sitemaps = re.findall(r"<loc>([^<]+)</loc>", idx)
    urls = []
    for sm in sitemaps:
        st, body = fetch(sm, accept="application/xml")
        if st != 200:
            raise Stop("nelze stáhnout %s (%s)" % (sm, st))
        urls += [u for u in re.findall(r"<loc>([^<]+)</loc>", body) if PRODUCT_MARK in u]
    urls = sorted(set(urls))
    with open(URLS, "w", encoding="utf-8") as f:
        f.write("\n".join(urls) + "\n")
    log("sitemapa: %d produktových URL" % len(urls))
    return urls


def load_done():
    done = set()
    if os.path.exists(PRODUCTS):
        with open(PRODUCTS, encoding="utf-8") as f:
            for line in f:
                try:
                    done.add(json.loads(line)["url"])
                except Exception:
                    pass
    return done


def harvest_products(limit, refresh_sitemap):
    urls = fetch_urls(refresh_sitemap)
    done = load_done()
    todo = [u for u in urls if u not in done]
    log("stránek celkem %d, hotovo %d, zbývá %d" % (len(urls), len(done), len(todo)))
    if limit:
        todo = todo[:limit]
    n = 0
    t0 = time.monotonic()
    with open(PRODUCTS, "a", encoding="utf-8") as f:
        for u in todo:
            status, html = fetch(u)
            if status is None:
                continue  # neúspěch -> příští běh zkusí znovu
            if status == 404:
                rec = {"url": u, "status": "404"}
            else:
                p = product_from_html(html, u)
                if not p or not p.get("vanr"):
                    rec = {"url": u, "status": "nohp"}
                else:
                    rec = dict(status="ok", **slim(p, u))
                    rec["url"] = u
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            f.flush()
            n += 1
            if n % 100 == 0:
                rate = n / max(1.0, time.monotonic() - t0)
                log("staženo %d (zbývá %d), %.2f stránek/s" % (n, len(todo) - n, rate))
    log("produkty: staženo nově %d" % n)


def harvest_akce():
    products, page = [], 1
    while True:
        url = AKCE_API.replace("page=0", "page=%d" % page)
        status, body = fetch(url, accept="application/json")
        if status != 200:
            log("akce: stránka %d nedostupná (%s), přerušuji" % (page, status))
            return
        d = json.loads(body)
        items = d.get("products") or []
        products += [slim(p, None) for p in items]
        if not d.get("paginationShowMore") or not items:
            break
        page += 1
    with open(AKCE, "w", encoding="utf-8") as f:
        json.dump({"fetched": datetime.date.today().isoformat(), "total": len(products),
                   "products": products}, f, ensure_ascii=False)
    log("akce: staženo %d položek (%d stránek)" % (len(products), page))


# ---------- kategorie ----------
def norm(s):
    s = unicodedata.normalize("NFKD", (s or "").lower())
    return "".join(c for c in s if not unicodedata.combining(c)).strip()


def map_placement(dept, cat, sub):
    """Vrátí kategorii FORMAT.md, nebo None (nepotravina / neznámé)."""
    d, c, s = norm(dept), norm(cat), norm(sub)
    txt = c + " " + s
    if d in ("cerstve potraviny", "zdravy svet"):
        if d == "zdravy svet" and "trvanl" in c:
            return map_dry(txt)
        if d == "zdravy svet" and "cerstv" not in c:
            return None
        if "mrazen" in txt:
            return "MRAZENE"
        if "pecivo" in txt or "pekar" in txt:
            return "PECIVO"
        if "ovoce" in txt or "zelenin" in txt:
            return "OVOCE_ZELENINA"
        if "vejce" in txt:
            return "VEJCE"
        if any(k in txt for k in ("uzenin", "salam", "sunk", "parek", "parky", "klobas")):
            return "UZENINY"
        if any(k in txt for k in ("maso", "ryb", "drubez", "kure", "hovez", "vepr", "losos")):
            return "MASO_RYBY"
        if any(k in txt for k in ("mlec", "syr", "jogurt", "smetan", "tvaroh", "maslo", "kefir", "mleko")):
            return "MLECNE"
        return "OSTATNI"
    if d == "trvanlive potraviny":
        return map_dry(txt)
    if d == "pekarstvi":
        return "PECIVO"
    if d == "ovoce a zelenina":
        return "OVOCE_ZELENINA"
    if d == "napojove centrum":
        if any(k in txt for k in ("piva", "pivo", "vino", "vina", "lihovin", "alkohol", "sekt", "whisky",
                                  "vodk", "becherovk", "likér", "liker", "gin", "rum")):
            return "ALKOHOL"
        return "NAPOJE"
    if d == "svet zvirat":
        return "ZVIRATA" if "krmiv" in txt else None
    return None


def map_dry(txt):
    if any(k in txt for k in ("sladk", "cukrov", "cokolad", "bonbon", "zvykov", "dezert")):
        return "SLADKOSTI"
    return "TRVANLIVE"


def categorize(placements, unmapped, excluded):
    for pl in placements:
        cat = map_placement(pl.get("department"), pl.get("category"), pl.get("subcategory"))
        if cat:
            return cat
    if placements:
        for pl in placements:
            unmapped[(pl.get("department"), pl.get("category"), pl.get("subcategory"))] += 1
        excluded["nemapováno/nepotravina: " + str(placements[0].get("department"))] += 1
    else:
        excluded["bez údaje o kategorii"] += 1
    return None


# ---------- výstup ----------
INTERNAL_PREFIX = ("2", "02", "04")  # interní / vážené kódy obchodu, nejsou EAN


def eans_of(lst):
    if not lst or len(lst) > 10:
        return []
    out = []
    for e in lst:
        if not isinstance(e, str) or not re.fullmatch(r"\d{8}|\d{13}", e):
            continue
        if e.startswith(INTERNAL_PREFIX):
            continue
        d = [int(c) for c in e]
        body, check = d[:-1], d[-1]
        s = sum(x * (3 if (len(body) - i) % 2 == 1 else 1) for i, x in enumerate(body))
        if (10 - s % 10) % 10 != check or e in out:
            continue
        out.append(e)
    return out


def size_of(txt):
    if not txt:
        return None, None
    t = txt.strip().lower()
    if "x" in t:  # vícenásobné balení – celkovou velikost nelze spolehlivě určit
        return None, None
    m = re.fullmatch(r"(\d+(?:[.,]\d+)?)\s*(g|kg|ml|l|ks)", t)
    if not m:
        return None, None
    v = float(m.group(1).replace(",", "."))
    u = m.group(2)
    if u == "g":
        return round(v / 1000, 6), "kg"
    if u == "ml":
        return round(v / 1000, 6), "l"
    return v, u


def slugify(s):
    s = norm(s)
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-") or "produkt"


def build():
    if not os.path.exists(PRODUCTS):
        raise Stop("chybí cache %s – nejdřív spusť sběr" % PRODUCTS)
    items = {}  # vanr -> dict(slim, cela_url, akce)
    with open(PRODUCTS, encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            if r.get("status") != "ok" or not r.get("vanr"):
                continue
            items.setdefault(r["vanr"], {"p": r, "cela": r["url"], "akce": False})
    if os.path.exists(AKCE):
        akce = json.load(open(AKCE, encoding="utf-8"))
        for p in akce["products"]:
            if not p.get("vanr"):
                continue
            if p["vanr"] in items:
                items[p["vanr"]]["akce"] = True
            else:
                items[p["vanr"]] = {"p": p, "cela": None, "akce": True}

    unmapped, excluded = Counter(), Counter()
    recs = []
    for vanr in sorted(items):
        it = items[vanr]
        p = it["p"]
        name = p.get("name") or ""
        if not name:
            excluded["bez názvu"] += 1
            continue
        cat = categorize(p.get("placements") or [], unmapped, excluded)
        if not cat:
            continue
        rec = {"id": "globus-%s-%s" % (vanr, slugify(name)), "name": name, "category": cat}
        b = p.get("brand")
        if b and b != "None":
            rec["brand"] = b
        sv, su = size_of(p.get("size"))
        if sv is not None:
            rec["size_value"], rec["size_unit"] = sv, su
        e = eans_of(p.get("ean"))
        if e:
            rec["eans"] = e
        store_url = it["cela"] or AKCE_URL
        rec["stores"] = [{"store": "Globus", "receipt_name": None, "receipt_name_source": None, "url": store_url}]
        if p.get("img"):
            rec["image_url"] = p["img"]
        sources = []
        if it["cela"]:
            sources.append(it["cela"])
        if it["akce"]:
            sources.append(AKCE_URL)
        rec["sources"] = sources
        recs.append(rec)

    tmp = OUT + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    os.replace(tmp, OUT)
    with open(UNMAPPED, "w", encoding="utf-8") as f:
        f.write("# nemapované (department, category, subcategory): počet\n")
        for k, v in unmapped.most_common():
            f.write("%d\t%s\n" % (v, " | ".join(str(x) for x in k)))
        f.write("\n# vyřazeno:\n")
        for k, v in excluded.most_common():
            f.write("%d\t%s\n" % (v, k))
    log("výstup: %d záznamů -> %s (unikátních produktů v cache: %d)" % (len(recs), OUT, len(items)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", action="store_true", help="jen přepiš výstup z cache")
    ap.add_argument("--limit", type=int, default=0, help="nejvýš N nových produktových stránek")
    ap.add_argument("--refresh-sitemap", action="store_true")
    ap.add_argument("--skip-akce", action="store_true")
    args = ap.parse_args()
    os.makedirs(CACHE, exist_ok=True)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    try:
        if not args.build:
            if not args.skip_akce:
                harvest_akce()
            harvest_products(args.limit, args.refresh_sitemap)
        build()
    except Stop as e:
        log("ZASTAVENO: %s" % e)
        if not args.build:
            build()
        sys.exit(2)


if __name__ == "__main__":
    main()
