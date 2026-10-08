# Katalog produktů

Soubory `app/src/main/assets/catalog/*.jsonl` se přibalí do aplikace. Při spuštění nové verze se
nahrají do databáze v telefonu, takže rozpoznání produktu je **offline a zdarma**.

Jeden řádek = jeden produkt v JSON (UTF-8). Řádky začínající `//` se ignorují.

```json
{"id":"kukuricne-kureci-rizky","store":"Lidl","name":"Kukuřičné kuřecí prsní řízky","brand":"Lidl",
 "quantity":"500 g","category":"MASO_RYBY","image":"https://…/foto.jpg","url":"https://www.lidl.cz/p/…",
 "eans":["4056489…"],"aliases":["Kukuř.kuře.prs.ř."],"source":"lidl.cz"}
```

| pole | povinné | význam |
|---|---|---|
| `id` | ano | unikátní v rámci souboru (např. slug názvu) |
| `name` | ano | skutečný celý název produktu |
| `store` | ne | obchod (`Lidl`, `Kaufland`, `Albert`, `Billa`, `Penny`, `Tesco`, `Globus`, `Rohlík`…); prázdné = obecný produkt |
| `brand` | ne | značka |
| `quantity` | ne | balení („500 g“, „1 l“, „6 ks“) |
| `category` | ne | jedna z: `OVOCE_ZELENINA, PECIVO, MASO_RYBY, UZENINY, MLECNE, VEJCE, MRAZENE, TRVANLIVE, SLADKOSTI, NAPOJE, ALKOHOL, DROGERIE, ZVIRATA, OSTATNI` |
| `image` | ne | URL fotky produktu |
| `url` | ne | stránka produktu |
| `eans` | ne | čárové kódy (EAN-13/EAN-8) |
| `aliases` | ne | názvy přesně tak, jak jsou vytištěné na účtence daného obchodu (`"Kukuř.kuře.prs.ř."`) |
| `source` | ne | odkud data jsou |

Párování názvu z účtenky s `aliases` toleruje diakritiku, velikost písmen, záměny l/1/I a O/0
a 1–2 překlepy z OCR. Jeden soubor na obchod / zdroj (`lidl.jsonl`, `kaufland.jsonl`, `off_cz.jsonl`…).
