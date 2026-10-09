#!/usr/bin/env python3
"""Hromadný sběr z kupi.cz: aktuální akce kamenných obchodů ALBERT a BILLA (jen potraviny).

Výstup: data/foods/raw/19-kupi-albert-billa.jsonl. Spuštění z kteréhokoli adresáře:
    python3 data/foods/harvest/19-kupi-albert-billa.py

Zdroj (kupi.cz, pravidla v data/foods/prompts/haiku-kupi.md):
  - výpis akcí obchodu v kategorii: /slevy/<kategorie>/<obchod>[?page=N], seznam = JSON-LD ItemList;
    stránky se berou, dokud přibývají nové produkty
  - detail produktu /sleva/<slug>: JSON-LD Product (name, brand, image, offers[].offeredBy = obchody v akci),
    podkategorie („Tento výrobek najdete v kategorii X a podkategorii Y“) a velikost balení z textu stránky

Produkt bez obchodu v offers se vynechá. Produkt, jehož podkategorie není v tabulce (a hlavní kategorie
nemá záložní kategorii), se vynechá a vypíše do přehledu – tabulku pak doplň.

Existující výstup se nemaže: nové produkty se přidají, produkty se stejným id (kupi-<slug>) se znovu nestahují.
Šetrnost: max 1 požadavek za sekundu, User-Agent prohlížeče, při 429/5xx exponenciální čekání,
po 5 neúspěších stránku přeskočit. Při 403 se sběr zastaví a uloží se, co se stihlo (blokaci neobcházíme).
"""
import html
import json
import re
import sys
import time
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "data/foods/raw/19-kupi-albert-billa.jsonl"

SITE = "https://www.kupi.cz"
OBCHODY = ["albert", "billa"]  # slugy obchodů na kupi.cz
# Kategorie potravin na kupi.cz; nepotraviny se nesbírají. pro-deti jen přes podkategorie v tabulce.
KATEGORIE = ["alkohol", "konzervy", "lahudky", "maso-drubez-a-ryby", "mlecne-vyrobky-a-vejce",
             "mrazene-a-instantni-potraviny", "nealko-napoje", "ovoce-a-zelenina", "pecivo",
             "sladkosti-a-slane-snacky", "vareni-a-peceni", "zdrava-vyziva", "pro-deti"]
MAX_PAGES = 60
MIN_INTERVAL = 1.0  # sekund mezi požadavky (sdíleno pro všechny dotazy)
MAX_RETRIES = 5
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"

# Názvy obchodů z offers[].offeredBy: podle začátku názvu sjednotíme (např. „Penny Market“ -> Penny,
# „Albert hypermarket“ -> Albert). Ostatní názvy zůstávají, jak jsou.
ZNAME_OBCHODU = ["Lidl", "Kaufland", "Albert", "Billa", "Penny", "Tesco", "Globus", "Norma", "Coop", "Makro"]

# Podkategorie kupi (malými písmeny) -> kategorie FORMAT.md; None = nepotravina, vynechat.
PODKATEGORIE = {
}

# Záložní kategorie podle hlavní kategorie kupi (ze, kterého výpisu produkt přišel),
# když podkategorie není v tabulce výše. None = vynechat.
HLAVNI = {
    "alkohol": "ALKOHOL",
    "konzervy": "TRVANLIVE",
    "lahudky": "UZENINY",
    "maso-drubez-a-ryby": "MASO_RYBY",
    "mlecne-vyrobky-a-vejce": "MLECNE",
    "mrazene-a-instantni-potraviny": "MRAZENE",
    "nealko-napoje": "NAPOJE",
    "ovoce-a-zelenina": "OVOCE_ZELENINA",
    "pecivo": "PECIVO",
    "sladkosti-a-slane-snacky": "SLADKOSTI",
    "vareni-a-peceni": "TRVANLIVE",
    "zdrava-vyziva": "TRVANLIVE",
    "pro-deti": None,
}

SLUG_URL = re.compile(r"^https?://(?:www\.)?kupi\.cz/sleva/([a-z0-9][a-z0-9-]*)/?$")
SIZE = re.compile(r"(\d+(?:[.,]\d+)?)\s*(kg|g|ml|l|ks)")
TOP_PREFIX = "Aktuální akční slevy "

