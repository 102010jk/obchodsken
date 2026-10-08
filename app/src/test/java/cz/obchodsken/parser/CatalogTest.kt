package cz.obchodsken.parser

import cz.obchodsken.data.Catalog
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import java.io.File

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class CatalogTest {
    private val files = File("src/main/assets/catalog").listFiles { f -> f.name.endsWith(".jsonl") }!!.toList()

    private fun entries() = files.flatMap { f ->
        f.readLines().filter { it.isNotBlank() && !it.startsWith("//") }.map { line ->
            Catalog.parse(JSONObject(line), f.nameWithoutExtension) ?: error("Neplatný řádek v ${f.name}: $line")
        }
    }

    @Test fun catalogFilesAreValid() {
        val all = entries()
        assertTrue(all.isNotEmpty())
        val ids = all.map { it.first.id }
        assertEquals("Duplicitní id: " + ids.groupBy { it }.filter { it.value.size > 1 }.keys, ids.size, ids.toSet().size)
        all.forEach { (p, _, _) -> assertTrue("Neznámá kategorie u ${p.name}", Category.entries.any { it.name == p.category }) }
    }

    @Test fun receiptNamesAreFoundInCatalog() {
        val matcher = NameMatcher(entries().flatMap { (p, _, a) -> a.map { it.alias to p.name } })
        assertEquals("Kukuřičné kuřecí prsní řízky", matcher.find("Kukuř.kuře.prs.ř"))   // parser odstraní koncovou tečku
        assertEquals("Odpadkové pytle 35 l", matcher.find("Odpad.pytle 351"))            // OCR: l -> 1
        assertEquals("Žervé (čerstvý sýr) s kápií", matcher.find("Žervé s kápii"))
    }
}
