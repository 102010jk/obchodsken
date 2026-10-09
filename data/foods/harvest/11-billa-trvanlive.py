#!/usr/bin/env python3
"""Hromadný sběr Billa (online nákup www.billa.cz) -> data/foods/raw/11-billa-trvanlive.jsonl (přepíše).

Rozsah: všechny listové kategorie potravin KROMĚ mléčných výrobků, masa/ryb, uzenin, pečiva
(ty sbírá jiný agent), chlazeného sortimentu a nepotravin (drogerie, domácnost, tabák, kuchyňské potřeby).
Mapování kategorií je v MAP_* částech níže; každá vyřazená/zařazená větev se vypíše na stderr.

Zdroj (JSON API, které volá stránka; ověřeno v JS bundlu a požadavky):
  GET /api/product-discovery/categories/tree
  GET /api/product-discovery/categories/{slug}/products?page={n}&pageSize=100
      page je od 0, offset = page * pageSize; odpověď: results, total
Detail produktu (/products/{sku}) se nestahuje: seznam obsahuje všechna pole, která FORMAT používá,
a detail čárový kód (EAN) také nemá.
URL produktu: https://www.billa.cz/produkt/{slug}/{sku} – ověřeno: skutečný produkt vrací 200
s názvem v HTML, neexistující SKU 404.

Šetrnost: nejvýše 1 požadavek za sekundu; při 429, 5xx nebo síťové chybě exponenciální čekání
(2, 4, 8, 16 s); po 5 neúspěších stránku přeskočit (zapíše se do souhrnu).

Spuštění:  python3 data/foods/harvest/11-billa-trvanlive.py
Kontrola:  python3 data/foods/validate.py data/foods/raw/11-billa-trvanlive.jsonl
"""
import json
import os
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://www.billa.cz"
API = BASE + "/api/product-discovery"
UA = "Mozilla/5.0"
MIN_INTERVAL = 1.0      # s mezi požadavky (max 1 za sekundu)
MAX_TRIES = 5           # pokusů na jeden požadavek
PAGE_SIZE = 100
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.normpath(os.path.join(HERE, "..", "raw", "11-billa-trvanlive.jsonl"))

