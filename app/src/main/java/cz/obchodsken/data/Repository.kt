package cz.obchodsken.data

import android.content.Context
import android.graphics.Bitmap
import android.net.Uri
import cz.obchodsken.barcode.ProductLookup
import cz.obchodsken.ocr.ReceiptOcr
import cz.obchodsken.parser.Category
import cz.obchodsken.parser.Money
import cz.obchodsken.parser.ParsedReceipt
import cz.obchodsken.parser.ProductInfo
import cz.obchodsken.parser.ProductNames
import cz.obchodsken.parser.ReceiptParser
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext
import java.io.File
import java.io.FileOutputStream
import java.time.Instant
import java.time.LocalDateTime
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.util.UUID

sealed interface ImportOutcome {
    data class Saved(val id: Long, val warning: String?) : ImportOutcome
    data class Duplicate(val id: Long) : ImportOutcome
    data class NotReceipt(val reason: String) : ImportOutcome
}

data class ImportState(
    val running: Boolean = false,
    val total: Int = 0,
    val done: Int = 0,
    val saved: Int = 0,
    val duplicates: Int = 0,
    val failed: Int = 0,
    val withWarnings: Int = 0,
    val lastSavedId: Long? = null,
    val lastError: String? = null,
)

class Repository(private val context: Context, private val db: AppDatabase, private val scope: CoroutineScope) {
    val dao = db.dao()
    private val ocr by lazy { ReceiptOcr() }
    private val importMutex = Mutex()

    private val _import = MutableStateFlow(ImportState())
    val importState: StateFlow<ImportState> = _import.asStateFlow()

    private val imagesDir: File get() = File(context.filesDir, "receipts").apply { mkdirs() }

    // ---------------------------------------------------------------- import

    /** Hromadný import (galerie, sdílení z jiné aplikace). Běží na pozadí aplikace. */
    fun enqueue(uris: List<Uri>) {
        if (uris.isEmpty()) return
        _import.update {
            if (it.running) it.copy(total = it.total + uris.size)
            else ImportState(running = true, total = uris.size)
        }
        scope.launch {
            importMutex.withLock {
                for (uri in uris) {
                    val outcome = try {
                        importUri(uri)
                    } catch (e: Throwable) {
                        ImportOutcome.NotReceipt(e.message ?: e.javaClass.simpleName)
                    }
                    _import.update { s ->
                        when (outcome) {
                            is ImportOutcome.Saved -> s.copy(
                                done = s.done + 1, saved = s.saved + 1, lastSavedId = outcome.id,
                                withWarnings = s.withWarnings + if (outcome.warning != null) 1 else 0,
                            )
                            is ImportOutcome.Duplicate -> s.copy(done = s.done + 1, duplicates = s.duplicates + 1)
                            is ImportOutcome.NotReceipt -> s.copy(done = s.done + 1, failed = s.failed + 1, lastError = outcome.reason)
                        }
                    }
                }
                _import.update { if (it.done >= it.total) it.copy(running = false) else it }
            }
        }
    }

    fun dismissImportState() = _import.update { if (it.running) it else ImportState() }

    /** Zpracuje jednu fotku/screenshot účtenky. */
    suspend fun importUri(uri: Uri): ImportOutcome = withContext(Dispatchers.Default) {
        val bitmap = ReceiptOcr.loadBitmap(context, uri)
            ?: return@withContext ImportOutcome.NotReceipt("Obrázek se nepodařilo načíst")
        val result = ocr.recognize(bitmap)
        try {
            val parsed = ReceiptParser.parse(result.rows)
            if (parsed.items.isEmpty() && parsed.total == null) {
                return@withContext ImportOutcome.NotReceipt("Na obrázku jsem nenašel účtenku")
            }
            parsed.uniqueKey?.let { key -> dao.findByKey(key)?.let { return@withContext ImportOutcome.Duplicate(it) } }
            val imagePath = saveImage(result.bitmap)
            val id = save(parsed, result.rows, imagePath)
            ImportOutcome.Saved(id, parsed.warnings.firstOrNull())
        } finally {
            if (result.bitmap !== bitmap) result.bitmap.recycle()
            bitmap.recycle()
        }
    }

