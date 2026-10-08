package cz.obchodsken.barcode

import cz.obchodsken.data.ProductEntity
import cz.obchodsken.parser.ProductNames
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL

/**
 * Vyhledání produktu podle čárového kódu ve volných databázích
 * Open Food Facts (potraviny), Open Beauty Facts (kosmetika) a Open Products Facts (ostatní).
 */
object ProductLookup {
    private val hosts = listOf(
        "world.openfoodfacts.org" to "Open Food Facts",
        "world.openbeautyfacts.org" to "Open Beauty Facts",
        "world.openproductsfacts.org" to "Open Products Facts",
    )
    private const val FIELDS =
        "product_name,product_name_cs,generic_name_cs,generic_name,brands,quantity,categories_tags,image_front_small_url,image_front_url,nutriscore_grade,ingredients_text_cs,ingredients_text"

    suspend fun lookup(barcode: String): ProductEntity? = withContext(Dispatchers.IO) {
        for ((host, source) in hosts) {
            val json = try {
                get("https://$host/api/v2/product/$barcode.json?fields=$FIELDS")
            } catch (e: Exception) {
                null
            } ?: continue
            val obj = JSONObject(json)
            if (obj.optInt("status") != 1) continue
            val p = obj.optJSONObject("product") ?: continue
            val name = listOf("product_name_cs", "product_name", "generic_name_cs", "generic_name")
                .map { p.optString(it).trim() }.firstOrNull { it.isNotEmpty() } ?: continue
            val tags = p.optJSONArray("categories_tags")?.let { a -> (0 until a.length()).map { a.optString(it) } } ?: emptyList()
            return@withContext ProductEntity(
                barcode = barcode,
                name = name,
                brand = p.optString("brands").takeIf { it.isNotBlank() },
                quantity = p.optString("quantity").takeIf { it.isNotBlank() },
                category = ProductNames.categoryFromOff(tags, name).name,
                imageUrl = (p.optString("image_front_url").ifBlank { p.optString("image_front_small_url") }).takeIf { it.isNotBlank() },
                nutriscore = p.optString("nutriscore_grade").takeIf { it.length == 1 },
                ingredients = (p.optString("ingredients_text_cs").ifBlank { p.optString("ingredients_text") }).takeIf { it.isNotBlank() },
                source = source,
                linkedRawKey = null,
            )
        }
        null
    }

    private fun get(url: String): String? {
        val c = URL(url).openConnection() as HttpURLConnection
        c.connectTimeout = 8000
        c.readTimeout = 10000
        c.setRequestProperty("User-Agent", "Obchodsken/1.0 (Android; osobni aplikace na uctenky)")
        return try {
            if (c.responseCode != 200) null else c.inputStream.bufferedReader().use { it.readText() }
        } finally {
            c.disconnect()
        }
    }
}
