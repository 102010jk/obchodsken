package cz.obchodsken.parser

import androidx.test.core.app.ApplicationProvider
import cz.obchodsken.data.AppDatabase
import cz.obchodsken.data.FoodInput
import kotlinx.coroutines.runBlocking
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class FoodsTest {
    private val db = AppDatabase.inMemory(ApplicationProvider.getApplicationContext())
    private val foods = db.foods()

    @After fun close() = db.close()

    private fun input(name: String, vararg stores: String, related: List<Long> = emptyList()) =
        FoodInput(name = name, receiptName = name.take(8) + ".", stores = stores.toList(), relatedIds = related)

    @Test fun requiredFieldsAreValidated() {
        val e = FoodInput(name = " ", receiptName = "", stores = listOf(" ")).errors()
        assertEquals(setOf("name", "receiptName", "stores"), e.keys)
        val ok = FoodInput("Rohlík", "Rohlík tuk.", listOf("Lidl"))
        assertTrue(ok.errors().isEmpty())
    }

    @Test fun optionalFieldsAreValidatedOnlyWhenFilled() {
        val base = FoodInput("Mléko", "Mléko 1,5%", listOf("Lidl"))
        assertEquals(setOf("sizeKg"), base.copy(sizeKg = "abc").errors().keys)
        assertEquals(setOf("sizeKg"), base.copy(sizeKg = "0").errors().keys)
        assertEquals(setOf("imageUrl", "storeUrl"), base.copy(imageUrl = "obrazek.jpg", storeUrl = "www.lidl.cz").errors().keys)
        val ok = base.copy(sizeKg = "1,05 kg", imageUrl = "https://x.cz/a.jpg", storeUrl = "http://lidl.cz/p/1")
        assertTrue(ok.errors().isEmpty())
        assertEquals(1.05, ok.toEntity().sizeKg!!, 1e-9)
    }

    @Test fun storesAreTrimmedAndDeduplicated() {
        assertEquals(listOf("Lidl", "Billa"), FoodInput("a", "b", listOf(" Lidl", "lidl", "", "Billa")).cleanStores())
    }

    @Test fun saveEditAndDelete() = runBlocking {
        val milk = foods.saveFood(0, input("Mléko", "Lidl", "Kaufland"))
        val butter = foods.saveFood(0, input("Máslo", "Lidl", related = listOf(milk)))

        // příbuznost platí oběma směry
        assertEquals(listOf("Mléko"), foods.relatedOf(butter).map { it.name })
        assertEquals(listOf("Máslo"), foods.relatedOf(milk).map { it.name })
        assertEquals(listOf("Kaufland", "Lidl"), foods.storesOf(milk))

        // úprava přepíše obchody i příbuzné a zachová datum vytvoření
        val created = foods.food(milk)!!.createdAt
        foods.saveFood(milk, input("Mléko polotučné", "Albert").copy(sizeKg = "1"))
        val d = foods.detail(milk)!!
        assertEquals("Mléko polotučné", d.food.name)
        assertEquals(1.0, d.food.sizeKg!!, 0.0)
        assertEquals(created, d.food.createdAt)
        assertEquals(listOf("Albert"), d.stores)
        assertTrue(d.related.isEmpty())
        assertTrue(foods.relatedOf(butter).isEmpty())

        // smazání odstraní i vazby
        foods.saveFood(milk, input("Mléko polotučné", "Albert", related = listOf(butter)))
        foods.deleteFood(milk)
        assertNull(foods.detail(milk))
        assertTrue(foods.relatedOf(butter).isEmpty())
        assertEquals(listOf("Lidl"), foods.usedStores())
        assertEquals(1, foods.foodCount())
    }
}
