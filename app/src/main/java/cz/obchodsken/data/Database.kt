package cz.obchodsken.data

import android.content.Context
import androidx.room.AutoMigration
import androidx.room.Dao
import androidx.room.Database
import androidx.room.Entity
import androidx.room.ForeignKey
import androidx.room.Index
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.PrimaryKey
import androidx.room.Query
import androidx.room.Room
import androidx.room.RoomDatabase
import androidx.room.Transaction
import androidx.room.Update
import androidx.room.Upsert
import kotlinx.coroutines.flow.Flow

@Entity(tableName = "receipts", indices = [Index("uniqueKey"), Index("purchasedAt")])
data class ReceiptEntity(
    @PrimaryKey(autoGenerate = true) val id: Long = 0,
    val store: String,
    val branch: String?,
    /** epoch millis (lokální čas) */
    val purchasedAt: Long?,
    /** haléře */
    val total: Long,
    val totalDiscount: Long,
    val payment: String?,
    val receiptNumber: String?,
    val uniqueKey: String?,
    val imagePath: String?,
    /** Text z OCR po řádcích – umožňuje účtenku znovu zpracovat bez nového focení. */
    val ocrText: String,
    val warning: String?,
    val createdAt: Long = System.currentTimeMillis(),
)

@Entity(
    tableName = "items",
    foreignKeys = [ForeignKey(
        entity = ReceiptEntity::class, parentColumns = ["id"], childColumns = ["receiptId"],
        onDelete = ForeignKey.CASCADE,
    )],
    indices = [Index("receiptId"), Index("rawKey"), Index("name")],
)
data class ItemEntity(
    @PrimaryKey(autoGenerate = true) val id: Long = 0,
    val receiptId: Long,
    val position: Int,
    val rawName: String,
    val rawKey: String,
    val name: String,
    val category: String,
    val quantity: Double,
    val unit: String,
    val unitPrice: Long?,
    val price: Long,
    val discount: Long,
    val discountLabel: String?,
    val vat: String?,
    val articleCode: String?,
    val brand: String? = null,
    val imageUrl: String? = null,
    /** Produkt z katalogu, se kterým se položka spárovala (null = nerozpoznáno katalogem). */
    val catalogId: String? = null,
)

val ItemEntity.finalPrice: Long get() = price - discount
val ItemWithReceipt.finalPrice: Long get() = price - discount

/** Ruční opravy názvů – aplikace si je pamatuje a použije u dalších účtenek. */
@Entity(tableName = "name_mappings")
data class NameMappingEntity(
    @PrimaryKey val rawKey: String,
    val name: String,
    val category: String,
    val imageUrl: String? = null,
)

/**
 * Katalog produktů přibalený v aplikaci (assets/catalog (soubory .jsonl)) – připravený předem,
 * aby rozpoznání produktů nic nestálo a fungovalo offline.
 */
@Entity(tableName = "catalog_products")
data class CatalogProductEntity(
    @PrimaryKey val id: String,
    val store: String?,
    val name: String,
    val brand: String?,
    val quantity: String?,
    val category: String,
    val imageUrl: String?,
    val url: String?,
    val source: String?,
)

@Entity(tableName = "catalog_eans", indices = [Index("productId")])
data class CatalogEanEntity(@PrimaryKey val ean: String, val productId: String)

/** Název, pod kterým je produkt vytištěný na účtence daného obchodu. */
@Entity(tableName = "catalog_aliases", primaryKeys = ["store", "alias"], indices = [Index("productId")])
data class CatalogAliasEntity(val store: String, val alias: String, val productId: String)

/** Naskenované čárové kódy, které se nikde nenašly – k doplnění do katalogu. */
@Entity(tableName = "unknown_codes")
data class UnknownCodeEntity(@PrimaryKey val code: String, val scannedAt: Long = System.currentTimeMillis())

data class UnmatchedItem(val store: String, val rawName: String, val name: String, val count: Int)

