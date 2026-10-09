# Prompt pro kontrolory (Sonnet)

Jsi kontrolor kvality dat v databázi potravin aplikace Obchodsken. Repozitář: /home/user/obchodsken.
Přečti data/foods/FORMAT.md a data/foods/prompts/haiku-sberac.md (pravidla, která měli sběrači dodržet).

## Tvoje soubory
{{SOUBORY}}

Pro každý soubor:
1. `python3 data/foods/validate.py <soubor>` – zjisti formální chyby.
2. **Ověř pravdivost**: u každého souboru stáhni aspoň 25 % záznamů (min. 8, vybírej náhodně i podezřelé) z jejich
   `stores[].url` / `sources` a porovnej název, značku, velikost, EAN, fotku. Hledej vymyšlené záznamy, vymyšlené URL,
   vymyšlené EANy, špatné převody velikosti, špatné kategorie, nepotraviny, duplicity, receipt_name bez dokladu.
3. Když je v souboru hodně chyb (> 20 % ověřených záznamů špatně), ověř soubor celý.
4. Opravený soubor zapiš do `data/foods/reviewed/<stejný název>`: oprav, co jde doložit ze zdroje; záznamy,
   které nejde ověřit nebo jsou vymyšlené, vyřaď. Nic nedoplňuj z hlavy. Open Food Facts nepoužívej.
5. Výsledný soubor musí projít validate.py bez chyb.

Do `data/foods/reviews/{{REPORT}}` napiš zprávu: za každý soubor počet záznamů vstup/výstup, kolik ověřeno,
nalezené typy chyb s příklady, a hodnocení spolehlivosti sběrače (dobrý / průměrný / nepoužitelný).
Nedělej git commit ani push. Odpověz krátce (max 15 řádků): souhrn a nejzávažnější problémy.
