#!/usr/bin/env python3
"""Akce Kaufland a Tesco z kupi.cz (agregátor aktuálních akčních letáků).

Výstup: data/foods/raw/18-kupi-kaufland-tesco.jsonl (nové záznamy se sloučí se stávajícími podle id).
Spuštění z kteréhokoli adresáře:
    python3 data/foods/harvest/18-kupi-kaufland-tesco.py                 # sběr + zápis
    python3 data/foods/harvest/18-kupi-kaufland-tesco.py --dry-run       # bez zápisu výstupu
    python3 data/foods/harvest/18-kupi-kaufland-tesco.py --cache FILE    # detaily produktů se ukládají do FILE
                                                                          # a při dalším běhu se z něj berou

Postup:
  1) /slevy/<kategorie>/<obchod> a ?page=N (JSON-LD ItemList) pro Kaufland a Tesco; stránky se chodí,
     dokud přibývají nové produkty;
  2) /sleva/<slug> – JSON-LD Product (name, image, offers[].offeredBy = obchody v akci); z textu stránky
     podkategorie („Tento výrobek najdete v kategorii X a podkategorii Y“) a velikost balení
     (řádek „Aktuální akční slevy <název> <velikost>“);
  3) záznam podle FORMAT.md; všechny obchody z offers, url a receipt_name null.

Produkty, které už jsou ve výstupu (stejné id), se znovu nestahují. Produkty bez obchodu v offers se vynechají.
Šetrnost: max 1 požadavek za sekundu, browser User-Agent, při 429/5xx exponenciální čekání (5 pokusů),
při 403 se skript ukončí bez zápisu (blokaci neobcházíme).
"""
import argparse
import html as html_lib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "data/foods/raw/18-kupi-kaufland-tesco.jsonl"

BASE = "https://www.kupi.cz"
STORE_SLUGS = ["kaufland", "tesco"]
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/124.0 Safari/537.36")
MIN_INTERVAL = 1.0      # sekund mezi požadavky (celkem)
MAX_RETRIES = 5
MAX_PAGES = 40

# Kategorie potravin na kupi.cz -> výchozí kategorie FORMAT.md (None = jen podle podkategorie).
TOP_CAT = {
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
    "pro-deti": None,   # jen dětské potraviny – ostatní podkategorie se vynechají
}

# Podkategorie kupi (slug z odkazu /slevy/<slug>) -> kategorie FORMAT.md; "SKIP" = nepotravina / vynechat.
SUB_CAT = {}

_last_request = 0.0
stats = {"requests": 0, "retries": 0, "failed": 0}
unknown_subs = {}


class Blocked(Exception):
    pass


def _wait():
    global _last_request
    wait = MIN_INTERVAL - (time.monotonic() - _last_request)
    if wait > 0:
        time.sleep(wait)
    _last_request = time.monotonic()


def get(url):
    """Vrátí HTML, nebo None (404 / trvale selhalo). 403 ukončí běh výjimkou Blocked."""
    for attempt in range(MAX_RETRIES):
        _wait()
        stats["requests"] += 1
        req = urllib.request.Request(url, headers={
            "User-Agent": UA,
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "cs,en;q=0.8",
        })
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            if e.code == 403:
                raise Blocked(url)
            if e.code == 404:
                return None
            if e.code != 429 and e.code < 500:
                raise
        except urllib.error.URLError:
            pass  # síťová chyba – zkusíme znovu
        stats["retries"] += 1
        if attempt < MAX_RETRIES - 1:
            time.sleep(2 ** (attempt + 1))
    stats["failed"] += 1
    print(f"varování: přeskočeno po {MAX_RETRIES} neúspěšných pokusech: {url}", file=sys.stderr)
    return None


LD_RE = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.S)


def ld_blocks(page):
    out = []
    for m in LD_RE.finditer(page):
        try:
            out.append(json.loads(m.group(1)))
        except json.JSONDecodeError:
            pass
    return out


def plain_lines(page):
    h = re.sub(r"<script.*?</script>|<style.*?</style>", "", page, flags=re.S)
    h = re.sub(r"<[^>]+>", "\n", h)
    h = html_lib.unescape(h).replace("\xa0", " ")
    return [re.sub(r"\s+", " ", ln).strip() for ln in h.split("\n") if ln.strip()]