/** Produkt podle čárového kódu (z Open Food Facts nebo zadaný ručně). */
@Entity(tableName = "products", indices = [Index("linkedRawKey")])
data class ProductEntity(
    @PrimaryKey val barcode: String,
    val name: String,
    val brand: String?,
    val quantity: String?,
    val category: String,
    val imageUrl: String?,
    val nutriscore: String?,
    val ingredients: String?,
    val source: String,
    /** Propojení s položkou z účtenek (ItemEntity.rawKey). */
    val linkedRawKey: String?,
    val updatedAt: Long = System.currentTimeMillis(),
)

data class ReceiptWithCount(
    val id: Long,
    val store: String,
    val branch: String?,
    val purchasedAt: Long?,
    val total: Long,
    val warning: String?,
    val itemCount: Int,
)

data class ItemWithReceipt(
    val id: Long,
    val receiptId: Long,
    val rawName: String,
    val rawKey: String,
    val name: String,
    val category: String,
    val quantity: Double,
    val unit: String,
    val unitPrice: Long?,
    val price: Long,
    val discount: Long,
    val store: String,
    val branch: String?,
    val purchasedAt: Long?,
)

data class ProductSummary(
    val name: String,
    val category: String,
    val rawKey: String,
    val count: Int,
    val spent: Long,
    val lastPrice: Long,
    val lastAt: Long?,
)

data class CategorySum(val category: String, val spent: Long, val count: Int)
data class MonthSum(val month: String, val spent: Long, val receipts: Int)
data class RawNameCount(val rawKey: String, val rawName: String, val name: String, val count: Int)

@Dao
interface AppDao {
    // --- účtenky ---
    @Insert suspend fun insertReceipt(r: ReceiptEntity): Long
    @Update suspend fun updateReceipt(r: ReceiptEntity)
    @Query("DELETE FROM receipts WHERE id = :id") suspend fun deleteReceipt(id: Long)
    @Query("SELECT * FROM receipts WHERE id = :id") suspend fun receipt(id: Long): ReceiptEntity?
    @Query("SELECT * FROM receipts WHERE id = :id") fun receiptFlow(id: Long): Flow<ReceiptEntity?>
    @Query("SELECT id FROM receipts WHERE uniqueKey = :key LIMIT 1") suspend fun findByKey(key: String): Long?
    @Query("SELECT COUNT(*) FROM receipts") suspend fun receiptCount(): Int
    @Query("SELECT imagePath FROM receipts WHERE imagePath IS NOT NULL") suspend fun allImagePaths(): List<String>

    @Query(
        """SELECT r.id, r.store, r.branch, r.purchasedAt, r.total, r.warning,
           (SELECT COUNT(*) FROM items i WHERE i.receiptId = r.id) AS itemCount
           FROM receipts r ORDER BY COALESCE(r.purchasedAt, r.createdAt) DESC"""
    )
    fun receipts(): Flow<List<ReceiptWithCount>>

    // --- položky ---
    @Insert suspend fun insertItems(items: List<ItemEntity>)
    @Insert suspend fun insertItem(item: ItemEntity): Long
    @Update suspend fun updateItem(item: ItemEntity)
    @Query("DELETE FROM items WHERE id = :id") suspend fun deleteItem(id: Long)
    @Query("DELETE FROM items WHERE receiptId = :receiptId") suspend fun deleteItemsOf(receiptId: Long)
    @Query("SELECT * FROM items WHERE receiptId = :receiptId ORDER BY position") fun itemsFlow(receiptId: Long): Flow<List<ItemEntity>>
    @Query("SELECT * FROM items WHERE receiptId = :receiptId ORDER BY position") suspend fun items(receiptId: Long): List<ItemEntity>
    @Query("UPDATE items SET name = :name, category = :category WHERE rawKey = :rawKey")
    suspend fun renameAll(rawKey: String, name: String, category: String)
    @Query("SELECT * FROM name_mappings WHERE rawKey = :rawKey") suspend fun mapping(rawKey: String): NameMappingEntity?

    @Query(
        """SELECT i.id, i.receiptId, i.rawName, i.rawKey, i.name, i.category, i.quantity, i.unit, i.unitPrice,
           i.price, i.discount, r.store, r.branch, r.purchasedAt
           FROM items i JOIN receipts r ON r.id = i.receiptId
           WHERE i.name = :name ORDER BY r.purchasedAt DESC"""
    )
    fun historyByName(name: String): Flow<List<ItemWithReceipt>>

