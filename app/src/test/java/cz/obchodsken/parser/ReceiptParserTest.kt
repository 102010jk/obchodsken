package cz.obchodsken.parser

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.time.LocalDateTime

class ReceiptParserTest {

    /** Fixtures = slova z OCR (tesseract) se souřadnicemi, z reálných elektronických účtenek Lidl Plus. */
    private fun loadRows(name: String): List<String> {
        val text = javaClass.classLoader!!.getResource(name)!!.readText()
        val lines = text.lines().filter { it.isNotBlank() }.map {
            val p = it.split('\t')
            OcrLine(p[4], p[0].toFloat(), p[1].toFloat(), p[2].toFloat(), p[3].toFloat())
        }
        return RowBuilder.buildRows(lines)
    }

    private fun check(
        file: String, total: Long, itemCount: Int, date: LocalDateTime, branchPart: String,
    ): ParsedReceipt {
        val r = ReceiptParser.parse(loadRows(file))
        val dump = r.items.joinToString("\n") { "  ${it.rawName} | ${it.price} -${it.discount} | ${it.quantity} ${it.unit}" }
        assertEquals("total $file\n$dump", total, r.total)
        assertEquals("items $file\n$dump", itemCount, r.items.size)
        assertEquals("sum $file\n$dump", total, r.itemsSum)
        assertEquals(date, r.purchasedAt)
        assertEquals("Lidl", r.store)
        assertTrue("branch ${r.branch}", r.branch!!.contains(branchPart))
        assertTrue("warnings ${r.warnings}", r.warnings.isEmpty())
        assertNotNull(r.uniqueKey)
        return r
    }

    @Test fun electronic_1006() {
        val r = check("e_1006.tsv", 22761, 9, LocalDateTime.of(2026, 6, 10, 13, 44, 25), "Gerská")
        assertEquals("Omáčka sladk.-kys", r.items[0].rawName)
        assertEquals(349L, r.items[0].discount)
        assertEquals("Karta", r.payment)
    }

    @Test fun electronic_2207() {
        val r = check("e_2207.tsv", 78987, 14, LocalDateTime.of(2026, 7, 22, 13, 27, 20), "Studentská")
        val tunak = r.items[0]
        assertEquals(2.0, tunak.quantity, 0.0)
        assertEquals(6490L, tunak.unitPrice)
        assertEquals(3246L, tunak.discount)
        assertEquals("538838", r.items[1].articleCode)
        assertEquals("Rukavice", r.items[1].rawName)
        assertEquals("Měkká utěrka", r.items[2].rawName)
        val rajcata = r.items.first { it.rawName.startsWith("Rajčata") }
        assertEquals("kg", rajcata.unit)
        assertEquals(0.678, rajcata.quantity, 1e-9)
        assertEquals(8246L, r.totalDiscount)
    }

    @Test fun electronic_1408() {
        val r = check("e_1408.tsv", 83634, 12, LocalDateTime.of(2026, 8, 14, 12, 8, 30), "Plaská")
        assertEquals(2, r.items.count { it.rawName == "Meloun vodní" })
    }

    @Test fun electronic_3008() {
        check("e_3008.tsv", 60660, 12, LocalDateTime.of(2026, 8, 30, 19, 30, 33), "Plaská")
    }

    @Test fun electronic_2109() {
        check("e_2109.tsv", 65475, 12, LocalDateTime.of(2026, 9, 21, 9, 46, 19), "Gerská")
    }

    @Test fun electronic_0710a() {
        val r = check("e_0710a.tsv", 59723, 8, LocalDateTime.of(2026, 10, 7, 13, 39, 10), "Gerská")
        assertEquals(756L, r.items[0].discount) // SLEVA 20%
        assertEquals(734L, r.items[1].discount) // Lidl Plus sleva na rajčata
    }