# ---------------------------------------------------------------- mapování kategorií
EXCL_TOP = {
    "tabakove-produkty-3018",               # tabák
    "pecivo-1198",                          # pečivo (jiný agent)
    "chlazene-mlecne-a-rostlinne-vyrobky-1207",  # chlazené / mléčné (jiný agent)
    "maso-a-ryby-1263",                     # maso a ryby
    "drogerie-a-kosmetika-2426",            # drogerie
    "domacnost-2427",                       # domácnost
}
# přesné názvy uzlů (kterýkoli předek i list), které se vyřazují
EXCL_EXACT = {
    "Pečivo", "Mražené pečivo", "Chléb", "Slané pečivo", "Sladké pečivo", "Bagety a sendviče",
    "Chlebíčky", "Mléčné", "Mléčné a jogurtové nápoje", "Mléčné a ledové kávy",
    "Mléčné, jogurtové a zakysané nápoje", "Mléčné výrobky", "Podle regionů",
    "Trvanlivé mléko", "Kondenzované mléko", "Sušené mléko", "Čerstvé mléko", "Máslo a margaríny",
}
# regulární výraz na spojené názvy předků a listu (malá písmena)
EXCL_RE = re.compile(
    r"masa\b|maso|masov|uzenin|lahůd|delikates|šunk|salám|párk|sýr|slanin|pršut|karé|carpacc|"
    r"aspik|utopenc|paštik|závitk|chlebíč|sendvič|zabijačk|chlazen|čerstvé těstoviny|zmrzlin|"
    r"bezlaktóz|pleny|hračk|vlhčen|praní|kosmetik|zuby|těhotn|podestýl|příslušenství|"
    r"servírování|pomůcky|kytice|drogeri|tofu|tempeh|\bryby\b|\brybí\b|\bryba\b|"
    r"jogurt|tvaroh|kefír|podmáslí|šlehačk|smetan|másl|margarín"
)
EXCL_RE = re.compile(EXCL_RE.pattern, re.IGNORECASE)
ALCOHOL_NAMES = {"Pivo", "Víno", "Lihoviny", "Cidery", "Alkoholické", "Alkoholické nápoje"}
NON_ALCOHOL_NAMES = {"Nealkoholická", "Dealkoholizovaná vína"}
NAPOJE_NAMES = {
    "Nápoje", "Nealko", "Káva", "Čaj", "Kávoviny", "Sirupy", "Rostlinné nápoje", "Vody a minerálky",
    "Vody a limonády", "Džusy a ovocné nápoje", "Limonády a energy", "Ostatní nápoje",
    "Čaj, kakao a horká čokoláda", "Kapsle a pody do kávovarů", "Mletá", "Zrnková", "Instantní káva",
    "nealkoholické nápoje, Smoothie, shots", "Nápoje pro děti",
}
SLADKOSTI_NAMES = {
    "Cukrovinky", "Sušenky a oplatky", "Piškoty a jemné pečivo", "Tyčinky", "Čokoládové",
    "Proteinové", "Cereální a ostatní", "Bonbóny a lízátka", "Čokolády",
}
OSTATNI_NAMES = {
    "Dětská strava", "Dětská strava a nápoje", "Péče o dítě", "Hotová jídla", "Hotová jídla a instatní pokrmy",
    "Hotová jídla a instantní pokrmy", "Hotová jídla a polotovary", "Doplňky stravy", "Proteinová strava",
    "Potraviny se sníženým obsahem cukru", "Bílkovinové produkty", "Rostlinné nugetky, kuličky a burgery",
    "Kapsičky do ruky", "Příkrmy a přesnídávky pro děti", "Svačinky", "Svačinky pro nejmenší",
    "Kojenecká a batolecí mléka",
}
UZENINY_HOTOVA_LEAVES = {"Sushi", "Pizza", "Hotové zeleninové saláty"}
UZENINY_HOTOVA_ANCESTORS = {"Hotová jídla", "Hlavní jídla"}


def map_leaf(path):
    """path = [uzel nejvyšší úrovně, ..., list]. Vrátí kód kategorie FORMAT.md, nebo None (vyřadit)."""
    top = path[0]["slug"]
    names = [n.get("name", "") for n in path]
    leaf = names[-1]
    if top in EXCL_TOP:
        return None
    if any(n in EXCL_EXACT for n in names):
        return None
    # název nejvyšší úrovně se nekontroluje (např. „Uzeniny, lahůdky a hotová jídla“ by vyřadil vše)
    if EXCL_RE.search(" / ".join(names[1:])):
        return None

    if top == "trvanlive-potraviny-1332":
        return "TRVANLIVE"
    if top == "cukrovinky-1449":
        return "SLADKOSTI"
    if top == "mrazene-1307":
        return "MRAZENE"
    if top == "mazlicci-1630":
        return "ZVIRATA"
    if top == "ovoce-a-zelenina-1165":
        if path[-1]["slug"] in ("susene-2023", "orechy-a-seminka-2277", "zpracovani-ovoce-a-zeleniny-2957"):
            return "TRVANLIVE"
        return "OVOCE_ZELENINA"
    if top == "pece-o-dite-1582":
        if any(n.startswith("Nápoje pro děti") for n in names):
            return "NAPOJE"
        return "OSTATNI"
    if top in ("billa-vlastni-vyroba-2030", "setrime-jidlem-2270"):
        return "OSTATNI"
    if top == "uzeniny-lahudky-a-hotova-jidla-1276":
        # z tohoto stromu jen hotová jídla (masa, lahůdky, sýry, uzeniny jsou vyřazeny výše)
        if any(n in UZENINY_HOTOVA_ANCESTORS for n in names) or leaf in UZENINY_HOTOVA_LEAVES:
            return "OSTATNI"
        return None
    if top in ("napoje-1474", "farmarske-a-lokalni-produkty-1667", "specialni-a-rostlinna-vyziva-1576"):
        return map_mixed(names, path)
    return None