_last_request = 0.0
stats = {"requests": 0, "retries": 0}


class Blocked(Exception):
    pass


def get(url):
    """GET stránky s limitem 1 req/s a retry (exponenciálně) při 429/5xx/síťové chybě. None = přeskočit."""
    global _last_request
    for attempt in range(MAX_RETRIES):
        wait = MIN_INTERVAL - (time.monotonic() - _last_request)
        if wait > 0:
            time.sleep(wait)
        _last_request = time.monotonic()
        stats["requests"] += 1
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": UA,
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "cs-CZ,cs;q=0.9",
            })
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            if e.code == 403:
                raise Blocked(url)
            if not (e.code == 429 or e.code >= 500):
                print(f"  HTTP {e.code}, přeskakuji: {url}", file=sys.stderr)
                return None
        except (urllib.error.URLError, TimeoutError) as e:
            print(f"  chyba sítě ({e}), zkusím znovu: {url}", file=sys.stderr)
        stats["retries"] += 1
        time.sleep(2 ** attempt)
    print(f"  po {MAX_RETRIES} pokusech přeskakuji: {url}", file=sys.stderr)
    return None


def ld_blocks(page):
    """Všechny JSON-LD objekty na stránce (seznam nebo jediný objekt)."""
    out = []
    for m in re.finditer(r'<script[^>]*ld\+json[^>]*>(.*?)</script>', page, re.S):
        try:
            data = json.loads(m.group(1), strict=False)
        except json.JSONDecodeError:
            continue
        out.extend(data if isinstance(data, list) else [data])
    return [o for o in out if isinstance(o, dict)]


def page_text(page):
    """Čitelný text stránky (bez skriptů a značek), nbsp převedené na mezery."""
    t = re.sub(r"<script.*?</script>|<style.*?</style>", " ", page, flags=re.S)
    t = html.unescape(re.sub(r"<[^>]+>", " ", t)).replace("\xa0", " ")
    return re.sub(r"\s+", " ", t).strip()


def store_name(raw):
    raw = raw.strip()
    low = raw.lower()
    for name in ZNAME_OBCHODU:
        if low == name.lower() or low.startswith(name.lower() + " "):
            return name
    return raw


def listing_slugs(page):
    slugs = []
    for o in ld_blocks(page):
        if o.get("@type") != "ItemList":
            continue
        for el in o.get("itemListElement") or []:
            m = SLUG_URL.match(str(el.get("url", "")))
            if m:
                slugs.append(m.group(1))
    return list(dict.fromkeys(slugs))


def crawl_listing(obchod, kat):
    """Slugy produktů obchodu v kategorii; stránky, dokud přibývají nové produkty."""
    seen = []
    for page in range(1, MAX_PAGES + 1):
        url = f"{SITE}/slevy/{kat}/{obchod}" + ("" if page == 1 else f"?page={page}")
        body = get(url)
        if body is None:
            break
        new = [s for s in listing_slugs(body) if s not in seen]
        if not new:
            break
        seen.extend(new)
    return seen


def collect_offer_stores(node, out):
    """Projde offers (i vnořené AggregateOffer.offers) a nasbírá offeredBy."""
    if isinstance(node, dict):
        if "offeredBy" in node:
            ob = node["offeredBy"]
            if isinstance(ob, dict):
                ob = ob.get("name")
            if isinstance(ob, str) and ob.strip():
                s = store_name(ob)
                if s not in out:
                    out.append(s)
        for v in node.values():
            collect_offer_stores(v, out)
    elif isinstance(node, list):
        for v in node:
            collect_offer_stores(v, out)


def size_from_text(text, name):
    """Velikost jen když je v textu přesně „Aktuální akční slevy <název> <velikost> Doporučené akce“."""
    i = text.find(TOP_PREFIX + name)
    if i < 0:
        return None, None
    start = i + len(TOP_PREFIX) + len(name)
    j = text.find("Doporučené akce", start)
    rest = text[start:j if j > 0 else start + 30].strip()
    m = re.fullmatch(SIZE.pattern, rest)
    if not m:
        return None, None
    v = float(m.group(1).replace(",", "."))
    unit = m.group(2)
    if unit == "g":
        return round(v / 1000, 3), "kg"
    if unit == "ml":
        return round(v / 1000, 3), "l"
    return round(v, 3), unit