    @Query(
        """SELECT i.id, i.receiptId, i.rawName, i.rawKey, i.name, i.category, i.quantity, i.unit, i.unitPrice,
           i.price, i.discount, r.store, r.branch, r.purchasedAt
           FROM items i JOIN receipts r ON r.id = i.receiptId
           WHERE i.rawKey = :rawKey ORDER BY r.purchasedAt DESC"""
    )
    suspend fun historyByRawKey(rawKey: String): List<ItemWithReceipt>

    @Query(
        """SELECT i.name, i.category, MIN(i.rawKey) AS rawKey, COUNT(*) AS count, SUM(i.price - i.discount) AS spent,
           (SELECT i2.price - i2.discount FROM items i2 JOIN receipts r2 ON r2.id = i2.receiptId
              WHERE i2.name = i.name ORDER BY r2.purchasedAt DESC LIMIT 1) AS lastPrice,
           MAX(r.purchasedAt) AS lastAt
           FROM items i JOIN receipts r ON r.id = i.receiptId
           GROUP BY i.name ORDER BY count DESC, spent DESC"""
    )
    fun productSummaries(): Flow<List<ProductSummary>>

    @Query(
        """SELECT rawKey, MIN(rawName) AS rawName, MIN(name) AS name, COUNT(*) AS count
           FROM items GROUP BY rawKey ORDER BY count DESC"""
    )
    suspend fun rawNames(): List<RawNameCount>

    // --- statistiky ---
    @Query(
        """SELECT i.category AS category, SUM(i.price - i.discount) AS spent, COUNT(*) AS count
           FROM items i JOIN receipts r ON r.id = i.receiptId
           WHERE (:from IS NULL OR r.purchasedAt >= :from)
           GROUP BY i.category ORDER BY spent DESC"""
    )
    fun categorySums(from: Long?): Flow<List<CategorySum>>

    @Query(
        """SELECT strftime('%Y-%m', purchasedAt / 1000, 'unixepoch', 'localtime') AS month, SUM(total) AS spent, COUNT(*) AS receipts
           FROM receipts WHERE purchasedAt IS NOT NULL GROUP BY month ORDER BY month DESC LIMIT 24"""
    )
    fun monthSums(): Flow<List<MonthSum>>

    @Query("SELECT COALESCE(SUM(total), 0) FROM receipts WHERE (:from IS NULL OR purchasedAt >= :from)")
    fun totalSpent(from: Long?): Flow<Long>

    @Query("SELECT COALESCE(SUM(totalDiscount), 0) FROM receipts WHERE (:from IS NULL OR purchasedAt >= :from)")
    fun totalSaved(from: Long?): Flow<Long>

    // --- naučené názvy ---
    @Upsert suspend fun upsertMapping(m: NameMappingEntity)
    @Query("SELECT * FROM name_mappings") suspend fun mappings(): List<NameMappingEntity>

    // --- produkty (čárové kódy) ---
    @Insert(onConflict = OnConflictStrategy.REPLACE) suspend fun upsertProduct(p: ProductEntity)
    @Query("SELECT * FROM products WHERE barcode = :code") suspend fun product(code: String): ProductEntity?
    @Query("SELECT * FROM products WHERE linkedRawKey = :rawKey") suspend fun productsForRawKey(rawKey: String): List<ProductEntity>
    @Query("SELECT * FROM products ORDER BY updatedAt DESC") fun products(): Flow<List<ProductEntity>>

    // --- export ---
    @Query(
        """SELECT i.id, i.receiptId, i.rawName, i.rawKey, i.name, i.category, i.quantity, i.unit, i.unitPrice,
           i.price, i.discount, r.store, r.branch, r.purchasedAt
           FROM items i JOIN receipts r ON r.id = i.receiptId ORDER BY r.purchasedAt, i.position"""
    )
    suspend fun allItems(): List<ItemWithReceipt>

