#!/usr/bin/env python3
"""Hromadný sběr: kupi.cz – potraviny v akci u obchodů Globus, Norma, Coop, Makro, CBA, Hruška, Flop, JIP.

Výstup: data/foods/raw/20-kupi-ostatni.jsonl. Existující záznamy (stejné id) se nechávají být – produkt, který už
máme, se znovu nestahuje. Spuštění z kteréhokoli adresáře:
    python3 data/foods/harvest/20-kupi-ostatni.py            # celý sběr (nové produkty se přidají ke starým)
    python3 data/foods/harvest/20-kupi-ostatni.py --dry-run  # jen počty z listingů, bez stahování detailů

Jak kupi.cz funguje:
- /slevy/<kategorie>/<obchod>[?page=N]  – akce obchodu v kategorii, JSON-LD ItemList (url produktu), 18 na stránku.
- /sleva/<slug>                          – JSON-LD Product: offers[].offeredBy = VŠECHNY obchody, kde je produkt v akci;
  v textu „Tento výrobek najdete v kategorii X a podkategorii Y“; velikost v „discount_amount“ (např. „/ 680 g“).
Produkt se stáhne jednou a sdílí se mezi obchody. Produkty bez obchodu v offers se vynechají.

Šetrnost: max 1 požadavek za sekundu (celkem přes všechny dotazy), User-Agent běžného prohlížeče, při 429/5xx
exponenciální čekání, po 5 neúspěších dotaz přeskočit. Při 403 se sběr zastaví a zapíše se to, co je staženo
(blokaci neobcházíme).
"""
import json
import os
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "data/foods/raw/20-kupi-ostatni.jsonl"

BASE = "https://www.kupi.cz"
# slug na kupi.cz -> název obchodu (jak ho uvádí FORMAT.md)
OBCHODY = {
    "globus": "Globus", "norma": "Norma", "coop": "Coop", "makro": "Makro",
    "cba": "CBA", "hruska": "Hruška", "flop": "Flop", "jip": "JIP",
}
# kategorie potravin na kupi.cz (nepotraviny vynechat; pro-deti jen dětské potraviny – filtr níže)
KATEGORIE = [
    "alkohol", "konzervy", "lahudky", "maso-drubez-a-ryby", "mlecne-vyrobky-a-vejce",
    "mrazene-a-instantni-potraviny", "nealko-napoje", "ovoce-a-zelenina", "pecivo",
    "sladkosti-a-slane-snacky", "vareni-a-peceni", "zdrava-vyziva", "pro-deti",
]
MIN_INTERVAL = 1.0      # sekund mezi požadavky, celkem přes všechny dotazy
MAX_RETRIES = 5
MAX_PAGES = 60
SAVE_EVERY = 25
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"

CANON_STORES = ["Lidl", "Kaufland", "Albert", "Billa", "Penny", "Tesco", "Globus", "Rohlík", "Košík",
                "Makro", "Norma", "Coop", "CBA", "Hruška", "Flop", "JIP"]

LD_RE = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.S)
PRODUCT_URL = re.compile(r"^https://www\.kupi\.cz/sleva/([^/?#\s]+)$")
SLUG_RE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
SUBCAT_RE = re.compile(
    r'kategorii <a href="/slevy/([^"?#]+)"[^>]*>[^<]*</a>(?:\s*a podkategorii <a href="/slevy/([^"?#]+)")?',
    re.S)
SIZE_RE = re.compile(r'discount_amount">\s*/\s*(\d+(?:[.,]\d+)?)\s*(kg|g|ml|cl|l|ks)\b')

_last_request = 0.0
stats = {"requests": 0, "retries": 0, "failed": 0}
mapping = Counter()   # (rodič, podkategorie, kategorie) -> počet, pro kontrolu mapování


class Blocked(Exception):
    pass


# ---------- stahování ----------

def _wait():
    global _last_request
    wait = MIN_INTERVAL - (time.monotonic() - _last_request)
    if wait > 0:
        time.sleep(wait)
    _last_request = time.monotonic()


