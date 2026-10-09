# Rozdělení práce – 16 sběračů (Haiku) + 2 kontroloři (Sonnet)

Každý sběrač dostane `haiku-sberac.md` s dosazeným ZADANI a SOUBOR:

| # | soubor (`data/foods/raw/`) | zadání |
|---|---|---|
| 01 | `01-rohlik-pecivo-ovoce.jsonl` | Rohlík.cz – Pekárna a cukrárna (300101000), Ovoce a zelenina (300102000) |
| 02 | `02-rohlik-maso-uzeniny.jsonl` | Rohlík.cz – Maso a ryby (300103000), Uzeniny a lahůdky (300104000) |
| 03 | `03-rohlik-mlecne.jsonl` | Rohlík.cz – Mléčné a chlazené (300105000) |
| 04 | `04-rohlik-trvanlive.jsonl` | Rohlík.cz – Trvanlivé (300106000) |
| 05 | `05-rohlik-mrazene-napoje.jsonl` | Rohlík.cz – Mražené (300107000), Nápoje (300108000) |
| 06 | `06-kosik-chlazene.jsonl` | Košík.cz – mléčné, vejce, maso, uzeniny |
| 07 | `07-kosik-trvanlive-napoje.jsonl` | Košík.cz – trvanlivé, sladkosti, nápoje, pečivo |
| 08 | `08-lidl-trvanlive.jsonl` | Lidl.cz – trvanlivé, sladkosti, nápoje |
| 09 | `09-lidl-chlazene.jsonl` | Lidl.cz – chlazené, maso, mléčné, pečivo, mražené |
| 10 | `10-billa-chlazene.jsonl` | shop.billa.cz – mléčné, maso, uzeniny, pečivo |
| 11 | `11-billa-trvanlive.jsonl` | shop.billa.cz – trvanlivé, sladkosti, nápoje, alkohol |
| 12 | `12-albert.jsonl` | Albert.cz – všechny kategorie |
| 13 | `13-penny.jsonl` | Penny.cz – všechny kategorie |
| 14 | `14-globus.jsonl` | Globus.cz – všechny kategorie |
| 15 | `15-kaufland-tesco.jsonl` | Kaufland a Tesco (jejich weby blokují) – oficiální letáky / agregátory skutečných letáků |
| 16 | `16-lidl-uctenky.jsonl` | skutečné názvy z účtenek v repozitáři → dohledat produkt na lidl.cz (`receipt_name_source: "uctenka"`) |

Kontroloři (`sonnet-kontrolor.md`): A = soubory 01–08 (`review-A.md`), B = soubory 09–16 (`review-B.md`).
Po kontrole jeden z nich sloučí `reviewed/*.jsonl` do `data/foods/foods.jsonl` (stejný produkt ve více
obchodech = jeden záznam s více `stores`).

Rohlík API (ověřeno): ID v kategorii `https://www.rohlik.cz/api/v1/categories/normal/<KAT>/products?limit=100`
(`productIds`), detaily `https://www.rohlik.cz/api/v1/products?products=<ID>&products=<ID>` (name, brand,
textualAmount, slug, images, weightedItem), stránka produktu `https://www.rohlik.cz/<id>-<slug>`.

## Druhé kolo – hromadný sběr a kupi.cz
Sběrači 01–05 (Rohlík), 06–07 (Košík), 08–11 (Lidl, Billa), 12 (Albert), 14 (Globus): režim hromadného sběru
(celý sortiment, skripty v `data/foods/harvest/`). Penny (13) víc než aktuální nabídku na webu nemá.

Kupi.cz (`haiku-kupi.md`) – aktuální akce kamenných obchodů, skript jde pouštět každý týden:
| # | soubor | obchody |
|---|---|---|
| 17 | `17-kupi-lidl-penny.jsonl` | Lidl, Penny |
| 18 | `18-kupi-kaufland-tesco.jsonl` | Kaufland, Tesco |
| 19 | `19-kupi-albert-billa.jsonl` | Albert, Billa |
| 20 | `20-kupi-ostatni.jsonl` | Globus, Norma, Coop, Makro, CBA, Hruška, Flop, JIP |