    // --- katalog ---
    @Insert(onConflict = OnConflictStrategy.REPLACE) suspend fun insertCatalogProducts(p: List<CatalogProductEntity>)
    @Insert(onConflict = OnConflictStrategy.REPLACE) suspend fun insertCatalogEans(e: List<CatalogEanEntity>)
    @Insert(onConflict = OnConflictStrategy.REPLACE) suspend fun insertCatalogAliases(a: List<CatalogAliasEntity>)
    @Query("DELETE FROM catalog_products") suspend fun clearCatalogProducts()
    @Query("DELETE FROM catalog_eans") suspend fun clearCatalogEans()
    @Query("DELETE FROM catalog_aliases") suspend fun clearCatalogAliases()
    @Query("SELECT * FROM catalog_aliases") suspend fun catalogAliases(): List<CatalogAliasEntity>
    @Query("SELECT * FROM catalog_products WHERE id = :id") suspend fun catalogProduct(id: String): CatalogProductEntity?
    @Query("SELECT p.* FROM catalog_products p JOIN catalog_eans e ON e.productId = p.id WHERE e.ean = :ean LIMIT 1")
    suspend fun catalogByEan(ean: String): CatalogProductEntity?
    @Query("SELECT COUNT(*) FROM catalog_products") suspend fun catalogCount(): Int

    @Upsert suspend fun addUnknownCode(c: UnknownCodeEntity)
    @Query("DELETE FROM unknown_codes WHERE code = :code") suspend fun removeUnknownCode(code: String)
    @Query("SELECT * FROM unknown_codes ORDER BY scannedAt DESC") suspend fun unknownCodes(): List<UnknownCodeEntity>
    @Query(
        """SELECT r.store AS store, MIN(i.rawName) AS rawName, MIN(i.name) AS name, COUNT(*) AS count
           FROM items i JOIN receipts r ON r.id = i.receiptId
           WHERE i.catalogId IS NULL AND i.rawKey NOT IN (SELECT rawKey FROM name_mappings)
           GROUP BY r.store, i.rawKey ORDER BY count DESC"""
    )
    suspend fun unmatchedItems(): List<UnmatchedItem>
    @Query("SELECT COUNT(DISTINCT i.rawKey) FROM items i WHERE i.catalogId IS NULL AND i.rawKey NOT IN (SELECT rawKey FROM name_mappings)")
    fun unmatchedCount(): Flow<Int>

    @Query("UPDATE items SET imageUrl = :imageUrl WHERE rawKey = :rawKey AND imageUrl IS NULL")
    suspend fun setImageForRawKey(rawKey: String, imageUrl: String)

    @Transaction
    suspend fun replaceCatalog(p: List<CatalogProductEntity>, e: List<CatalogEanEntity>, a: List<CatalogAliasEntity>) {
        clearCatalogAliases(); clearCatalogEans(); clearCatalogProducts()
        p.chunked(500).forEach { insertCatalogProducts(it) }
        e.chunked(500).forEach { insertCatalogEans(it) }
        a.chunked(500).forEach { insertCatalogAliases(it) }
    }

    @Transaction
    suspend fun insertReceiptWithItems(r: ReceiptEntity, items: List<ItemEntity>): Long {
        val id = insertReceipt(r)
        insertItems(items.map { it.copy(receiptId = id) })
        return id
    }

    @Transaction
    suspend fun replaceItems(receiptId: Long, items: List<ItemEntity>) {
        deleteItemsOf(receiptId)
        insertItems(items.map { it.copy(receiptId = receiptId) })
    }
}

@Database(
    entities = [
        ReceiptEntity::class, ItemEntity::class, NameMappingEntity::class, ProductEntity::class,
        CatalogProductEntity::class, CatalogEanEntity::class, CatalogAliasEntity::class, UnknownCodeEntity::class,
    ],
    version = 2,
    exportSchema = true,
    autoMigrations = [AutoMigration(from = 1, to = 2)],
)
abstract class AppDatabase : RoomDatabase() {
    abstract fun dao(): AppDao

    companion object {
        fun create(context: Context): AppDatabase =
            Room.databaseBuilder(context, AppDatabase::class.java, "obchodsken.db").build()

        fun inMemory(context: Context): AppDatabase =
            Room.inMemoryDatabaseBuilder(context, AppDatabase::class.java).allowMainThreadQueries().build()
    }
}
