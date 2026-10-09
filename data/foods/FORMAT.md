# Databáze potravin – formát dat

Jeden soubor `.jsonl` = jeden řádek JSON na potravinu (UTF-8). Struktura odpovídá 1:1 tabulkám
v `supabase/schema.sql`, takže import do Supabase je jen přepis řádků.

```json
{"id":"lidl-pilos-polotucne-mleko-1-5-1l","name":"Pilos Polotučné mléko 1,5 %","brand":"Pilos",
 "category":"MLECNE","size_value":1,"size_unit":"l","eans":["4056489123456"],
 "stores":[{"store":"Lidl","receipt_name":null,"receipt_name_source":null,"url":"https://www.lidl.cz/p/..."}],
 "related":["lidl-pilos-plnotucne-mleko-3-5-1l"],"image_url":"https://...jpg",
 "sources":["https://www.lidl.cz/p/..."]}
```

| pole | povinné | význam |
|---|---|---|
| `id` | ano | unikátní slug: malá písmena bez diakritiky, číslice, pomlčky (`[a-z0-9-]+`) |
| `name` | ano | celý název potraviny tak, jak ho uvádí obchod/výrobce |
| `brand` | ne | značka |
| `category` | ano | `OVOCE_ZELENINA, PECIVO, MASO_RYBY, UZENINY, MLECNE, VEJCE, MRAZENE, TRVANLIVE, SLADKOSTI, NAPOJE, ALKOHOL, DROGERIE, ZVIRATA, OSTATNI` |
| `size_value` + `size_unit` | ne | velikost balení; jednotka `kg`, `l` nebo `ks` (500 g = `0.5` + `kg`). Buď obě, nebo ani jedno |
| `eans` | ne | čárové kódy EAN-13/EAN-8 se správnou kontrolní číslicí |
| `stores` | ano, ≥1 | obchody; každý se svým názvem na účtence a odkazem na produkt |
| `stores[].store` | ano | `Lidl, Kaufland, Albert, Billa, Penny, Tesco, Globus, Rohlík, Košík, Makro, Norma, Coop` – kamenné i internetové obchody |
| `stores[].receipt_name` | ano* | název přesně jak je vytištěný na účtence **tohoto** obchodu. *Smí být `null`, pokud ho nemáme doložený – nikdy se nevymýšlí |
| `stores[].receipt_name_source` | – | `"uctenka"` = viděno na skutečné účtence; jinak `null` |
| `stores[].url` | ne | stránka produktu v e-shopu / letáku daného obchodu |
| `related` | ne | `id` příbuzných potravin (jiná velikost, příchuť, tučnost…) |
| `image_url` | ne | přímý odkaz na fotku produktu |
| `sources` | ano, ≥1 | odkud data jsou (URL webu obchodu), aby šla ověřit. **Ne Open Food Facts** – ten aplikace čte sama, data by byla dvakrát |

`receipt_name` je v aplikaci povinné, ale z webu se skoro nedá zjistit – záznamy s `null` se doplní
z naskenovaných účtenek. Stejný produkt ve více obchodech = **jeden** záznam s více položkami ve `stores` (žádné duplicity).
Kontrola: `python3 data/foods/validate.py data/foods/raw/*.jsonl`.