    @Test fun electronic_0710b_and_paper_are_same_receipt() {
        val e = check("e_0710b.tsv", 11609, 2, LocalDateTime.of(2026, 10, 7, 18, 39, 41), "Plaská")
        // Papírová verze téže účtenky (jak ji typicky přečte OCR z fotky – s chybami v diakritice)
        val paper = ReceiptParser.parse(
            listOf(
                "Lidl provozovna:", "Plzeň, Plaská", "Kč",
                "Zahradní směs 89,90 B", "Lidl Plus sleva -22,48", "Cena po slevé 67,42",
                "Ovocná směs maliny 64, 90 B", "Lidl Plus sleva - 16,23", "Cena po slevě 48,67",
                "----------------------------", "K PLATBĚ 116,09", "Karta 116,09",
                "Celková zaplacená částka 116,09", "07/10/26 18:40 Účtenka číslo 02020",
                "Celková sleva 38,71", "B 12% DPH z 116,09 12,44",
                "0546 053368/086/86 07.10.26 18:39:41", "Záruční a další údaje - zadní strana",
            )
        )
        assertEquals(e.uniqueKey, paper.uniqueKey)
        assertEquals(2, paper.items.size)
        assertEquals(11609L, paper.itemsSum)
        assertEquals("02020", paper.receiptNumber)
    }

    @Test fun paper_cash_with_rounding() {
        val r = ReceiptParser.parse(
            listOf(
                "Lidl provozovna:", "Plzeň, Plaská", "Kč",
                "Coca Cola Zero 24,90 C", "Bagetka s párkem 19,90 B", "Kapsa třešňová 14,90 8",
                "------------------", "SUMA 3 Poz. 59,70", "zaokrouhleno 0,30", "K PLATBĚ 60,00",
                "Hotovost Kč 60,00", "Celková zaplacená částka 60,00",
                "B 12% DPH z 34,80 3,73", "C 21% DPH z 24,90 4,32",
                "0546 174745/015/01 05.10.26 12:44",
            )
        )
        assertEquals(3, r.items.size)
        assertEquals("B", r.items[2].vat)
        assertEquals(6000L, r.total)
        assertEquals(5970L, r.subtotal)
        assertEquals("Hotovost", r.payment)
        assertTrue(r.warnings.toString(), r.warnings.isEmpty())
        assertEquals(LocalDateTime.of(2026, 10, 5, 12, 44), r.purchasedAt)
    }

    @Test fun missed_discount_line_is_recovered_from_price_after_discount() {
        val r = ReceiptParser.parse(
            listOf("Mozzarella 12,90 B", "Cena po slevě 9,90", "Okurka 9,90 B", "K PLATBĚ 19,80")
        )
        assertEquals(300L, r.items[0].discount)
        assertEquals(1980L, r.itemsSum)
    }

    @Test fun names_are_expanded() {
        assertEquals("Odpadkové pytle se zatahovacími uchy", ProductNames.describe("Odpad.pytle s uchy").name)
        assertEquals(Category.MASO_RYBY, ProductNames.describe("Kukuř.kuře.prs.ř.").category)
        // neznámé zkratky -> rozepsání po slovech
        assertEquals("Hořká čokoláda 70%", ProductNames.expand("Hoř.čokoláda 70%"))
        assertEquals(Category.SLADKOSTI, ProductNames.describe("Hoř.čokoláda 70%").category)
        assertEquals(Category.MLECNE, ProductNames.describe("Jogurt bílý 150g").category)
        assertEquals(Category.OVOCE_ZELENINA, ProductNames.describe("Zelenina mix").category)
        assertEquals(Category.DROGERIE, ProductNames.describe("Toal.papír 8ks").category)
        assertEquals("Toaletní papír 8 ks", ProductNames.expand("Toal.papír 8ks"))
    }

    @Test fun money() {
        assertEquals(8990L, Money.parse("89,90"))
        assertEquals(-349L, Money.parse("-3,49"))
        assertEquals("1 234,50 Kč", Money.format(123450))
    }
}