def listing_slugs(page):
    """Slugy produktů z JSON-LD ItemList na stránce seznamu."""
    slugs = []
    for d in ld_blocks(page):
        if d.get("@type") != "ItemList":
            continue
        for it in d.get("itemListElement", []):
            m = re.search(r"/sleva/([^/?#]+)", it.get("url", ""))
            if m:
                slugs.append(m.group(1))
    return slugs


def list_store(top, store):
    """Všechny produkty na /slevy/<top>/<store>, stránkováno ?page=N, dokud přibývají nové."""
    found, seen = [], set()
    for page_no in range(1, MAX_PAGES + 1):
        url = f"{BASE}/slevy/{top}/{store}" + ("" if page_no == 1 else f"?page={page_no}")
        page = get(url)
        if page is None:
            break
        items = listing_slugs(page)
        new = [s for s in items if s not in seen]
        if not new:
            break
        seen.update(new)
        found.extend(new)
    return found


SUB_RE = re.compile(
    r'Tento výrobek najdete v kategorii\s*<a href="/slevy/([^"]+)"[^>]*>[^<]*</a>\s*'
    r'a podkategorii\s*<a href="/slevy/([^"]+)"[^>]*>([^<]*)</a>', re.S)
UNIT = {"kg": (1, "kg"), "g": (0.001, "kg"), "l": (1, "l"), "ml": (0.001, "l"), "cl": (0.01, "l"),
        "ks": (1, "ks")}


def parse_size(lines, name):
    """Velikost balení z řádku „Aktuální akční slevy <název> <velikost>“ (jen když je za názvem)."""
    prefix = "Aktuální akční slevy "
    for ln in lines:
        if ln.startswith(prefix):
            rest = ln[len(prefix):]
            if not rest.startswith(name):
                return None, None
            m = re.fullmatch(r"(\d+(?:[.,]\d+)?)\s*(kg|g|ml|cl|l|ks)", rest[len(name):].strip(), re.I)
            if not m:
                return None, None
            num = float(m.group(1).replace(",", "."))
            factor, unit = UNIT[m.group(2).lower()]
            if num <= 0:
                return None, None
            return round(num * factor, 4), unit
    return None, None


def offered_by(prod):
    offs = prod.get("offers") or {}
    items = offs.get("offers", []) if isinstance(offs, dict) else offs
    if isinstance(items, dict):
        items = [items]
    names = []
    for it in items:
        ob = it.get("offeredBy")
        if isinstance(ob, dict):
            ob = ob.get("name")
        if isinstance(ob, str) and ob.strip() and ob.strip() not in names:
            names.append(ob.strip())
    return names


def fetch_detail(slug):
    """Detail produktu jako dict, nebo None (není v akci / stránka nejde)."""
    page = get(f"{BASE}/sleva/{slug}")
    if page is None:
        return None
    prod = next((d for d in ld_blocks(page) if d.get("@type") == "Product"), None)
    if prod is None:
        return None
    stores = offered_by(prod)
    if not stores:
        return None
    name = (prod.get("name") or "").strip()
    if not name:
        return None
    m = SUB_RE.search(page.replace("\xa0", " "))
    top_slug, sub_slug, sub_name = (m.group(1), m.group(2), html_lib.unescape(m.group(3)).strip()) if m else (None, None, None)
    lines = plain_lines(page)
    size_value, size_unit = parse_size(lines, name)
    eans = []
    for key in ("gtin13", "gtin8"):
        v = prod.get(key)
        if isinstance(v, str) and re.fullmatch(r"\d{8}|\d{13}", v) and v not in eans:
            eans.append(v)
    brand = prod.get("brand")
    if isinstance(brand, dict):
        brand = brand.get("name")
    return {
        "name": name,
        "brand": brand.strip() if isinstance(brand, str) and brand.strip() else None,
        "image_url": prod.get("image") if isinstance(prod.get("image"), str) else None,
        "eans": eans,
        "stores": stores,
        "sub_top": top_slug,
        "sub_slug": sub_slug,
        "sub_name": sub_name,
        "size_value": size_value,
        "size_unit": size_unit,
    }


STORE_CANON = {s.lower(): s for s in ["Lidl", "Kaufland", "Albert", "Billa", "Penny", "Tesco", "Globus",
                                      "Rohlík", "Košík", "Makro", "Norma", "Coop"]}