def fetch(url):
    """GET s limitem 1 req/s. Vrací (text, konečná_url), nebo (None, None) při 404 / trvalé chybě. 403 -> Blocked."""
    for attempt in range(MAX_RETRIES):
        _wait()
        stats["requests"] += 1
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": UA,
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "cs-CZ,cs;q=0.9",
            })
            with urllib.request.urlopen(req, timeout=40) as resp:
                return resp.read().decode("utf-8", errors="replace"), resp.geturl()
        except urllib.error.HTTPError as e:
            if e.code == 403:
                raise Blocked(url)
            if e.code == 404:
                print(f"  404, přeskakuji: {url}", file=sys.stderr)
                return None, None
            if not (e.code == 429 or e.code >= 500):
                print(f"  HTTP {e.code}, přeskakuji: {url}", file=sys.stderr)
                return None, None
            err = f"HTTP {e.code}"
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            err = str(e)
        stats["retries"] += 1
        if attempt < MAX_RETRIES - 1:
            wait = 2 ** (attempt + 1)
            print(f"  {err}, čekám {wait} s: {url}", file=sys.stderr)
            time.sleep(wait)
    stats["failed"] += 1
    print(f"  po {MAX_RETRIES} pokusech přeskakuji: {url}", file=sys.stderr)
    return None, None


# ---------- parsování ----------

def ld_blocks(html):
    out = []
    for m in LD_RE.finditer(html):
        try:
            out.append(json.loads(m.group(1), strict=False))
        except json.JSONDecodeError:
            pass
    return out


def listing_slugs(html):
    slugs = []
    for j in ld_blocks(html):
        if isinstance(j, dict) and j.get("@type") == "ItemList":
            for e in j.get("itemListElement") or []:
                m = PRODUCT_URL.match((e or {}).get("url") or "")
                if m:
                    slugs.append(m.group(1))
    return slugs


def list_slugs(store, cat):
    """Všechny produkty obchodu v kategorii (projde stránkování, dokud přibývají nové produkty)."""
    out, seen = [], set()
    path = f"/slevy/{cat}/{store}"
    for page in range(1, MAX_PAGES + 1):
        url = BASE + path + ("" if page == 1 else f"?page={page}")
        html, final = fetch(url)
        if html is None:
            break
        if urlparse(final).path.rstrip("/") != path:   # přesměrováno jinam = obchod v kategorii nemá akce
            break
        new = [s for s in listing_slugs(html) if s not in seen]
        if not new:
            break
        for s in new:
            seen.add(s)
            out.append(s)
    return out


def ld_product(html):
    for j in ld_blocks(html):
        if isinstance(j, dict) and j.get("@type") == "Product":
            return j
    return None


def canon_store(raw):
    raw = " ".join(str(raw).split())
    f = fold(raw)
    for c in CANON_STORES:
        fc = fold(c)
        if f == fc or f.startswith(fc + " "):
            return c
    return raw


def fold(s):
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower().strip()


def num(x):
    return int(x) if float(x).is_integer() else round(float(x), 4)


def norm_size(value, unit):
    v = float(value.replace(",", "."))
    if unit == "g":
        return num(v / 1000), "kg"
    if unit == "kg":
        return num(v), "kg"
    if unit == "ml":
        return num(v / 1000), "l"
    if unit == "cl":
        return num(v / 100), "l"
    if unit == "l":
        return num(v), "l"
    return num(v), "ks"


# Mapování podkategorie kupi.cz -> kategorie FORMAT.md. Nejdřív se hledá podle klíčového slova v tokenech
# podkategorie (slug rozdělený na „-“), jinak podle kategorie, ze které produkt přišel.
PARENT_DEFAULT = {
    "alkohol": "ALKOHOL", "nealko-napoje": "NAPOJE", "ovoce-a-zelenina": "OVOCE_ZELENINA",
    "pecivo": "PECIVO", "mrazene-a-instantni-potraviny": "MRAZENE", "maso-drubez-a-ryby": "MASO_RYBY",
    "mlecne-vyrobky-a-vejce": "MLECNE", "lahudky": "TRVANLIVE", "konzervy": "TRVANLIVE",
    "sladkosti-a-slane-snacky": "SLADKOSTI", "vareni-a-peceni": "TRVANLIVE", "zdrava-vyziva": "TRVANLIVE",
    "pro-deti": "TRVANLIVE",
}
NONFOOD_PREFIX = ("krmiv", "kosmet", "hygien", "plenk", "pleny", "drogeri", "tabak", "cigar", "zahrad", "kocky")
NONFOOD_EXACT = ("pes", "psi", "kocek")
ALK_PREFIX = ("vino", "pivo", "vodk", "whisk", "bourbon", "sekt", "liker", "lihovin", "tequil", "brandy",
              "vermut", "cider", "becher", "absint", "medovin", "prosecc", "sampan", "konak", "slivovic")