    private suspend fun learned(): Map<String, ProductInfo> =
        dao.mappings().associate { it.rawKey to ProductInfo(it.name, Category.of(it.category)) }

    private suspend fun save(parsed: ParsedReceipt, rows: List<String>, imagePath: String?): Long {
        val learned = learned()
        val receipt = ReceiptEntity(
            store = parsed.store,
            branch = parsed.branch,
            purchasedAt = parsed.purchasedAt?.toEpochMillis(),
            total = parsed.effectiveTotal,
            totalDiscount = parsed.totalDiscount,
            payment = parsed.payment,
            receiptNumber = parsed.receiptNumber,
            uniqueKey = parsed.uniqueKey,
            imagePath = imagePath,
            ocrText = rows.joinToString("\n"),
            warning = parsed.warnings.joinToString("\n").ifEmpty { null },
        )
        return dao.insertReceiptWithItems(receipt, toItems(parsed, learned))
    }

    private fun toItems(parsed: ParsedReceipt, learned: Map<String, ProductInfo>): List<ItemEntity> =
        parsed.items.mapIndexed { i, it ->
            val info = ProductNames.describe(it.rawName, learned)
            ItemEntity(
                receiptId = 0, position = i, rawName = it.rawName, rawKey = ProductNames.key(it.rawName),
                name = info.name, category = info.category.name, quantity = it.quantity, unit = it.unit,
                unitPrice = it.unitPrice, price = it.price, discount = it.discount,
                discountLabel = it.discountLabel, vat = it.vat, articleCode = it.articleCode,
            )
        }

    /** Znovu zpracuje uložený text z OCR (např. po vylepšení parseru). Ruční úpravy položek se přepíšou. */
    suspend fun reparse(receiptId: Long) {
        val r = dao.receipt(receiptId) ?: return
        val parsed = ReceiptParser.parse(r.ocrText.lines())
        dao.replaceItems(receiptId, toItems(parsed, learned()))
        dao.updateReceipt(
            r.copy(
                store = parsed.store, branch = parsed.branch ?: r.branch,
                purchasedAt = parsed.purchasedAt?.toEpochMillis() ?: r.purchasedAt,
                total = parsed.effectiveTotal, totalDiscount = parsed.totalDiscount,
                payment = parsed.payment ?: r.payment, uniqueKey = parsed.uniqueKey ?: r.uniqueKey,
                warning = parsed.warnings.joinToString("\n").ifEmpty { null },
            )
        )
    }

    private fun saveImage(b: Bitmap): String? = try {
        val maxW = 1200
        val scaled = if (b.width > maxW) Bitmap.createScaledBitmap(b, maxW, (b.height * maxW.toFloat() / b.width).toInt(), true) else b
        val f = File(imagesDir, UUID.randomUUID().toString() + ".jpg")
        FileOutputStream(f).use { scaled.compress(Bitmap.CompressFormat.JPEG, 80, it) }
        if (scaled !== b) scaled.recycle()
        f.absolutePath
    } catch (e: Exception) {
        null
    }

    // ---------------------------------------------------------------- úpravy

    suspend fun updateItem(item: ItemEntity, applyToAll: Boolean) {
        dao.updateItem(item)
        if (applyToAll) {
            dao.upsertMapping(NameMappingEntity(item.rawKey, item.name, item.category))
            dao.renameAll(item.rawKey, item.name, item.category)
        }
        recalcWarning(item.receiptId)
    }

    suspend fun addItem(receiptId: Long, name: String, price: Long, category: Category) {
        val pos = (dao.items(receiptId).maxOfOrNull { it.position } ?: -1) + 1
        dao.insertItem(
            ItemEntity(
                receiptId = receiptId, position = pos, rawName = name, rawKey = ProductNames.key(name), name = name,
                category = category.name, quantity = 1.0, unit = "ks", unitPrice = null, price = price,
                discount = 0, discountLabel = null, vat = null, articleCode = null,
            )
        )
        recalcWarning(receiptId)
    }

    suspend fun deleteItem(item: ItemEntity) {
        dao.deleteItem(item.id)
        recalcWarning(item.receiptId)
    }

    suspend fun updateReceipt(r: ReceiptEntity) {
        dao.updateReceipt(r)
        recalcWarning(r.id)
    }

