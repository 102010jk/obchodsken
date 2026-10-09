#!/usr/bin/env python3
"""Hromadný sběr Košík.cz: trvanlivé, sladkosti/snacky, nápoje (vč. kávy a čaje), alkohol,
mražené, dětská výživa. Výstup: data/foods/raw/07-kosik-trvanlive-napoje.jsonl (přepsán).

Jak se stránkuje: endpoint /api/front/page/products/flexible ignoruje parametr `cursor` (vrací
vždy prvních 30), proto se listingy dělí podkategoriemi a facetem značek (`filters=brands:<id>`).
Každý uzel: pokud totalCount <= 30, je hotovo; jinak se jde do podkategorií; u listového uzlu
se jde po značkách. Zbytek (listový uzel + jedna značka > 30) se loguje jako zkrácený.

Spuštění:  python3 data/foods/harvest/07-kosik-trvanlive-napoje.py [--with-details]
  --with-details  stáhne i detail každého produktu a hledá EAN (default vypnuto: u dvou
                  ověřených produktů detail EAN neobsahuje, jen složení/výživu, které schéma nemá).
Limity: max 1 požadavek za sekundu; při 429/5xx exponenciální čekání (2,4,8,16,32 s), po 5 neúspěších přeskočit.
Cache požadavků: data/foods/harvest/.cache/07-kosik.jsonl (re-run pokračuje bez nových požadavků).
"""
import json, os, re, subprocess, sys, time, unicodedata, urllib.parse

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
OUT = os.path.join(ROOT, "data", "foods", "raw", "07-kosik-trvanlive-napoje.jsonl")
CACHE = os.path.join(ROOT, "data", "foods", "harvest", ".cache", "07-kosik.jsonl")
BASE = "https://www.kosik.cz"
API = BASE + "/api/front/page/products/flexible"
UA = "Mozilla/5.0"
LIMIT = 30
MIN_INTERVAL = 1.0
MAX_RETRIES = 5
MAX_DEPTH = 12
WITH_DETAILS = "--with-details" in sys.argv

# Kořeny (slug, základní kategorie). Vše pod nimi se projde rekurzivně.
ROOTS = [
    ("c1211-trvanlive", "TRVANLIVE"), ("c2659-trvanlive", "TRVANLIVE"), ("c5944-trvanlive", "TRVANLIVE"),
    ("c2715-snacky-a-krekry", "TRVANLIVE"), ("c2711-bramburky-a-chipsy", "TRVANLIVE"),
    ("c3300-susenky-snacky-a-sladke-tycinky", "TRVANLIVE"),
    ("c1107-napoje", "NAPOJE"), ("c3141-napoje", "NAPOJE"), ("c5959-napoje", "NAPOJE"),
    ("c1195-nealko", "NAPOJE"), ("c4939-nealkoholicka", "NAPOJE"),
    ("c1333-s-alkoholem", "ALKOHOL"),
    ("c1083-mrazene", "MRAZENE"),
    ("c1609-detska-vyziva", "TRVANLIVE"), ("c1611-kojenecka-mleka", "TRVANLIVE"),
    ("c1619-kojenecke-vody-a-napoje", "NAPOJE"),
]

PRIORITY = ["ALKOHOL", "NAPOJE", "SLADKOSTI", "MRAZENE", "TRVANLIVE"]

# Tokeny (slova ze slugů podkategorií, oddělená pomlčkou). Podle nich se určí kategorie.
ALKOHOL_T = {"alkohol", "alkoholem", "piva", "pivo", "vina", "vino", "lihoviny", "cidery", "cider",
             "chnapky", "sekt", "vermut", "vodka", "whisky", "rum", "likery", "absint", "becherovka"}
NAPOJE_T = {"napoje", "napoj", "napoju", "dzusy", "dzus", "nektar", "caje", "caj", "kava", "kavy",
            "kakao", "vody", "voda", "limonady", "sirupy", "nealko", "nealkoholicka", "energy",
            "sodastream", "vychlazeno", "ledove", "ledova", "vychlazene"}
SLADKOSTI_T = {"sladke", "sladkosti", "cokolady", "cokolada", "cokoladove", "cokoladova", "bonbony",
               "bonboniery", "susenky", "oplatky", "tycinky", "zvykacky", "zvykacka", "lizatka",
               "draze", "pendreky", "karamelove", "perniky", "cukrovi", "mikulas", "vanoce",
               "marshmallow", "piskoty", "trubicky", "cukrarske", "pomazanky", "lizatko"}