ALK_EXACT = ("rum", "gin")
NAP_PREFIX = ("caj", "kav", "sirup", "dzus", "limonad", "mineral", "energet", "napoj", "koncentrat", "smoothie")
NAP_EXACT = ("sok", "voda", "vody", "kola")
RYBY_PREFIX = ("losos", "tunak", "sardin", "makrel", "treska", "kapr", "krevet")
RYBY_EXACT = ("ryby", "ryba", "ryb", "sled")
UZEN_PREFIX = ("uzenin", "salam", "sunk", "pasti", "slanin", "parek", "parky", "klobas", "sekan", "debrec")
MASO_PREFIX = ("maso", "kure", "kurec", "kurat", "hovez", "veprov", "telec", "drubez", "krut", "kachn", "zverin",
               "mlet", "husa", "krocan", "jehn")
PECIVO_PREFIX = ("pecivo", "peciv", "chleb", "rohl", "houska", "buchet", "kvasnic", "trdeln", "kolac")
PECIVO_EXACT = ("testa", "testo", "tortil", "tousty")
MLECNE_PREFIX = ("mlek", "mlec", "jogurt", "smetan", "tvaroh", "syr", "maslo", "kefir", "podmasl", "mascarp", "jogh")
DETI_FOOD = ("vyziv", "kas", "piskot", "mlek", "mlec", "omack", "sirek", "sirk", "ovoc", "zelenin", "mas", "jogurt",
             "dzus", "caj", "napoj", "mus", "cerea", "sust", "tvaroh", "susen", "sladk", "cokolad", "bonbon",
             "instant", "polevk", "pecivo", "chleb", "keks", "sunk", "uzenin")


def _any(ts, prefixes):
    return any(t.startswith(p) for t in ts for p in prefixes)


def _exact(ts, words):
    return any(t in words for t in ts)


def category_for(parent, sub):
    """Vrací kategorii FORMAT.md, nebo None (nepotravina)."""
    ts = sub.split("-") if sub else []
    if _any(ts, NONFOOD_PREFIX) or _exact(ts, NONFOOD_EXACT):
        return None
    if _any(ts, ("bezalk", "nealko")):
        return "NAPOJE"
    if parent == "pro-deti" and not _any(ts, DETI_FOOD):
        return None
    if parent == "alkohol" or _any(ts, ALK_PREFIX) or _exact(ts, ALK_EXACT):
        return "ALKOHOL"
    if parent == "nealko-napoje" or _any(ts, NAP_PREFIX) or _exact(ts, NAP_EXACT):
        return "NAPOJE"
    if _any(ts, ("vejc",)):
        return "VEJCE"
    if _any(ts, ("zmrzl",)):
        return "MRAZENE"
    if _exact(ts, RYBY_EXACT) or _any(ts, RYBY_PREFIX):
        return "MASO_RYBY"
    if _any(ts, UZEN_PREFIX):
        return "UZENINY"
    if _any(ts, MASO_PREFIX):
        return "MASO_RYBY"
    if _any(ts, PECIVO_PREFIX) or _exact(ts, PECIVO_EXACT):
        return "PECIVO"
    if parent in ("mlecne-vyrobky-a-vejce", "pro-deti") and _any(ts, MLECNE_PREFIX):
        return "MLECNE"
    if _any(ts, ("testovin", "rez", "ryz", "mouk", "kase")):   # suché těstoviny, rýže, mouka, kaše
        return "TRVANLIVE"
    if parent == "ovoce-a-zelenina" and _any(ts, ("susen", "orech", "nakladan", "sterilo", "konzerv")):
        return "TRVANLIVE"
    if parent == "mrazene-a-instantni-potraviny" and _any(ts, ("instant", "polevk")):
        return "TRVANLIVE"
    if parent in PARENT_DEFAULT:
        return PARENT_DEFAULT[parent]
    return "OSTATNI"