def category_for(top, sub_slug):
    """Kategorie FORMAT.md, nebo None (vynechat). Podle podkategorie, jinak podle hlavní kategorie."""
    if sub_slug in SUB_CAT:
        return None if SUB_CAT[sub_slug] == "SKIP" else SUB_CAT[sub_slug]
    if top in TOP_CAT and TOP_CAT[top]:
        if sub_slug:
            unknown_subs.setdefault(f"{top}/{sub_slug}", 0)
            unknown_subs[f"{top}/{sub_slug}"] += 1
        return TOP_CAT[top]
    if sub_slug:
        unknown_subs.setdefault(f"{top}/{sub_slug}", 0)
        unknown_subs[f"{top}/{sub_slug}"] += 1
    return None


def build_record(slug, top, d):
    cat = category_for(top, d.get("sub_slug"))
    if cat is None:
        return None
    rec = {"id": f"kupi-{slug}", "name": d["name"]}
    if d["brand"]:
        rec["brand"] = d["brand"]
    rec["category"] = cat
    if d["size_value"] is not None:
        rec["size_value"] = d["size_value"]
        rec["size_unit"] = d["size_unit"]
    if d["eans"]:
        rec["eans"] = d["eans"]
    rec["stores"] = [{"store": STORE_CANON.get(s.lower(), s), "receipt_name": None,
                      "receipt_name_source": None, "url": None} for s in d["stores"]]
    if d["image_url"]:
        rec["image_url"] = d["image_url"]
    rec["sources"] = [f"{BASE}/sleva/{slug}"]
    return rec


def load_existing():
    recs = {}
    if OUT.exists():
        with open(OUT, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    o = json.loads(line)
                    recs[o["id"]] = o
    return recs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="nezapisovat výstup")
    ap.add_argument("--cache", type=Path, help="JSON soubor s detaily produktů (čte se i zapisuje)")
    args = ap.parse_args()

    cache = {}
    if args.cache and args.cache.exists():
        cache = json.loads(args.cache.read_text(encoding="utf-8"))

    existing = load_existing()

    # 1) seznamy akcí Kaufland + Tesco
    candidates = {}   # slug -> hlavní kategorie kupi
    for top in TOP_CAT:
        for store in STORE_SLUGS:
            for slug in list_store(top, store):
                candidates.setdefault(slug, top)
    print(f"kandidátů ze seznamů: {len(candidates)}", file=sys.stderr)

    # 2) detaily nových produktů
    new = {}
    known = skipped_nonfood = no_offer = 0
    for slug, top in candidates.items():
        rid = f"kupi-{slug}"
        if rid in existing:
            known += 1
            continue
        if slug in cache:
            d = cache[slug]
        else:
            d = fetch_detail(slug)
            cache[slug] = d
            if args.cache:
                args.cache.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
        if d is None:
            no_offer += 1
            continue
        rec = build_record(slug, top, d)
        if rec is None:
            skipped_nonfood += 1
            continue
        new[rid] = rec

    # 3) sloučení se stávajícími a zápis
    merged = dict(existing)
    for rid, rec in new.items():
        merged[rid] = rec
    rows = [merged[k] for k in sorted(merged)]

    if not args.dry_run:
        tmp = OUT.with_suffix(".jsonl.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        os.replace(tmp, OUT)

    per_store = {}
    for r in rows:
        for s in r["stores"]:
            per_store[s["store"]] = per_store.get(s["store"], 0) + 1
    print(f"nových záznamů: {len(new)}, už známých (nestahováno): {known}, "
          f"bez akce: {no_offer}, nepotravina/vynecháno: {skipped_nonfood}", file=sys.stderr)
    print(f"celkem ve výstupu: {len(rows)}; podle obchodů: {per_store}", file=sys.stderr)
    print(f"požadavků: {stats['requests']}, opakování: {stats['retries']}, neúspěšné: {stats['failed']}",
          file=sys.stderr)
    if unknown_subs:
        print("podkategorie bez mapování (použit výchozí podle hlavní kategorie):", file=sys.stderr)
        for k, v in sorted(unknown_subs.items()):
            print(f"  {k}: {v}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Blocked as e:
        print(f"403 – blokace, končím bez zápisu: {e}", file=sys.stderr)
        sys.exit(2)
