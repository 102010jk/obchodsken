#!/usr/bin/env python3
"""Hromadný sběr potravin z Rohlík.cz – kategorie Maso a ryby (300103000) a Uzeniny a lahůdky (300104000).

Výstup: data/foods/raw/02-rohlik-maso-uzeniny.jsonl (přepíše se). Formát viz data/foods/FORMAT.md.
Spuštění: python3 data/foods/harvest/02-rohlik-maso-uzeniny.py

Postup: stránkování kategorií -> podkategorie (mapovací tabulka níže) -> detaily produktů po dávkách (50 ID).
Požadavky jsou omezené na 1 za sekundu; při 429/5xx se čeká exponenciálně, po 5 neúspěších se požadavek přeskočí.
Velikost se uvádí jen u neváženého zboží (textualAmount bez „cca“ a bez weightedItem); vážené položky jsou v datech.
"""
import json
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.request
from pathlib import Path

BASE = "https://www.rohlik.cz/api/v1"
PAGE_URL = "https://www.rohlik.cz"
STORE = "Rohlík"
PARENTS = {300103000: "MASO_RYBY", 300104000: "UZENINY"}  # fallback podle hlavní kategorie
DETAIL_BATCH = 50
MIN_INTERVAL = 1.0  # s mezi požadavky (max 1 za sekundu – sdílený web)
MAX_RETRIES = 5
UA = "Mozilla/5.0 (obchodsken-harvest)"

# Mapování podkategorie obchodu -> kategorie FORMAT.md (ID podkategorií z /categories/normal/<rodic>/subcategories)
SUB_CATEGORY = {
    300115247: "MASO_RYBY",  # Drůbež
    300117217: "MASO_RYBY",  # Hovězí a telecí
    300117385: "MASO_RYBY",  # Ryby a mořské plody
    300103009: "MASO_RYBY",  # Vepřové
    300121424: "MASO_RYBY",  # BIO maso a ryby
    300117355: "MASO_RYBY",  # Maso na gril, steaky a burgery
    300122988: "MASO_RYBY",  # Zvěřina, jehněčí, králičí a speciality
    300124949: "UZENINY",    # Z čerstvého pultu (většinou lahůdkové maso a saláty)
    300104001: "UZENINY",    # Šunky a slaniny
    300104012: "UZENINY",    # Párky, klobásy a špekáčky
    300104020: "UZENINY",    # Zabijačkové speciality
    300104007: "UZENINY",    # Salámy
    300104016: "UZENINY",    # Paštiky a masné výrobky
    300104032: "UZENINY",    # Saláty, pomazánky a pesta
    300104039: "UZENINY",    # Lahůdky
    300104049: "OSTATNI",    # Hotová jídla a přílohy
    300121878: "OSTATNI",    # Dárkové koše a kazety
}

# Nepotraviny (drogerie, kuchyňské potřeby) – vyřadit
NONFOOD_MAIN_CATEGORY = {300109043, 300124630}  # 300109043: mytí nádobí (Jar); 300124630: bambusová podložka na sushi
NONFOOD_NAME = re.compile(r"podložk|nádobí|mýdl|prací|čisticí", re.IGNORECASE)

_last_request = [0.0]
stats = {"requests": 0, "retries": 0, "failed": []}


def get_json(url):
    """Rate-limitované GET s exponenciálním zpožděním při 429/5xx a chybách sítě."""
    for attempt in range(MAX_RETRIES):
        wait = MIN_INTERVAL - (time.time() - _last_request[0])
        if wait > 0:
            time.sleep(wait)
        _last_request[0] = time.time()
        stats["requests"] += 1
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code not in (429, 500, 502, 503, 504):
                print(f"  HTTP {e.code} u {url}", file=sys.stderr)
                break
            print(f"  HTTP {e.code}, opakuji ({attempt + 1}/{MAX_RETRIES})", file=sys.stderr)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            print(f"  chyba {e!r}, opakuji ({attempt + 1}/{MAX_RETRIES})", file=sys.stderr)
        stats["retries"] += 1
        time.sleep(2 ** attempt)
    stats["failed"].append(url)
    return None


def slugify(text):
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def parse_size(text):
    """'250 g' -> (0.25, 'kg'); '0,66 l' -> (0.66, 'l'); '2 ks' -> (2, 'ks'); 'cca ...' -> None."""
    if not text or text.lower().startswith("cca"):
        return None, None
    m = re.fullmatch(r"\s*(\d+(?:[.,]\d+)?)\s*(g|kg|ml|l|ks)\s*", text)
    if not m:
        return None, None
    v = float(m.group(1).replace(",", "."))
    u = m.group(2)
    if u == "g":
        return round(v / 1000, 4), "kg"
    if u == "kg":
        return v, "kg"
    if u == "ml":
        return round(v / 1000, 4), "l"
    if u == "l":
        return v, "l"
    return v, "ks"


def fetch_parent_ids(parent):
    ids, page = [], 0
    while page < 50:
        d = get_json(f"{BASE}/categories/normal/{parent}/products?limit=100&page={page}")
        if d is None:
            break
        pids = d.get("productIds") or []
        if not pids:
            break
        ids += pids
        page += 1
    return ids


