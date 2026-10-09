# Prompt pro sběrače kupi.cz (Haiku)

Sbíráš potraviny, které se prodávají v kamenných obchodech, z akčních letáků na kupi.cz.
Repozitář: /home/user/obchodsken. Nejdřív přečti data/foods/FORMAT.md a data/foods/prompts/haiku-sberac.md
(pravidla 1–9 a sekce „Režim hromadného sběru“ platí i tady – kromě toho, že zdroj je kupi.cz, ne web obchodu).

## Tvoje obchody
{{OBCHODY}}   → výstup `data/foods/raw/{{SOUBOR}}`, skript `data/foods/harvest/{{SOUBOR bez .jsonl}}.py`

## Jak kupi.cz funguje (ověřeno)
- Seznam aktuálních akcí obchodu v kategorii: `https://www.kupi.cz/slevy/<kategorie>/<obchod>` a další stránky
  `?page=2`, `?page=3`… (dokud přibývají produkty). Seznam je v HTML jako JSON-LD `ItemList` (url + name).
  Slug obchodu zjistíš z `https://www.kupi.cz/slevy/<obchod>` (např. `lidl`; ostatní ověř, např. `penny-market`).
- Kategorie potravin: `alkohol, konzervy, lahudky, maso-drubez-a-ryby, mlecne-vyrobky-a-vejce,
  mrazene-a-instantni-potraviny, nealko-napoje, ovoce-a-zelenina, pecivo, sladkosti-a-slane-snacky,
  vareni-a-peceni, zdrava-vyziva` (+ `pro-deti` jen dětské potraviny). Nepotraviny vynech.
- Detail produktu `https://www.kupi.cz/sleva/<slug>`: JSON-LD `Product` (name, brand, image,
  offers[].offeredBy = obchody, kde je teď v akci). V textu stránky je podkategorie
  („Tento výrobek najdete v kategorii X a podkategorii Y“) a velikost balení u nabídky (např. „/ 1 kg“, „500 g“).

## Záznam
- `id` = `kupi-<slug>` (stejný produkt z jiného souboru bude mít stejné id – to je v pořádku, sloučí se).
- `stores` = VŠECHNY obchody z `offers[].offeredBy` (ne jen tvoje), každý s `url: null`, `receipt_name: null`.
  Názvy obchodů sjednoť na: Lidl, Kaufland, Albert, Billa, Penny, Tesco, Globus, Norma, Coop, Makro (jiné
  řetězce potravin – CBA, Hruška, Flop, JIP, Tamda… – uveď jak jsou, validátor je jen označí varováním).
- `sources` = [URL produktu na kupi.cz]. `image_url` = obrázek z JSON-LD (nezkoušej ho zvětšovat).
- Kategorie podle podkategorie kupi (mapovací tabulka ve skriptu). Velikost jen když je jednoznačná.
- Produkty bez obchodu v `offers` (není v akci) vynech.

## Šetrnost
Paralelně stahují kupi.cz další 3 agenti → MAX 1 požadavek za sekundu, User-Agent běžného prohlížeče,
při 429/5xx exponenciální čekání. Stránky produktů, které už máš (stejný slug), znovu nestahuj.
Skript musí jít spustit znovu (např. každý týden) a nové produkty přidat ke starým (sloučit podle id,
obchody sjednotit) – tak databáze poroste s každým letákem.

Na konci `python3 data/foods/validate.py data/foods/raw/{{SOUBOR}}` bez chyb (varování o obchodu nevadí).
Nedělej git commit ani push. Odpověz krátce: počet záznamů, rozdělení podle obchodů, počet požadavků, co nešlo.
