package cz.obchodsken.parser

import android.content.Context
import androidx.test.core.app.ApplicationProvider
import cz.obchodsken.App
import cz.obchodsken.data.AppDatabase
import cz.obchodsken.data.ImportOutcome
import cz.obchodsken.data.Repository
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

/** Celá cesta po OCR: text -> položky -> katalog -> databáze -> duplicita. */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class ImportFlowTest {
    private fun rows(name: String): List<String> {
        val text = javaClass.classLoader!!.getResource(name)!!.readText()
        return RowBuilder.buildRows(text.lines().filter { it.isNotBlank() }.map {
            val p = it.split('\t')
            OcrLine(p[4], p[0].toFloat(), p[1].toFloat(), p[2].toFloat(), p[3].toFloat())
        })
    }

    @Test fun importMatchesCatalogAndDetectsDuplicates() = runBlocking {
        // App při startu nahraje katalog do své DB na pozadí a uloží si značku – počkat na to a značku smazat,
        // jinak by testovací DB katalog přeskočila (podle toho, kdo doběhne dřív).
        val app = ApplicationProvider.getApplicationContext<App>()
        app.repo.catalog.ensureLoaded()
        app.getSharedPreferences("catalog", Context.MODE_PRIVATE).edit().clear().commit()
        val db = AppDatabase.inMemory(ApplicationProvider.getApplicationContext())
        val repo = Repository(ApplicationProvider.getApplicationContext(), db, CoroutineScope(Dispatchers.Default))

        val first = repo.importRows(rows("e_2109.tsv"))
        assertTrue(first.toString(), first is ImportOutcome.Saved)
        val id = (first as ImportOutcome.Saved).id
        val items = db.dao().items(id)
        assertEquals(12, items.size)
        val kure = items.first { it.rawName.startsWith("Kukuř") }
        assertEquals("Kukuřičné kuřecí prsní řízky", kure.name)
        assertNotNull("položka má být spárovaná s katalogem", kure.catalogId)
        assertEquals(Category.MASO_RYBY.name, kure.category)

        // Stejná účtenka podruhé = duplicita
        assertTrue(repo.importRows(rows("e_2109.tsv")) is ImportOutcome.Duplicate)

        // Ruční oprava má přednost před katalogem a platí pro další účtenky
        repo.updateItem(kure.copy(name = "Řízky v kukuřičné strouhance"), applyToAll = true)
        assertEquals("Řízky v kukuřičné strouhance", db.dao().items(id).first { it.id == kure.id }.name)

        // Nesmysl není účtenka
        assertTrue(repo.importRows(listOf("Ahoj", "jak se máš")) is ImportOutcome.NotReceipt)
        db.close()
    }
}