def map_mixed(names, path):
    """Smíšené větve: nápoje/alkohol, sladkosti, dětská výživa, trvanlivé, ovoce a zelenina, mražené."""
    leaf = names[-1]
    if any(n in ALCOHOL_NAMES for n in names) or leaf in ALCOHOL_NAMES:
        if any(n in NON_ALCOHOL_NAMES for n in names):
            return "NAPOJE"
        return "ALKOHOL"
    if any(n in NAPOJE_NAMES for n in names):
        return "NAPOJE"
    if any(n in SLADKOSTI_NAMES for n in names):
        return "SLADKOSTI"
    if any(n in OSTATNI_NAMES for n in names):
        return "OSTATNI"
    if any(n == "Ovoce a zelenina" for n in names):
        return "OVOCE_ZELENINA"
    if any(n == "Mražené" for n in names):
        return "MRAZENE"
    return "TRVANLIVE"


# ---------------------------------------------------------------- HTTP s šetrností
_last = [0.0]
stats = {"requests": 0, "retries": 0, "failed_requests": 0}


def log(*args):
    print(*args, file=sys.stderr, flush=True)


def get_json(url):
    """Vrátí JSON, nebo None (404 nebo vyčerpané pokusy). Dodržuje MIN_INTERVAL."""
    for attempt in range(MAX_TRIES):
        wait = MIN_INTERVAL - (time.monotonic() - _last[0])
        if wait > 0:
            time.sleep(wait)
        _last[0] = time.monotonic()
        stats["requests"] += 1
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            if e.code != 429 and e.code < 500:
                log(f"  HTTP {e.code}, neopakuji: {url}")
                stats["failed_requests"] += 1
                return None
            err = f"HTTP {e.code}"
        except (urllib.error.URLError, TimeoutError, ConnectionError, ValueError) as e:
            err = f"chyba {e!r}"
        stats["retries"] += 1
        if attempt == MAX_TRIES - 1:
            break
        back = 2 ** (attempt + 1)  # 2, 4, 8, 16 s
        log(f"  {err} – čekám {back} s a zkouším znovu: {url}")
        time.sleep(back)
    stats["failed_requests"] += 1
    log(f"  VZDÁNO po {MAX_TRIES} pokusech: {url}")
    return None


# ---------------------------------------------------------------- pomocné funkce
def slugify(text):
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = text.lower().replace("%", " procent ")
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")


def parse_size(p):
    """Vrátí (hodnota, jednotka kg|l) nebo None. Vážené zboží a neznámé jednotky se vynechají."""
    if p.get("weightArticle") or p.get("weightPieceArticle"):
        return None
    try:
        amount = float(str(p.get("amount", "")).replace(",", "."))
    except ValueError:
        return None
    unit = (p.get("volumeLabelShort") or "").strip().lower()
    table = {"g": (0.001, "kg"), "kg": (1.0, "kg"), "ml": (0.001, "l"), "cl": (0.01, "l"), "l": (1.0, "l")}
    if unit not in table or amount <= 0:
        return None
    factor, out_unit = table[unit]
    value = round(amount * factor, 4)
    return (int(value) if float(value).is_integer() else value), out_unit


SIZE_IN_NAME = re.compile(r"\b\d+(?:[.,]\d+)?\s?(?:g|kg|ml|l|cl|lt|ks)\b|\b\d+\s?x\s?\d+\s?(?:g|ml)\b", re.I)


def related_key(rec):
    base = SIZE_IN_NAME.sub(" ", rec["name"])
    return (rec.get("brand") or "").lower() + "|" + rec["category"] + "|" + slugify(base)