# Nepotraviny – vyřadí záznam (pokud se stejný produkt neobjeví i v potravinové větvi).
NONFOOD_T = {"kosmetika", "kosmetiky", "kosmet", "prani", "nadobi", "plenky", "pleny", "potreby",
             "pece", "drogerie", "cisteni", "cistici", "hygiena", "pribor", "pribory", "telova",
             "vlasy", "zubni", "holeni", "masky", "odpady", "septiky", "zmekcovace", "hracky",
             "mydla", "dezodoranty", "balzamy", "pleti"}
# Chlazené / masné / mléčné / čerstvé pečivo – patří druhému agentovi; vyřadí se,
# pokud větev nejde přes nápojovou kategorii nebo trvanlivé pečivo.
CHILLED_T = {"mlecne", "jogurty", "jogurt", "jogurtove", "tvarohy", "chlazene", "chlazeny", "uzeniny",
             "salamy", "maso", "ryby", "vejce", "syrove", "syry", "pecivo", "dezerty"}
TRVANLIVE_T = {"trvanlive", "trvanliva", "trvanlivy"}

def slug_base(slug):
    return re.sub(r"^c\d+-", "", slug)

def tokens_of(slugs):
    out = set()
    for s in slugs:
        out.update(slug_base(s).split("-"))
    return out

def categorize(base, path):
    """Vrátí kategorii pro jeden výskyt produktu v dané větvi, nebo None (vyřadit)."""
    toks_all = tokens_of(path)
    toks_nonroot = tokens_of(path[1:]) if len(path) > 1 else set()
    if toks_all & NONFOOD_T:
        return None
    food_ctx = bool(toks_nonroot & (NAPOJE_T | ALKOHOL_T))
    chilled_hits = toks_nonroot & CHILLED_T
    if chilled_hits and not food_ctx:
        # trvanlivé pečivo (např. „trvanlivé sladké pečivo“) necháme, ostatní chlazené vyřadíme
        if not (toks_nonroot & TRVANLIVE_T and chilled_hits <= {"pecivo"}):
            return None
    if toks_all & ALKOHOL_T:
        return "ALKOHOL"
    if toks_all & NAPOJE_T:
        return "NAPOJE"
    if toks_all & SLADKOSTI_T:
        return "SLADKOSTI"
    return base

# ---------- HTTP s limitem a zálohou ----------
_last = [0.0]
_stats = {"live": 0, "retries": 0, "skipped": 0, "cache_hits": 0}
_cache = {}

def load_cache():
    if os.path.exists(CACHE):
        for line in open(CACHE, encoding="utf-8"):
            row = json.loads(line)
            _cache[row["url"]] = row["data"]

def _curl(url):
    wait = MIN_INTERVAL - (time.time() - _last[0])
    if wait > 0:
        time.sleep(wait)
    _last[0] = time.time()
    _stats["live"] += 1
    p = subprocess.run(["curl", "-sL", "-A", UA, "-o", "-", "-w", "\n%{http_code}", url],
                       capture_output=True, text=True, timeout=120)
    body, _, code = p.stdout.rpartition("\n")
    return int(code or 0), body

def http_json(url):
    if url in _cache:
        _stats["cache_hits"] += 1
        return _cache[url]
    for attempt in range(MAX_RETRIES + 1):
        code, body = _curl(url)
        if code == 200:
            try:
                data = json.loads(body)
            except ValueError:
                return None
            _cache[url] = data
            os.makedirs(os.path.dirname(CACHE), exist_ok=True)
            with open(CACHE, "a", encoding="utf-8") as f:
                f.write(json.dumps({"url": url, "data": data}, ensure_ascii=False) + "\n")
            return data
        if code in (400, 404, 405):
            return None  # chyba požadavku – opakovat nemá smysl
        if attempt < MAX_RETRIES:
            _stats["retries"] += 1
            time.sleep(2 ** (attempt + 1))
    _stats["skipped"] += 1
    print(f"  přeskočeno po {MAX_RETRIES} neúspěších: {url}", file=sys.stderr)
    return None

def listing(slug, brand):
    q = {"slug": slug, "limit": LIMIT}
    if brand:
        q["filters"] = f"brands:{brand}"
    d = http_json(API + "?" + urllib.parse.urlencode(q))
    if d is None:
        return None, None
    p = d.get("products") or {}
    items = p.get("items") or []
    subs = [s["url"].strip("/") for s in d.get("subCategories") or [] if s.get("url")]
    brands = []
    for f in d.get("filters") or []:
        if f.get("id") == "brands":
            for it in f.get("items") or []:
                if it.get("count"):
                    brands.append((str(it["id"]), it["count"]))
    return {"total": p.get("totalCount") or 0, "items": items, "subs": subs, "brands": brands}, API + "?" + urllib.parse.urlencode(q)