def fetch_sub_membership(parent):
    """Vrátí {productId: subId} pro podkategorie daného rodiče."""
    sub_of = {}
    d = get_json(f"{BASE}/categories/normal/{parent}/subcategories") or {}
    for sub in d.get("categoryIds") or []:
        page = 0
        while page < 50:
            r = get_json(f"{BASE}/categories/normal/{sub}/products?limit=100&page={page}")
            if r is None:
                break
            pids = r.get("productIds") or []
            if not pids:
                break
            for pid in pids:
                sub_of.setdefault(pid, sub)
            page += 1
    return sub_of


def build_record(p, category, group_ids):
    size_value, size_unit = parse_size(p.get("textualAmount"))
    if p.get("weightedItem"):
        size_value, size_unit = None, None
    slug = slugify(p.get("slug") or p["name"]) or str(p["id"])
    page_url = f"{PAGE_URL}/{p['id']}-{p.get('slug') or slug}"
    name = p["name"].replace("\xa0", " ").strip()
    rec = {"id": f"rohlik-{p['id']}-{slug}", "name": name}
    if p.get("brand"):
        rec["brand"] = p["brand"]
    rec["category"] = category
    if size_value is not None:
        rec["size_value"] = size_value
        rec["size_unit"] = size_unit
    rec["stores"] = [{"store": STORE, "receipt_name": None, "receipt_name_source": None, "url": page_url}]
    related = [g for g in group_ids if g != rec["id"]]
    if related:
        rec["related"] = related
    if p.get("images"):
        rec["image_url"] = p["images"][0]
    rec["sources"] = [page_url]
    return rec


def main():
    out_path = Path(__file__).resolve().parents[1] / "raw" / (Path(__file__).stem + ".jsonl")

    # 1) ID produktů z obou hlavních kategorií (stránkování)
    product_ids, seen = [], set()
    parent_of = {}
    for parent in PARENTS:
        ids = fetch_parent_ids(parent)
        print(f"kategorie {parent}: {len(ids)} ID", file=sys.stderr)
        for i in ids:
            parent_of.setdefault(i, parent)
            if i not in seen:
                seen.add(i)
                product_ids.append(i)
    print(f"unikátních ID: {len(product_ids)}", file=sys.stderr)

    # 2) příslušnost k podkategoriím
    sub_of = {}
    for parent in PARENTS:
        for pid, sub in fetch_sub_membership(parent).items():
            sub_of.setdefault(pid, sub)
    print(f"ID s podkategorií: {len(sub_of)}", file=sys.stderr)

    # 3) detaily po dávkách
    details = {}
    for n in range(0, len(product_ids), DETAIL_BATCH):
        batch = product_ids[n:n + DETAIL_BATCH]
        q = "&".join(f"products={i}" for i in batch)
        res = get_json(f"{BASE}/products?{q}")
        for p in res or []:
            details[p["id"]] = p
    print(f"detaily: {len(details)} z {len(product_ids)}", file=sys.stderr)

    # 4) záznamy
    included, skipped = [], {"nepotravina": 0, "archivovano": 0, "bez_detailu": 0}
    for pid in product_ids:
        p = details.get(pid)
        if p is None:
            skipped["bez_detailu"] += 1
            continue
        if p.get("type") not in (None, "PRODUCT") or p.get("archived"):
            skipped["archivovano"] += 1
            continue
        if p.get("mainCategoryId") in NONFOOD_MAIN_CATEGORY or NONFOOD_NAME.search(p["name"]):
            skipped["nepotravina"] += 1
            continue
        sub = sub_of.get(pid)
        if sub in SUB_CATEGORY:
            category = SUB_CATEGORY[sub]
        else:
            category = PARENTS[parent_of[pid]]
            if sub is not None:
                print(f"  neznámá podkategorie {sub} u {pid}, použit rodič", file=sys.stderr)
        included.append((p, category))

    # related: stejný název (liší se velikostí/variantou)
    by_name = {}
    for p, _ in included:
        by_name.setdefault(p["name"].strip().lower(), []).append(p)
    records = []
    for p, category in included:
        group = [f"rohlik-{q['id']}-{slugify(q.get('slug') or q['name']) or q['id']}" for q in by_name[p["name"].strip().lower()]]
        records.append(build_record(p, category, group))

    # kontrola unikátnosti id
    ids_out = [r["id"] for r in records]
    assert len(ids_out) == len(set(ids_out)), "duplicitní id"

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    cats = {}
    for r in records:
        cats[r["category"]] = cats.get(r["category"], 0) + 1
    print(f"zapsáno {len(records)} záznamů do {out_path}", file=sys.stderr)
    print(f"kategorie: {cats}", file=sys.stderr)
    print(f"vyřazeno: {skipped}", file=sys.stderr)
    print(f"požadavků: {stats['requests']}, opakování: {stats['retries']}, neúspěšné: {len(stats['failed'])}", file=sys.stderr)
    for url in stats["failed"]:
        print(f"  nešlo: {url}", file=sys.stderr)


if __name__ == "__main__":
    main()
