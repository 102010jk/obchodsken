#!/usr/bin/env python3
"""Hromadný sběr: Rohlík.cz, kategorie 300105000 (Mléčné a chlazené) – všechny stránky a podkategorie.

Výstup: data/foods/raw/03-rohlik-mlecne.jsonl (přepíše se). Spuštění: python3 data/foods/harvest/03-rohlik-mlecne.py
Požadavky: nejvýš 1 za sekundu, při 429/5xx exponenciální čekání, po 5 neúspěších se požadavek přeskočí.
Kategorie se určuje z podkategorie Rohlíku (CAT_MAP + PARENT), nepotraviny se vyřazují (NONFOOD_RULES).
"""
import json, os, re, subprocess, sys, time, unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.normpath(os.path.join(HERE, '..', 'raw', '03-rohlik-mlecne.jsonl'))
BASE = 'https://www.rohlik.cz/api/v1'
CATEGORY = 300105000
OBCHOD = 'rohlik'
MIN_INTERVAL = 1.0      # sekundy mezi požadavky (sdílený web – max 1 req/s)
BATCH = 40              # ID produktů na jeden požadavek na detaily
MAX_TRIES = 5           # počet pokusů na jeden požadavek

REQUESTS = [0]
_last = [0.0]


def http_get(url):
    """Vrátí tělo odpovědi (str), nebo None po neúspěchu. Dodržuje MIN_INTERVAL."""
    for attempt in range(1, MAX_TRIES + 1):
        wait = MIN_INTERVAL - (time.monotonic() - _last[0])
        if wait > 0:
            time.sleep(wait)
        _last[0] = time.monotonic()
        REQUESTS[0] += 1
        r = subprocess.run(['curl', '-sL', '-A', 'Mozilla/5.0', '--max-time', '60',
                            '-w', '\n%{http_code}', url], capture_output=True, text=True)
        body, _, code = r.stdout.rpartition('\n')
        code = int(code) if code.isdigit() else 0
        if code == 200:
            return body
        if 400 <= code < 500 and code != 429:
            print(f'  přeskočeno: HTTP {code} {url[:90]}', file=sys.stderr)
            return None
        if attempt < MAX_TRIES:
            time.sleep(2 ** attempt)   # 2, 4, 8, 16 s
    print(f'  přeskočeno po {MAX_TRIES} neúspěších: {url[:90]}', file=sys.stderr)
    return None


def slugify(s):
    s = unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode().lower()
    return re.sub(r'[^a-z0-9]+', '-', s).strip('-')


# ---- mapování podkategorií Rohlíku na kategorie aplikace (FORMAT.md) ----
# Podle uzlu nejblíž k produktu (vlastní uzel, pak rodič, ...). Vždy první nalezený.
CAT_MAP = {
    CATEGORY: 'MLECNE',
    300124994: 'MLECNE',    # XXL balení
    300124970: 'MLECNE',    # Sýry z čerstvého pultu
    300124986: 'MLECNE',    # Farmářské produkty
    300124993: 'VEJCE',     # Farmářské: Vejce a droždí
    300105026: 'MLECNE',    # Sýry
    300122648: 'MLECNE',    # Sýry k vínu
    300122651: 'ALKOHOL',   # Sýry k vínu > Dle druhu vína (víno)
    300105001: 'MLECNE',    # Mléko a mléčné nápoje
    300105006: 'NAPOJE',    # Rostlinné nápoje
    300105008: 'MLECNE',    # Jogurty a mléčné dezerty
    300105053: 'VEJCE',     # Vejce a droždí
    300105057: 'OSTATNI',   # Droždí
    300105048: 'MLECNE',    # Máslo, tuky a margaríny
    300105052: 'OSTATNI',   # Sádlo
    300122004: 'OSTATNI',   # Kitchin
    300105021: 'MLECNE',    # Smetany, šlehačky a tvarohy
    300105058: 'OSTATNI',   # Majonézy, tatarské omáčky a dresingy
    300121231: 'MLECNE',    # Bez laktózy, A2 a High protein
    300123064: 'MLECNE',    # High protein
    300123065: 'MLECNE',    # Tvarohy
}

