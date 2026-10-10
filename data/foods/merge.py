#!/usr/bin/env python3
"""Sloučí data/foods/raw/*.jsonl do data/foods/foods.jsonl (stejné id / stejný název+značka+velikost = jeden
záznam, obchody se sjednotí) a vyrobí z toho katalog aplikace app/src/main/assets/catalog/web.jsonl."""
import glob, json, re, unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STORE_FIX = {"Košík.cz": "Košík", "BENE NÁPOJE": "Bene nápoje", "TAMDA FOODS": "Tamda Foods",
             "ESO MARKET": "ESO Market", "TRAVEL FREE": "Travel Free"}

def key(o):
    n = ''.join(c for c in unicodedata.normalize('NFD', f"{o.get('brand') or ''} {o['name']}".lower())
                if unicodedata.category(c) != 'Mn')
    return re.sub(r'[^a-z0-9]+', ' ', n).strip(), o.get('size_value'), o.get('size_unit')

merged, by_key = {}, {}
for f in sorted(glob.glob(str(ROOT / 'data/foods/raw/*.jsonl'))):
    for line in open(f, encoding='utf-8'):
        if not line.strip():
            continue
        o = json.loads(line)
        if not (o.get('size_value') or 0) > 0:
            o.pop('size_value', None); o.pop('size_unit', None)
        for s in o.get('stores', []):
            s['store'] = STORE_FIX.get(s['store'], s['store'])
        k = key(o)
        prev = merged.get(o['id']) or merged.get(by_key.get(k))
        if prev is None:
            merged[o['id']] = o
            by_key[k] = o['id']
            continue
        have = {s['store'] for s in prev['stores']}
        prev['stores'] += [s for s in o['stores'] if s['store'] not in have]
        for fld in ('brand', 'image_url', 'size_value', 'size_unit'):
            if not prev.get(fld) and o.get(fld):
                prev[fld] = o[fld]
        prev['eans'] = sorted(set(prev.get('eans') or []) | set(o.get('eans') or []))
        prev['sources'] = list(dict.fromkeys(prev['sources'] + o['sources']))

out = ROOT / 'data/foods/foods.jsonl'
with open(out, 'w', encoding='utf-8') as w:
    for o in merged.values():
        w.write(json.dumps(o, ensure_ascii=False) + '\n')

def qty(o):
    v, u = o.get('size_value'), o.get('size_unit')
    if v is None:
        return None
    if u == 'kg' and v < 1:
        return f"{round(v * 1000):g} g"
    if u == 'l' and v < 1:
        return f"{round(v * 1000):g} ml"
    return f"{v:g} {u}"

cat = ROOT / 'app/src/main/assets/catalog/web.jsonl'
with open(cat, 'w', encoding='utf-8') as w:
    w.write('// Generováno z data/foods/foods.jsonl skriptem data/foods/merge.py – needitovat ručně.\n')
    for o in merged.values():
        st = o['stores'][0] if o['stores'] else {}
        c = {"id": o['id'], "name": o['name'], "category": o['category']}
        if st.get('store'): c['store'] = st['store']
        for k2, v2 in (('brand', o.get('brand')), ('quantity', qty(o)), ('image', o.get('image_url')),
                       ('url', st.get('url')), ('eans', o.get('eans') or None),
                       ('aliases', [s['receipt_name'] for s in o['stores'] if s.get('receipt_name')] or None),
                       ('source', o['sources'][0] if o.get('sources') else None)):
            if v2: c[k2] = v2
        w.write(json.dumps(c, ensure_ascii=False) + '\n')
print(f"Sloučeno: {len(merged)} potravin -> {out.relative_to(ROOT)} a {cat.relative_to(ROOT)}")
