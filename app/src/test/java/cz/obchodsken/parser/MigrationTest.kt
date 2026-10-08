package cz.obchodsken.parser

import androidx.room.testing.MigrationTestHelper
import androidx.test.platform.app.InstrumentationRegistry
import cz.obchodsken.data.AppDatabase
import org.junit.Assert.assertEquals
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

/** Aktualizace z verze 1 (první APK) nesmí smazat data ani spadnout. */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class MigrationTest {
    @get:Rule
    val helper = MigrationTestHelper(InstrumentationRegistry.getInstrumentation(), AppDatabase::class.java)

    @Test fun migrate1To2KeepsData() {
        helper.createDatabase("test.db", 1).apply {
            execSQL("INSERT INTO name_mappings (rawKey, name, category) VALUES ('odpad.pytle', 'Odpadkové pytle', 'DROGERIE')")
            execSQL(
                "INSERT INTO products (barcode, name, brand, quantity, category, imageUrl, nutriscore, ingredients, source, linkedRawKey, updatedAt) " +
                    "VALUES ('123', 'Test', NULL, NULL, 'OSTATNI', NULL, NULL, NULL, 'Ručně', NULL, 0)"
            )
            close()
        }
        val db = helper.runMigrationsAndValidate("test.db", 2, true)
        db.query("SELECT name FROM name_mappings").use { it.moveToFirst(); assertEquals("Odpadkové pytle", it.getString(0)) }
        db.query("SELECT COUNT(*) FROM products").use { it.moveToFirst(); assertEquals(1, it.getInt(0)) }
        db.query("SELECT COUNT(*) FROM catalog_products").use { it.moveToFirst(); assertEquals(0, it.getInt(0)) }
    }
}
