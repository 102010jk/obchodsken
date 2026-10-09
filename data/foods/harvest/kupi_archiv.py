#!/usr/bin/env python3
"""Archiv kupi.cz: všechny produktové stránky ze sitemapy -> data/foods/raw/kupi-archiv.jsonl.

Bere jen potraviny (podle kategorie na stránce). Produkty, které zrovna nejsou v akci, mají prázdné
`stores` (obchod zatím neznámý). Běh jde přerušit a znovu spustit – hotové a vyřazené stránky přeskočí.
Volby: --commit-every N  (průběžně git commit + push výstupu, výchozí 0 = ne)
       --shard I/N       (paralelní běh: tahle kopie zpracuje jen každý N-tý produkt od I-tého,
                          výstup kupi-archiv-I.jsonl; spusť N kopií s I = 0..N-1)
"""
import importlib.util
import json
import re
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("kupi", HERE / "kupi.py")
kupi = importlib.util.module_from_spec(spec)
spec.loader.exec_module(kupi)

ROOT = kupi.ROOT
OUT = ROOT / "data/foods/raw/kupi-archiv.jsonl"
SKIPPED = HERE / "cache" / "kupi-archiv-vyrazeno.txt"   # slugy, které nejsou potraviny / nejdou načíst
CURRENT = ROOT / "data/foods/raw/kupi.jsonl"            # aktuální akce (se obchody) – ty už máme
kupi.MIN_INTERVAL = 0.7
kupi.OUT = OUT

# Zjevné nepotraviny podle slova v adrese – ušetří požadavky (zbytek vyřadí kategorie na stránce).
NONFOOD_TOKENS = set("""
boty bota bunda tricko triko kalhoty ponozky podprsenka kosile mikina sukne saty pyzamo cepice rukavice
povleceni polstar prosteradlo deka lampa svitidlo zarovka vrtacka sroubovak pila brusk kladivo pneumatiky
pneumatika autobaterie nabytek sedacka stul zidle kreslo postel matrace skrin regal komoda panev hrnec
pekac sklenice sklenic talir talire hrnek pribory hracka hracky lego panenka stavebnice kocarek autosedacka
televizor notebook tablet telefon mobil sluchatka reproduktor pracka lednice mikrovlnna vysavac zehlicka
fen kulma holici sampon kondicioner deodorant antiperspirant sprchovy parfem toaletni pleny plenky
ubrousky avivaz praci prasek tablety kosmetika krem pletovy rtenka lak zubni kartacek krmivo granule
psy psi kocky kocka steliva stelivo hnojivo substrat semena kvetinac sekacka gril kolo kola stan spacak
""".split())
FOOD_PARENTS = set(kupi.PARENT_DEFAULT)
LOC_RE = re.compile(r"<loc>\s*(\S+?)\s*</loc>")


def sitemap_slugs():
    idx, _ = kupi.fetch(f"{kupi.BASE}/sitemaps/sitemap.xml")
    slugs = []
    for sm in LOC_RE.findall(idx or ""):
        xml, _ = kupi.fetch(sm)
        for u in LOC_RE.findall(xml or ""):
            m = kupi.PRODUCT_URL.match(u)
            if m:
                slugs.append(m.group(1))
    return list(dict.fromkeys(slugs))


def git_commit(n):
    try:
        subprocess.run(["git", "add", *map(str, OUT.parent.glob("kupi-archiv*.jsonl"))], cwd=ROOT, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-q", "-m", f"WIP: kupi.cz archive harvest ({n} items)\n\n"
                        "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"],
                       cwd=ROOT, capture_output=True)
        subprocess.run(["git", "push", "-q"], cwd=ROOT, capture_output=True, timeout=120)
    except Exception as e:   # průběžný commit nesmí shodit sběr
        print(f"commit selhal: {e}", file=sys.stderr)


def main(argv):
    global OUT, SKIPPED
    commit_every = int(argv[argv.index("--commit-every") + 1]) if "--commit-every" in argv else 0
    shard, nshards = 0, 1
    if "--shard" in argv:
        shard, nshards = map(int, argv[argv.index("--shard") + 1].split("/"))
        OUT = OUT.with_name(f"kupi-archiv-{shard}.jsonl")
        SKIPPED = SKIPPED.with_name(f"kupi-archiv-vyrazeno-{shard}.txt")
        kupi.OUT = OUT
    records = kupi.load_existing()
    have = set(records)
    for f in OUT.parent.glob("kupi-archiv*.jsonl"):        # co už mají ostatní kopie / dřívější běh
        have |= {json.loads(l)["id"] for l in f.open(encoding="utf-8") if l.strip()}
    for f in SKIPPED.parent.glob("kupi-archiv-vyrazeno*.txt"):
        have |= {f"kupi-{x}" for x in f.read_text(encoding="utf-8").split()}
    if CURRENT.exists():
        have |= {json.loads(l)["id"] for l in CURRENT.open(encoding="utf-8") if l.strip()}
    SKIPPED.parent.mkdir(parents=True, exist_ok=True)
    skipped = set(SKIPPED.read_text(encoding="utf-8").split()) if SKIPPED.exists() else set()

    slugs = sitemap_slugs()[shard::nshards]
    todo = [s for s in slugs if f"kupi-{s}" not in have and s not in skipped
            and kupi.SLUG_RE.fullmatch(s) and not (set(s.split("-")) & NONFOOD_TOKENS)]
    print(f"Sitemapa: {len(slugs)} produktů, hotovo {len(records)}, vyřazeno dříve {len(skipped)}, "
          f"k načtení {len(todo)}", file=sys.stderr, flush=True)

    added, since_commit, t0 = 0, 0, time.time()
    with SKIPPED.open("a", encoding="utf-8") as skip_f:
        try:
            for i, slug in enumerate(todo, 1):
                html, _ = kupi.fetch(f"{kupi.BASE}/sleva/{slug}")
                rec = None
                if html:
                    m = kupi.SUBCAT_RE.search(html)
                    if m and m.group(1) in FOOD_PARENTS:
                        rec, _ = kupi.build_record(slug, html, m.group(1), allow_no_store=True)
                if rec is None:
                    skip_f.write(slug + "\n")
                    continue
                records[rec["id"]] = rec
                added += 1
                since_commit += 1
                if added % 200 == 0:
                    kupi.save(records)
                    skip_f.flush()
                    rate = i / (time.time() - t0)
                    print(f"{i}/{len(todo)} stránek, potravin {len(records)}, "
                          f"zbývá ~{(len(todo) - i) / rate / 3600:.1f} h", file=sys.stderr, flush=True)
                if commit_every and since_commit >= commit_every:
                    kupi.save(records)
                    git_commit(len(records))
                    since_commit = 0
        except kupi.Blocked as e:
            print(f"BLOKACE (403), končím a ukládám: {e}", file=sys.stderr)
    kupi.save(records)
    if commit_every:
        git_commit(len(records))
    print(f"Hotovo: potravin {len(records)}, nových {added}, požadavků {kupi.stats['requests']}",
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
