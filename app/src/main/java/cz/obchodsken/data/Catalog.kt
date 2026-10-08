package cz.obchodsken.data

import android.content.Context
import cz.obchodsken.parser.Category
import cz.obchodsken.parser.NameMatcher
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext
import org.json.JSONObject

/**
 * Katalog produktů z assets/catalog (soubory .jsonl) (jeden produkt = jeden řádek JSON, formát viz catalog/FORMAT.md).
 * Při nové verzi aplikace se znovu nahraje do databáze; párování názvů z účtenek běží v paměti.
 */
class Catalog(private val context: Context, private val dao: AppDao) {
    private val mutex = Mutex()
    private var byStore: Map<String, NameMatcher<String>>? = null
    private var anyStore: NameMatcher<String>? = null

    /** Nahraje katalog do DB, pokud se od minula změnil (= nová verze aplikace). */
    suspend fun ensureLoaded() = mutex.withLock {
        if (byStore != null) return@withLock
        withContext(Dispatchers.IO) {
            val prefs = context.getSharedPreferences("catalog", Context.MODE_PRIVATE)
            val stamp = context.packageManager.getPackageInfo(context.packageName, 0).lastUpdateTime
            if (prefs.getLong("stamp", -1) != stamp) {
                importAssets()
                prefs.edit().putLong("stamp", stamp).apply()
            }
            val aliases = dao.catalogAliases()
            byStore = aliases.groupBy { it.store }.mapValues { (_, l) -> NameMatcher(l.map { it.alias to it.productId }) }
            anyStore = NameMatcher(aliases.map { it.alias to it.productId })
        }
    }

    private suspend fun importAssets() {
        val files = context.assets.list("catalog").orEmpty().filter { it.endsWith(".jsonl") }
        val products = ArrayList<CatalogProductEntity>()
        val eans = ArrayList<CatalogEanEntity>()
        val aliases = ArrayList<CatalogAliasEntity>()
        for (f in files) {
            context.assets.open("catalog/$f").bufferedReader(Charsets.UTF_8).useLines { lines ->
                for (line in lines) {
                    val t = line.trim()
                    if (t.isEmpty() || t.startsWith("//")) continue
                    val o = try { JSONObject(t) } catch (e: Exception) { continue }
                    val parsed = parse(o, f.removeSuffix(".jsonl")) ?: continue
                    products += parsed.first
                    eans += parsed.second
                    aliases += parsed.third
                }
            }
        }
        dao.replaceCatalog(products, eans, aliases)
    }

    /** Párování položky z účtenky: nejdřív stejný obchod, pak kterýkoli. */
    suspend fun matchReceiptItem(store: String, rawName: String): CatalogProductEntity? {
        ensureLoaded()
        val id = byStore?.get(storeKey(store))?.find(rawName) ?: anyStore?.find(rawName) ?: return null
        return dao.catalogProduct(id)
    }

    suspend fun byEan(ean: String): CatalogProductEntity? {
        ensureLoaded()
        return dao.catalogByEan(ean)
    }

    companion object {
        fun storeKey(store: String?): String = store?.trim()?.lowercase() ?: ""

        /** Jeden řádek katalogu -> entity. Veřejné kvůli testům. */
        fun parse(o: JSONObject, fileName: String): Triple<CatalogProductEntity, List<CatalogEanEntity>, List<CatalogAliasEntity>>? {
            val name = o.optString("name").trim().ifEmpty { return null }
            val store = o.optString("store").trim().ifEmpty { null }
            val id = "$fileName:" + o.optString("id").trim().ifEmpty { (store ?: "") + ":" + name }
            fun arr(k: String) = o.optJSONArray(k)?.let { a -> (0 until a.length()).map { a.optString(it).trim() }.filter { it.isNotEmpty() } }.orEmpty()
            val cat = o.optString("category").trim().uppercase()
            val product = CatalogProductEntity(
                id = id, store = store, name = name,
                brand = o.optString("brand").trim().ifEmpty { null },
                quantity = o.optString("quantity").trim().ifEmpty { null },
                category = Category.entries.firstOrNull { it.name == cat }?.name ?: Category.OSTATNI.name,
                imageUrl = o.optString("image").trim().ifEmpty { null },
                url = o.optString("url").trim().ifEmpty { null },
                source = o.optString("source").trim().ifEmpty { null },
            )
            val eans = arr("eans").filter { it.all(Char::isDigit) }.map { CatalogEanEntity(it, id) }
            val aliases = arr("aliases").map { CatalogAliasEntity(storeKey(store), it, id) }
            return Triple(product, eans, aliases)
        }
    }
}
