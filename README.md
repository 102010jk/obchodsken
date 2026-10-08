# Obchodsken

Android aplikace na účtenky a čárové kódy.

- **Vyfoť účtenku** (nebo naimportuj screenshoty elektronických účtenek z Lidl Plus – klidně stovky najednou,
  případně je pošli do aplikace přes *Sdílet*) → aplikace přečte text (ML Kit, offline v telefonu),
  rozpozná položky, ceny, slevy, množství/váhu, datum a pobočku a zkratky přeloží na normální názvy
  (`Odpad.pytle s uchy` → *Odpadkové pytle se zatahovacími uchy*, `Kukuř.kuře.prs.ř.` → *Kukuřičné kuřecí prsní řízky*)
  včetně kategorie.
- **Naskenuj čárový kód** → název, značka, kategorie, složení a Nutri-Score z Open Food Facts.
  Kód jde propojit s položkou z účtenek – pak uvidíš, kolikrát a za kolik jsi produkt kupoval.
- **Položky** – všechny koupené produkty, historie cen, min/max/průměr, slevy.
- **Přehled** – útraty po měsících a kategoriích, export všech položek do CSV.
- Opravíš-li název položky, aplikace si ho zapamatuje a použije u všech dalších účtenek.
- Duplicitní účtenky (např. papírová + elektronická verze téhož nákupu) se poznají a přeskočí.

## Instalace

Stáhni `obchodsken.apk` (z Releases nebo z artefaktu GitHub Actions), otevři v telefonu a povol instalaci
z neznámých zdrojů. Nové verze jdou instalovat přes starou (stejný podpisový klíč v `keystore/`).

## Sestavení

```
./gradlew :app:testDebugUnitTest   # testy parseru na reálných účtenkách
./gradlew :app:assembleRelease     # APK v app/build/outputs/apk/release/
```

Parser účtenek je v `app/src/main/java/cz/obchodsken/parser/` (čistý Kotlin, testovatelný bez Androidu),
slovník zkratek a kategorií v `ProductNames.kt`.