# ---------------------------------------------------------------- hlavní běh
def leaves(node, path):
    path = path + [node]
    children = node.get("children") or []
    if not children:
        yield path
    for child in children:
        yield from leaves(child, path)


def fetch_leaf(slug):
    """Stáhne všechny stránky listové kategorie. Vrátí (položky, total, complete)."""
    base = f"{API}/categories/{slug}/products"
    items, page, total, complete = [], 0, None, True
    while True:
        query = urllib.parse.urlencode({"page": page, "pageSize": PAGE_SIZE})
        data = get_json(f"{base}?{query}")
        if data is None:
            complete = False
            break
        results = data.get("results") or []
        total = data.get("total", total)
        items.extend(results)
        page += 1
        if not results or page * PAGE_SIZE >= (total or 0):
            break
    return items, total or 0, complete, f"{base}"


def main():
    tree = get_json(f"{API}/categories/tree")
    if not isinstance(tree, list):
        log("Strom kategorií se nepodařilo stáhnout.")
        return 1

    plan = []  # (path, code)
    excluded = []
    for top in tree:
        for path in leaves(top, []):
            code = map_leaf(path)
            label = " > ".join(n.get("name", "") for n in path)
            if code is None:
                excluded.append(label)
            else:
                plan.append((path, code))
    seen_slugs = set()
    log(f"Listových kategorií zařazeno: {len(plan)}, vyřazeno: {len(excluded)}")

    records = {}     # sku -> záznam (první výskyt rozhoduje o kategorii)
    raw_seen = set()
    incomplete = []
    for path, code in plan:
        slug = path[-1]["slug"]
        if slug in seen_slugs:
            continue
        seen_slugs.add(slug)
        items, total, complete, listing_url = fetch_leaf(slug)
        if not complete:
            incomplete.append(slug)
        new = 0
        for p in items:
            sku = p.get("sku")
            if not sku or sku in raw_seen:
                continue
            raw_seen.add(sku)
            if not p.get("published", True) or p.get("medical"):
                continue
            slug_p = p.get("slug")
            name = re.sub(r"\s+", " ", p.get("name") or "").strip()
            if not name or not slug_p:
                continue
            brand = re.sub(r"\s+", " ", (p.get("brand") or {}).get("name") or "").strip() or None
            url = f"{BASE}/produkt/{slug_p}/{sku}"
            rec = {
                "id": f"billa-{sku.lower()}-{slugify(name)[:60].rstrip('-')}",
                "name": name,
            }
            if brand:
                rec["brand"] = brand
            rec["category"] = code
            size = parse_size(p)
            if size:
                rec["size_value"], rec["size_unit"] = size
            rec["stores"] = [{"store": "Billa", "receipt_name": None, "receipt_name_source": None, "url": url}]
            if p.get("images"):
                rec["image_url"] = p["images"][0]
            rec["sources"] = [url, listing_url]
            records[sku] = rec
            new += 1
        log(f"{slug} [{code}] total={total} stažené={len(items)} nové={new}"
            + ("" if complete else " NEÚPLNÉ"))

    # související: stejná značka + kategorie + název bez gramáže
    groups = {}
    for rec in records.values():
        groups.setdefault(related_key(rec), []).append(rec)
    for members in groups.values():
        if len(members) > 1:
            for rec in members:
                rec["related"] = [m["id"] for m in members if m is not rec]

    tmp = OUT + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        for rec in records.values():
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    os.replace(tmp, OUT)

    log("")
    log(f"Zapsáno záznamů: {len(records)} -> {OUT}")
    log(f"Požadavků: {stats['requests']}, opakování: {stats['retries']}, neúspěšných: {stats['failed_requests']}")
    if incomplete:
        log(f"Neúplné kategorie ({len(incomplete)}): {', '.join(incomplete)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