# Rodič každé podkategorie v Rohlíku (z procházení stromu kategorie 300105000)
PARENT = {
    300105001: 300105000,
    300105002: 300105001,
    300105003: 300105001,
    300105004: 300105001,
    300105005: 300105001,
    300105006: 300105001,
    300105007: 300105001,
    300105008: 300105000,
    300105009: 300105008,
    300105010: 300105008,
    300105021: 300105000,
    300105022: 300105021,
    300105023: 300105021,
    300105024: 300105021,
    300105025: 300105021,
    300105026: 300105000,
    300105027: 300105026,
    300105028: 300105026,
    300105031: 300105026,
    300105040: 300105026,
    300105048: 300105000,
    300105049: 300105048,
    300105050: 300105048,
    300105051: 300105048,
    300105052: 300105048,
    300105053: 300105000,
    300105054: 300105053,
    300105055: 300105053,
    300105057: 300105053,
    300105058: 300105000,
    300105059: 300105058,
    300105060: 300105058,
    300105061: 300105058,
    300105069: 300105001,
    300105070: 300105008,
    300105072: 300105021,
    300105076: 300105053,
    300114171: 300105031,
    300114175: 300105031,
    300114177: 300105028,
    300114179: 300105028,
    300114181: 300105028,
    300114183: 300105028,
    300114187: 300105028,
    300114241: 300105010,
    300114243: 300105010,
    300114245: 300105010,
    300114329: 300105026,
    300114331: 300114329,
    300114333: 300114329,
    300114335: 300114329,
    300114337: 300114329,
    300114339: 300114329,
    300114341: 300114329,
    300114359: 300114329,
    300114361: 300114329,
    300114397: 300114329,
    300114403: 300105001,
    300114405: 300105021,
    300119767: 300114329,
    300120608: 300105026,
    300120609: 300120608,
    300120610: 300120608,
    300120681: 300114329,
    300121231: 300105000,
    300121232: 300121231,
    300121233: 300121231,
    300121234: 300121231,
    300121235: 300121231,
    300121236: 300121231,
    300121237: 300121231,
    300121397: 300120608,
    300121865: 300105026,
    300122004: 300105048,
    300122348: 300105048,
    300122373: 300105021,
    300122516: 300121231,
    300122648: 300105026,
    300122651: 300122648,
    300122652: 300122651,
    300122653: 300122651,
    300122654: 300122651,
    300122655: 300122651,
    300122656: 300122651,
    300122657: 300122651,
    300122658: 300122651,
    300122659: 300122651,
    300123064: 300121231,
    300123065: 300105021,
    300123204: 300123065,
    300123205: 300123065,
    300123206: 300123065,
    300123207: 300123065,
    300123208: 300123065,
    300123209: 300123065,
    300123217: 300120608,
    300123488: 300105031,
    300123498: 300105027,
    300123507: 300105026,
    300123509: 300123507,
    300123510: 300123507,
    300123521: 300105026,
    300123522: 300123521,
    300123523: 300123521,
    300123525: 300123521,
    300123532: 300105008,
    300123533: 300123532,
    300123534: 300123532,
    300123535: 300105008,
    300123537: 300123535,
    300123539: 300123535,
    300123542: 300105008,
    300123543: 300123542,
    300123545: 300123542,
    300123550: 300105008,
    300123551: 300123550,
    300123552: 300123550,
    300123555: 300105008,
    300123556: 300123555,
    300123557: 300123555,
    300123582: 300123064,
    300123583: 300123064,
    300124065: 300105026,
    300124066: 300105026,
    300124067: 300124066,
    300124068: 300124066,
    300124069: 300124066,
    300124070: 300105026,
    300124071: 300124070,
    300124072: 300124070,
    300124073: 300105027,
    300124075: 300105027,
    300124076: 300105027,
    300124077: 300105027,
    300124078: 300105027,
    300124079: 300105040,
    300124080: 300105040,
    300124081: 300105040,
    300124082: 300105040,
    300124083: 300105028,
    300124970: 300105000,
    300124978: 300124970,
    300124979: 300124970,
    300124980: 300124970,
    300124981: 300124970,
    300124986: 300105000,
    300124987: 300124986,
    300124988: 300124986,
    300124989: 300124986,
    300124991: 300124986,
    300124992: 300124986,
    300124993: 300124986,
    300124994: 300105000,
}



def category_of(node, names):
    """Vrátí (kategorie, None) nebo (None, jméno-podkategorie) pro neznámý uzel."""
    cur = node
    while cur is not None:
        if cur in CAT_MAP:
            return CAT_MAP[cur], None
        cur = PARENT.get(cur)
    return None, names


# ---- nepotraviny (vyřadit) ----
NONFOOD_RULES = [
    # (regex na jméno podkategorie Rohlíku, ...) – doplněno po průzkumu
]