subcats_seen = Counter()


def build_record(slug, body, top_kat):
    """Záznam z detailu produktu, nebo (None, důvod) když se produkt vynechá."""
    prod = next((o for o in ld_blocks(body) if o.get("@type") == "Product"), None)
    if prod is None:
        return None, "bez JSON-LD Product"
    name = re.sub(r"\s+", " ", str(prod.get("name") or "")).strip()
    if not name:
        return None, "bez názvu"
    stores = []
    collect_offer_stores(prod.get("offers"), stores)
    if not stores:
        return None, "není v akci (offers prázdné)"

    text = page_text(body)
    m = re.search(r"Tento výrobek najdete v kategorii (.+?) a podkategorii (.+?)\s*\.", text)
    sub = m.group(2).strip().lower() if m else None
    if sub:
        subcats_seen[sub] += 1
    if sub in PODKATEGORIE:
        cat = PODKATEGORIE[sub]
    else:
        cat = HLAVNI.get(top_kat)
    if cat is None:
        return None, f"nepotravina nebo nezařazeno (podkategorie {sub!r}, kategorie {top_kat})"

    rec = {"id": f"kupi-{slug}", "name": name}
    brand = prod.get("brand")
    if isinstance(brand, dict):
        brand = brand.get("name")
    if isinstance(brand, str) and brand.strip():
        rec["brand"] = brand.strip()
    rec["category"] = cat
    sv, su = size_from_text(text, name)
    if sv is not None:
        rec["size_value"], rec["size_unit"] = sv, su
    rec["stores"] = [{"store": s, "receipt_name": None, "receipt_name_source": None, "url": None}
                     for s in stores]
    img = prod.get("image")
    if isinstance(img, list):
        img = img[0] if img else None
    if isinstance(img, str) and img.startswith("http"):
        rec["image_url"] = img
    rec["sources"] = [f"{SITE}/sleva/{slug}"]
    return rec, None


def load_existing():
    existing = {}
    if OUT.exists():
        with open(OUT, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    o = json.loads(line)
                    existing.setdefault(o["id"], o)
    return existing


def main():
    existing = load_existing()
    known = {i[len("kupi-"):] for i in existing}
    print(f"ve výstupu už je {len(existing)} záznamů", file=sys.stderr)

    listed = {}  # slug -> hlavní kategorie, ze které přišel poprvé
    blocked = False
    added, skipped = [], Counter()
    try:
        for obchod in OBCHODY:
            for kat in KATEGORIE:
                slugs = crawl_listing(obchod, kat)
                new = sum(1 for s in slugs if s not in listed)
                for s in slugs:
                    listed.setdefault(s, kat)
                print(f"{obchod}/{kat}: {len(slugs)} produktů, nových {new}", file=sys.stderr)
        todo = [s for s in listed if s not in known]
        print(f"unikátních produktů {len(listed)}, ke stažení detailu {len(todo)}", file=sys.stderr)

        for n, slug in enumerate(todo, 1):
            body = get(f"{SITE}/sleva/{slug}")
            if body is None:
                skipped["stažení selhalo"] += 1
                continue
            rec, why = build_record(slug, body, listed[slug])
            if rec is None:
                skipped[why] += 1
            else:
                added.append(rec)
            if n % 25 == 0:
                print(f"  detailů {n}/{len(todo)}, přidáno {len(added)}", file=sys.stderr)
    except Blocked as e:
        blocked = True
        print(f"HTTP 403 – blokace, ukládám, co je stažené: {e}", file=sys.stderr)

    records = list(existing.values()) + added
    tmp = OUT.with_suffix(".jsonl.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    tmp.replace(OUT)

    print(f"\nzapsáno {len(records)} záznamů do {OUT} (přidáno nových {len(added)})")
    print(f"požadavků {stats['requests']}, opakování {stats['retries']}")
    if skipped:
        print("vynechané:")
        for k, v in skipped.most_common():
            print(f"  {v:4d}  {k}")
    print("podkategorie kupi (počet produktů):")
    for k, v in subcats_seen.most_common():
        print(f"  {v:4d}  {k}  -> {PODKATEGORIE.get(k, 'podle hlavní kategorie')}")
    return 2 if blocked else 0


if __name__ == "__main__":
    sys.exit(main())