# ---------- sběr ----------
found = {}        # product id -> {"item": ..., "cats": [...], "sources": [...]}
visited = set()
truncated = []
uncovered = []

def add(res, path, base, url):
    for it in res["items"]:
        pid = it["id"]
        rec = found.setdefault(pid, {"item": it, "cats": [], "sources": []})
        cat = categorize(base, path)
        if cat is not None:
            rec["cats"].append(cat)
        if url not in rec["sources"] and len(rec["sources"]) < 3:
            rec["sources"].append(url)

def visit(slug, brand, parent_path, base, depth):
    key = (slug, brand)
    if key in visited or depth > MAX_DEPTH:
        return
    visited.add(key)
    res, url = listing(slug, brand)
    if res is None:
        return
    path = parent_path + [slug]
    if res["total"] <= len(res["items"]):
        add(res, path, base, url)
        return
    if res["subs"]:
        add(res, path, base, url)
        for s in res["subs"]:
            visit(s, brand, path, base, depth + 1)
        return
    add(res, path, base, url)
    if brand is None:
        covered = 0
        for bid, cnt in res["brands"]:
            covered += cnt
            visit(slug, bid, parent_path, base, depth + 1)
        if res["total"] - covered > 0:
            uncovered.append((slug, res["total"] - covered))
    else:
        truncated.append((slug, brand, res["total"]))

def slugify(s, maxlen=60):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:maxlen].rstrip("-")

def size_of(pq):
    if not pq or pq.get("value") is None:
        return None, None
    v, u = pq["value"], pq.get("unit")
    if u == "g":
        return round(v / 1000, 3), "kg"
    if u == "kg":
        return round(v, 3), "kg"
    if u == "ml":
        return round(v / 1000, 3), "l"
    if u == "l":
        return round(v, 3), "l"
    return None, None  # např. „dávek“ – nejde převést na kg/l/ks

def ean_valid(code):
    if not re.fullmatch(r"\d{8}|\d{13}", code):
        return False
    digits = [int(c) for c in code]
    check = digits[-1]
    body = digits[:-1][::-1]
    s = sum(d * (3 if i % 2 == 0 else 1) for i, d in enumerate(body))
    return (10 - s % 10) % 10 == check

def find_eans(obj, out):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if re.search(r"ean|gtin|barcode", k, re.I) and isinstance(v, (str, int)):
                s = str(v).strip()
                if ean_valid(s):
                    out.add(s)
            find_eans(v, out)
    elif isinstance(obj, list):
        for v in obj:
            find_eans(v, out)
    return out

def main():
    load_cache()
    for slug, base in ROOTS:
        print(f"kořen {slug}", file=sys.stderr)
        visit(slug, None, [], base, 0)
    print(f"stránek/požadavků: živě {_stats['live']}, z cache {_stats['cache_hits']}, "
          f"opakování {_stats['retries']}, přeskočeno {_stats['skipped']}", file=sys.stderr)

    records = []
    dropped = 0
    for pid, rec in found.items():
        cats = [c for c in rec["cats"]]
        if not cats:
            dropped += 1
            continue
        cat = min(cats, key=lambda c: PRIORITY.index(c))
        it = rec["item"]
        name = re.sub(r"\s+", " ", it["name"]).strip()
        brand = (it.get("brand") or {}).get("name")
        sv, su = size_of(it.get("productQuantity"))
        image = it.get("image")
        image = image.replace("WIDTHxHEIGHT", "300x300") if image else None  # ověřeno: 200 image/png
        eans = None
        if WITH_DETAILS:
            d = http_json(f"{BASE}/api/front/product/slug/{it['url'].lstrip('/')}")
            if d:
                found_eans = sorted(find_eans(d, set()))
                eans = found_eans or None
        rid = f"kosik-{pid}-{slugify(name)}"
        rec_out = {
            "id": rid,
            "name": name,
            "brand": brand,
            "category": cat,
            "size_value": sv,
            "size_unit": su,
            "eans": eans,
            "stores": [{"store": "Košík", "receipt_name": None, "receipt_name_source": None,
                        "url": BASE + it["url"]}],
            "image_url": image,
            "sources": rec["sources"],
        }
        records.append({k: v for k, v in rec_out.items() if v is not None})

    records.sort(key=lambda r: r["id"])
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"zapsáno {len(records)} záznamů do {OUT} (vyřazeno nepotravin/chlazeného: {dropped})", file=sys.stderr)
    if truncated:
        print(f"zkrácené větve (>30 produktů i po značce): {len(truncated)}", file=sys.stderr)
    if uncovered:
        print(f"produkty bez značky mimo facet: {sum(n for _, n in uncovered)} v {len(uncovered)} větvích", file=sys.stderr)

if __name__ == "__main__":
    main()