# ---- podkategorie mimo strom 300105000: pravidla podle jména podkategorie Rohlíku ----
NAME_RULES = [
    # (regex na jméno podkategorie, kategorie)
]


def size_of(p):
    if p.get('weightedItem') or re.search(r'cca', p.get('name', ''), re.I):
        return None, None
    m = re.fullmatch(r'\s*(\d+(?:[.,]\d+)?)\s*(kg|g|ml|l|ks)\s*', p.get('textualAmount') or '')
    if not m:
        return None, None
    v, u = float(m.group(1).replace(',', '.')), m.group(2)
    if u == 'g':
        v, u = v / 1000, 'kg'
    elif u == 'ml':
        v, u = v / 1000, 'l'
    return round(v, 6), u


def main():
    t0 = time.time()
    # 1) všechna ID z kategorie, po stránkách
    ids, seen = [], set()
    for page in range(0, 200):
        body = http_get(f'{BASE}/categories/normal/{CATEGORY}/products?limit=100&page={page}')
        if body is None:
            break
        page_ids = json.loads(body).get('productIds', [])
        if not page_ids:
            break
        new = [i for i in page_ids if i not in seen]
        seen.update(page_ids)
        ids += new
        print(f'stránka {page}: {len(page_ids)} ID, nových {len(new)}', file=sys.stderr)
        if not new:
            break
    print(f'celkem ID z kategorie: {len(ids)}', file=sys.stderr)

    # 2) detaily po dávkách
    products = {}
    for i in range(0, len(ids), BATCH):
        chunk = ids[i:i + BATCH]
        body = http_get(f'{BASE}/products?' + '&'.join(f'products={x}' for x in chunk))
        if body is None:
            continue
        for p in json.loads(body):
            products[p['id']] = p
        if (i // BATCH) % 5 == 0:
            print(f'detaily: {min(i + BATCH, len(ids))}/{len(ids)}', file=sys.stderr)
    print(f'detaily získány: {len(products)}', file=sys.stderr)

    # 3) záznamy
    name_cache = {}
    stats = {'archivované': 0, 'nepotraviny': 0, 'bez kategorie': 0}
    unresolved = {}
    records = {}
    for pid, p in products.items():
        if p.get('archived'):
            stats['archivované'] += 1
            continue
        main = p.get('mainCategoryId')
        cat, unknown = category_of(main, None)
        if cat is None:
            # podkategorie mimo strom: zjistit její jméno (jedno ověření na uzel)
            if main not in name_cache:
                b = http_get(f'{BASE}/categories/normal/{main}')
                name_cache[main] = json.loads(b).get('name') if b else None
            sub = name_cache[main] or ''
            if any(re.search(rx, sub, re.I) for rx in NONFOOD_RULES):
                stats['nepotraviny'] += 1
                continue
            cat = next((c for rx, c in NAME_RULES if re.search(rx, sub, re.I)), None)
            if cat is None:
                stats['bez kategorie'] += 1
                unresolved[(main, sub)] = unresolved.get((main, sub), 0) + 1
                continue
        rid_slug = slugify(p.get('slug') or p['name'])
        rid = f'{OBCHOD}-{pid}-{rid_slug}'
        url = f"https://www.rohlik.cz/{pid}-{p['slug']}"
        v, u = size_of(p)
        rec = {
            'id': rid,
            'name': p['name'],
            'brand': p.get('brand') or None,
            'category': cat,
            'size_value': v,
            'size_unit': u,
            'stores': [{'store': 'Rohlík', 'receipt_name': None, 'receipt_name_source': None, 'url': url}],
            'image_url': (p.get('images') or [None])[0],
            'sources': [url],
        }
        records[rid] = {k: val for k, val in rec.items() if val is not None}
    # 4) zápis (přepis výstupu)
    tmp = OUT + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        for rid in sorted(records):
            f.write(json.dumps(records[rid], ensure_ascii=False) + '\n')
    os.replace(tmp, OUT)
    print(f'zapsáno záznamů: {len(records)} -> {OUT}', file=sys.stderr)
    print(f'vyřazeno: {stats}', file=sys.stderr)
    if unresolved:
        print('nerozřazené podkategorie (main_id, jméno): počet', file=sys.stderr)
        for (mid, sub), n in sorted(unresolved.items(), key=lambda x: -x[1]):
            print(f'  {mid} {sub!r}: {n}', file=sys.stderr)
    print(f'požadavků na web: {REQUESTS[0]}, doba: {time.time() - t0:.0f} s', file=sys.stderr)


if __name__ == '__main__':
    main()