    private suspend fun recalcWarning(receiptId: Long) {
        val r = dao.receipt(receiptId) ?: return
        val sum = dao.items(receiptId).sumOf { it.finalPrice }
        val w = if (kotlin.math.abs(sum - r.total) > 100) // zaokrouhlení u hotovosti
            "Součet položek ${Money.format(sum)} nesedí s celkem ${Money.format(r.total)}." else null
        if (w != r.warning) dao.updateReceipt(r.copy(warning = w))
    }

    suspend fun deleteReceipt(id: Long) {
        dao.receipt(id)?.imagePath?.let { File(it).delete() }
        dao.deleteReceipt(id)
    }

    // ---------------------------------------------------------------- čárové kódy

    data class BarcodeResult(
        val product: ProductEntity?,
        val history: List<ItemWithReceipt>,
        val suggestions: List<RawNameCount>,
        val offline: Boolean,
    )

    suspend fun lookupBarcode(code: String, forceOnline: Boolean = false): BarcodeResult {
        var product = dao.product(code)
        var offline = false
        if (product == null || forceOnline) {
            val online = try { ProductLookup.lookup(code) } catch (e: Exception) { offline = true; null }
            if (online != null) {
                product = online.copy(linkedRawKey = product?.linkedRawKey)
                dao.upsertProduct(product)
            }
        }
        val history = product?.linkedRawKey?.let { dao.historyByRawKey(it) } ?: emptyList()
        val suggestions = if (product != null && product.linkedRawKey == null) {
            val n = product.name + " " + (product.brand ?: "")
            dao.rawNames()
                .map { it to maxOf(ProductNames.similarity(n, it.rawName), ProductNames.similarity(n, it.name)) }
                .filter { it.second >= 0.5 }
                .sortedByDescending { it.second }
                .take(5).map { it.first }
        } else emptyList()
        return BarcodeResult(product, history, suggestions, offline)
    }

    suspend fun saveManualProduct(code: String, name: String, category: Category, linkedRawKey: String?) {
        val existing = dao.product(code)
        dao.upsertProduct(
            (existing ?: ProductEntity(
                barcode = code, name = name, brand = null, quantity = null, category = category.name,
                imageUrl = null, nutriscore = null, ingredients = null, source = "Ručně", linkedRawKey = null,
            )).copy(name = name, category = category.name, linkedRawKey = linkedRawKey ?: existing?.linkedRawKey,
                updatedAt = System.currentTimeMillis())
        )
    }

    suspend fun linkProduct(code: String, rawKey: String?) {
        dao.product(code)?.let { dao.upsertProduct(it.copy(linkedRawKey = rawKey, updatedAt = System.currentTimeMillis())) }
    }

    suspend fun rawNames(): List<RawNameCount> = dao.rawNames()

    // ---------------------------------------------------------------- export

    suspend fun exportCsv(): File = withContext(Dispatchers.IO) {
        val f = File(context.cacheDir, "export/polozky.csv").apply { parentFile?.mkdirs() }
        val fmt = DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm")
        f.bufferedWriter(Charsets.UTF_8).use { w ->
            w.write("﻿datum;obchod;pobočka;položka (účtenka);název;kategorie;množství;jednotka;cena;sleva;zaplaceno\n")
            for (i in dao.allItems()) {
                val d = i.purchasedAt?.let { fmt.format(it.toLocalDateTime()) } ?: ""
                fun q(s: String?) = "\"" + (s ?: "").replace("\"", "\"\"") + "\""
                w.write(
                    listOf(
                        d, q(i.store), q(i.branch), q(i.rawName), q(i.name), q(Category.of(i.category).label),
                        i.quantity.toString().replace('.', ','), i.unit,
                        Money.format(i.price, false), Money.format(i.discount, false), Money.format(i.finalPrice, false),
                    ).joinToString(";") + "\n"
                )
            }
        }
        f
    }
}

fun LocalDateTime.toEpochMillis(): Long = atZone(ZoneId.systemDefault()).toInstant().toEpochMilli()
fun Long.toLocalDateTime(): LocalDateTime = LocalDateTime.ofInstant(Instant.ofEpochMilli(this), ZoneId.systemDefault())
