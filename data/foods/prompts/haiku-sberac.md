# Prompt pro sběrače (Haiku) – společná část

Sbíráš skutečné potraviny z webů českých obchodů do databáze aplikace Obchodsken.
Repozitář: /home/user/obchodsken. Formát dat: data/foods/FORMAT.md – PŘEČTI HO CELÝ jako první.

## Tvůj úkol
{{ZADANI}}

Výstup: zapiš do souboru `data/foods/raw/{{SOUBOR}}` (jeden JSON na řádek, UTF-8). Do jiných souborů nesahej,
nedělej git commit ani push. Cíl: 40–60 různých potravin; kvalita je důležitější než počet.

## Pravidla (porušení = záznam se smaže)
1. **Jen skutečná data z webu obchodu.** Každý údaj (název, značka, velikost, EAN, fotka, odkaz) musí pocházet
   ze stránky / API obchodu, kterou jsi v tomto úkolu opravdu stáhl. Nic nedoplňuj z hlavy, nic neodhaduj.
   Když údaj nenajdeš, pole vynech (nebo `null`).
2. **Open Food Facts nepoužívej** (ani jako zdroj, ani pro fotky) – aplikace ho čte sama.
3. `sources` = URL, ze kterých jsi data skutečně vzal. `stores[].url` = stránka produktu v obchodě.
4. `receipt_name` nech `null` a `receipt_name_source` `null` – název na účtence se z webu zjistit nedá
   (výjimka jen pokud to tvé zadání výslovně říká).
5. Velikost převeď: 500 g → `0.5` + `kg`; 330 ml → `0.33` + `l`; 10 ks → `10` + `ks`. „cca 300 g“ (vážené zboží) → vynech.
6. Kategorie podle FORMAT.md. `id` = `<obchod>-<slug-nazvu-a-velikosti>`, např. `rohlik-pilos-mleko-polotucne-1l`.
7. Žádné duplicity: stejný produkt jen jednou. Různé velikosti/příchutě = různé záznamy, propoj je přes `related`
   (jen na `id` ze svého souboru).
8. Jen potraviny a nápoje (žádná drogerie, pokud to zadání neříká). Různorodě – běžné věci, které lidé kupují.
9. Buď šetrný k webům: max ~80 požadavků celkem, žádné paralelní bombardování. Když web vrací 403/blokaci,
   nesnaž se ji obcházet – zkus jiný postup ze zadání, případně skonči s tím, co máš.

## Postup
- Stahovat můžeš přes `curl -sL -A "Mozilla/5.0" URL` (Bash) nebo WebFetch; JSON zpracuj v `python3`.
- Záznamy piš skriptem (python `json.dumps(..., ensure_ascii=False)`), ne ručně.
- Na konci spusť `python3 data/foods/validate.py data/foods/raw/{{SOUBOR}}` a oprav všechny chyby.
- Odpověz krátce: kolik záznamů, odkud, co nešlo a proč (max 10 řádků).
