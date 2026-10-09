#!/usr/bin/env python3
"""Kontrola souborů databáze potravin (formát viz FORMAT.md). Použití: validate.py soubor.jsonl [...]"""
import json, re, sys

CATEGORIES = {"OVOCE_ZELENINA", "PECIVO", "MASO_RYBY", "UZENINY", "MLECNE", "VEJCE", "MRAZENE", "TRVANLIVE",
              "SLADKOSTI", "NAPOJE", "ALKOHOL", "DROGERIE", "ZVIRATA", "OSTATNI"}
STORES = {"Lidl", "Kaufland", "Albert", "Billa", "Penny", "Tesco", "Globus", "Rohlík", "Košík", "Makro", "Norma", "Coop"}
FIELDS = {"id", "name", "brand", "category", "size_value", "size_unit", "eans", "stores", "related", "image_url", "sources"}
URL = re.compile(r"^https?://\S+$")
SLUG = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


def ean_ok(e):
    if not re.fullmatch(r"\d{8}|\d{13}", e):
        return False
    d = [int(c) for c in e]
    body, check = d[:-1], d[-1]
    s = sum(x * (3 if (len(body) - i) % 2 == 1 else 1) for i, x in enumerate(body))
    return (10 - s % 10) % 10 == check


def check(o):
    err = []
    for k in set(o) - FIELDS:
        err.append(f"neznámé pole {k}")
    if not isinstance(o.get("id"), str) or not SLUG.match(o["id"]):
        err.append("id musí být slug [a-z0-9-]")
    if not isinstance(o.get("name"), str) or not o["name"].strip():
        err.append("chybí name")
    if o.get("category") not in CATEGORIES:
        err.append(f"neplatná category {o.get('category')!r}")
    sv, su = o.get("size_value"), o.get("size_unit")
    if (sv is None) != (su is None):
        err.append("size_value a size_unit musí být obě, nebo žádná")
    if sv is not None and (not isinstance(sv, (int, float)) or sv <= 0):
        err.append("size_value musí být kladné číslo")
    if su is not None and su not in ("kg", "l", "ks"):
        err.append("size_unit musí být kg/l/ks")
    for e in o.get("eans") or []:
        if not isinstance(e, str) or not ean_ok(e):
            err.append(f"neplatný EAN {e!r}")
    stores = o.get("stores")
    if not isinstance(stores, list):
        err.append("stores musí být seznam (prázdný = obchod neznámý, jen u archivu)")
    else:
        seen = set()
        for s in stores:
            if not isinstance(s, dict) or not s.get("store"):
                err.append("store bez názvu"); continue
            if s["store"] not in STORES:
                print(f"varování: neznámý obchod {s['store']!r} u {o.get('id')}")
            if s["store"] in seen:
                err.append(f"obchod {s['store']} dvakrát")
            seen.add(s["store"])
            rn, src = s.get("receipt_name"), s.get("receipt_name_source")
            if rn is not None and src != "uctenka":
                err.append(f"receipt_name {rn!r} bez receipt_name_source='uctenka' – nevymýšlet")
            if s.get("url") is not None and not URL.match(s["url"]):
                err.append(f"neplatná url {s['url']!r}")
    if o.get("image_url") is not None and not URL.match(o["image_url"]):
        err.append("neplatná image_url")
    src = o.get("sources")
    if not isinstance(src, list) or not src or not all(isinstance(u, str) and URL.match(u) for u in src):
        err.append("sources musí obsahovat aspoň jednu URL")
    elif any("openfoodfacts" in u for u in src) or "openfoodfacts" in str(o.get("image_url")):
        err.append("Open Food Facts není povolený zdroj (aplikace ho čte sama) – jen weby obchodů")
    return err


def main(paths):
    ids, eans, bad, total = {}, {}, 0, 0
    rows = []
    for p in paths:
        with open(p, encoding="utf-8") as f:
            for n, line in enumerate(f, 1):
                if not line.strip():
                    continue
                total += 1
                where = f"{p}:{n}"
                try:
                    o = json.loads(line)
                except json.JSONDecodeError as e:
                    print(f"{where}: neplatný JSON: {e}"); bad += 1; continue
                rows.append((where, o))
                errs = check(o)
                if o.get("id") in ids:
                    errs.append(f"duplicitní id (také {ids[o['id']]})")
                ids.setdefault(o.get("id"), where)
                for e in o.get("eans") or []:
                    if e in eans:
                        errs.append(f"EAN {e} už je u {eans[e]} (sloučit do jednoho záznamu?)")
                    eans.setdefault(e, where)
                if errs:
                    bad += 1
                    for e in errs:
                        print(f"{where}: {e}")
    for where, o in rows:
        for r in o.get("related") or []:
            if r not in ids:
                print(f"{where}: related {r!r} neexistuje (varování)")
    print(f"\nZáznamů: {total}, s chybou: {bad}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