def build_record(slug, html, listing_cat):
    prod = ld_product(html)
    if not prod:
        return None, "bez JSON-LD Product"
    offers = prod.get("offers") or {}
    if isinstance(offers, dict) and isinstance(offers.get("offers"), list):
        items = offers["offers"]
    elif isinstance(offers, dict):
        items = [offers]
    elif isinstance(offers, list):
        items = offers
    else:
        items = []
    stores = []
    for o in items:
        if isinstance(o, dict) and o.get("offeredBy"):
            n = canon_store(o["offeredBy"])
            if n not in stores:
                stores.append(n)
    if not stores:
        return None, "bez obchodu v akci"

    name = str(prod.get("name") or "").strip()
    if not name:
        return None, "bez názvu"

    m = SUBCAT_RE.search(html)
    parent = (m.group(1) if m else None) or listing_cat
    sub = m.group(2) if m and m.group(2) else None
    cat = category_for(parent, sub)
    if cat is None:
        return None, f"nepotravina ({parent}/{sub})"
    mapping[(parent, sub or "-", cat)] += 1

    sizes = set()
    for v, u in SIZE_RE.findall(html.replace("&nbsp;", " ")):
        sizes.add(norm_size(v, u))
    rec = {"id": f"kupi-{slug}", "name": name, "category": cat}
    brand = prod.get("brand")
    if isinstance(brand, dict):
        brand = brand.get("name")
    if isinstance(brand, str) and brand.strip():
        rec["brand"] = brand.strip()
    if len(sizes) == 1:
        rec["size_value"], rec["size_unit"] = sizes.pop()
    rec["eans"] = []
    rec["stores"] = [{"store": s, "receipt_name": None, "receipt_name_source": None, "url": None} for s in stores]
    img = prod.get("image")
    if isinstance(img, list):
        img = img[0] if img else None
    if isinstance(img, str) and img.startswith("https://"):
        rec["image_url"] = img
    rec["sources"] = [f"{BASE}/sleva/{slug}"]
    return rec, None


# ---------- zápis ----------

def load_existing():
    records = {}
    if OUT.exists():
        with open(OUT, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    r = json.loads(line)
                    records[r["id"]] = r
    return records


def save(records):
    OUT.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUT.with_name(OUT.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        for r in records.values():
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    os.replace(tmp, OUT)


def main(argv):
    dry = "--dry-run" in argv
    records = load_existing()
    print(f"Ve výstupu už je {len(records)} záznamů.", file=sys.stderr)

    listing = {}          # slug -> kategorie, ze které přišel (první výskyt)
    blocked = False
    try:
        for store in OBCHODY:
            for cat in KATEGORIE:
                slugs = list_slugs(store, cat)
                new = 0
                for s in slugs:
                    if s not in listing:
                        listing[s] = cat
                        new += 1
                print(f"{store}/{cat}: {len(slugs)} produktů, nových {new}", file=sys.stderr)
    except Blocked as e:
        blocked = True
        print(f"BLOKACE (403) při výpisu, sběr se zastavuje: {e}", file=sys.stderr)

    todo = [s for s in listing if f"kupi-{s}" not in records]
    bad = [s for s in todo if not SLUG_RE.fullmatch(s)]
    todo = [s for s in todo if SLUG_RE.fullmatch(s)]
    print(f"Produktů v listingech: {len(listing)}; k načtení detailu: {len(todo)}; "
          f"neplatný slug (přeskočeno): {len(bad)}", file=sys.stderr)

    dropped = Counter()
    if not dry and not blocked:
        done = 0
        try:
            for slug in todo:
                html, _ = fetch(f"{BASE}/sleva/{slug}")
                if html is None:
                    continue
                rec, why = build_record(slug, html, listing[slug])
                if rec is None:
                    dropped[why.split(" (")[0]] += 1
                    continue
                records[rec["id"]] = rec
                done += 1
                if done % SAVE_EVERY == 0:
                    save(records)
                    print(f"  … {done}/{len(todo)} detailů, požadavků {stats['requests']}", file=sys.stderr)
        except Blocked as e:
            blocked = True
            print(f"BLOKACE (403), sběr se zastavuje a zapisuje se to, co je staženo: {e}", file=sys.stderr)

    if not dry:
        save(records)
    print(f"\nZáznamů ve výstupu: {len(records)}", file=sys.stderr)
    per_store = Counter(s["store"] for r in records.values() for s in r["stores"])
    print("Obchody (počet záznamů, kde je produkt v akci):", dict(per_store.most_common()), file=sys.stderr)
    print("Kategorie:", dict(Counter(r["category"] for r in records.values())), file=sys.stderr)
    print(f"Vyřazeno: {dict(dropped)}", file=sys.stderr)
    print("Mapování podkategorií (rodič / podkategorie -> kategorie: počet):", file=sys.stderr)
    for (p, s, c), n in sorted(mapping.items()):
        print(f"  {p} / {s} -> {c}: {n}", file=sys.stderr)
    print(f"Požadavků: {stats['requests']}, opakování: {stats['retries']}, nepodařilo se: {stats['failed']}",
          file=sys.stderr)
    if blocked:
        print("STAV: zastaveno blokací (403).", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
