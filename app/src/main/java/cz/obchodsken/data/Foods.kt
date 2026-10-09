package cz.obchodsken.data

import androidx.room.Dao
import androidx.room.Entity
import androidx.room.ForeignKey
import androidx.room.Index
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.PrimaryKey
import androidx.room.Query
import androidx.room.Transaction
import androidx.room.Update
import kotlinx.coroutines.flow.Flow

/**
 * Databáze potravin zadávaných ručně. Na rozdíl od katalogu (assets/catalog) se při nové verzi aplikace
 * nepřepisuje – je to vlastní data uživatele.
 */
@Entity(tableName = "foods", indices = [Index("name"), Index("receiptName")])
data class FoodEntity(
    @PrimaryKey(autoGenerate = true) val id: Long = 0,
    /** Skutečný název potraviny. */
    val name: String,
    /** Název tak, jak je vytištěný na účtence. */
    val receiptName: String,
    /** Velikost balení v kg (nepovinné). */
    val sizeKg: Double? = null,
    val imageUrl: String? = null,
    /** Odkaz na stránku produktu v obchodě. */
    val storeUrl: String? = null,
    val createdAt: Long = System.currentTimeMillis(),
    val updatedAt: Long = System.currentTimeMillis(),
)

/** Obchody, ve kterých se potravina prodává (alespoň jeden). */
@Entity(
    tableName = "food_stores",
    primaryKeys = ["foodId", "store"],
    foreignKeys = [ForeignKey(entity = FoodEntity::class, parentColumns = ["id"], childColumns = ["foodId"], onDelete = ForeignKey.CASCADE)],
    indices = [Index("store")],
)
data class FoodStoreEntity(val foodId: Long, val store: String)

/** Příbuzné potraviny. Ukládá se oběma směry (A→B i B→A), takže stačí hledat podle foodId. */
@Entity(
    tableName = "food_relations",
    primaryKeys = ["foodId", "relatedId"],
    foreignKeys = [
        ForeignKey(entity = FoodEntity::class, parentColumns = ["id"], childColumns = ["foodId"], onDelete = ForeignKey.CASCADE),
        ForeignKey(entity = FoodEntity::class, parentColumns = ["id"], childColumns = ["relatedId"], onDelete = ForeignKey.CASCADE),
    ],
    indices = [Index("relatedId")],
)
data class FoodRelationEntity(val foodId: Long, val relatedId: Long)

/** Řádek seznamu potravin – obchody spojené čárkou. */
data class FoodListRow(
    val id: Long,
    val name: String,
    val receiptName: String,
    val sizeKg: Double?,
    val imageUrl: String?,
    val stores: String?,
)

/** Potravina se vším, co k ní patří – pro formulář. */
data class FoodDetail(val food: FoodEntity, val stores: List<String>, val related: List<FoodEntity>)

/** Co uživatel vyplnil ve formuláři (texty tak, jak jsou). */
data class FoodInput(
    val name: String,
    val receiptName: String,
    val stores: List<String>,
    val sizeKg: String = "",
    val relatedIds: List<Long> = emptyList(),
    val imageUrl: String = "",
    val storeUrl: String = "",
) {
    /** Chyby podle pole (prázdné = lze uložit). */
    fun errors(): Map<String, String> = buildMap {
        if (name.isBlank()) put("name", "Vyplň název potraviny")
        if (receiptName.isBlank()) put("receiptName", "Vyplň název z účtenky")
        if (cleanStores().isEmpty()) put("stores", "Vyber aspoň jeden obchod")
        if (sizeKg.isNotBlank() && (parseKg(sizeKg) ?: 0.0) <= 0.0) put("sizeKg", "Zadej kladné číslo v kg, např. 0,5")
        if (imageUrl.isNotBlank() && !isUrl(imageUrl)) put("imageUrl", "Odkaz musí začínat http:// nebo https://")
        if (storeUrl.isNotBlank() && !isUrl(storeUrl)) put("storeUrl", "Odkaz musí začínat http:// nebo https://")
    }

    /** Obchody bez prázdných a duplicit (bez ohledu na velikost písmen), v pořadí zadání. */
    fun cleanStores(): List<String> = stores.map { it.trim() }.filter { it.isNotEmpty() }.distinctBy { it.lowercase() }

    fun toEntity(id: Long = 0, createdAt: Long = System.currentTimeMillis()): FoodEntity {
        check(errors().isEmpty()) { "Neplatná potravina: ${errors()}" }
        return FoodEntity(
            id = id,
            name = name.trim(),
            receiptName = receiptName.trim(),
            sizeKg = if (sizeKg.isBlank()) null else parseKg(sizeKg),
            imageUrl = imageUrl.trim().ifEmpty { null },
            storeUrl = storeUrl.trim().ifEmpty { null },
            createdAt = createdAt,
        )
    }

    companion object {
        /** "0,5" / "0.5" / "1,25 kg" -> 0.5 / 1.25 */
        fun parseKg(s: String): Double? = s.trim().lowercase().removeSuffix("kg").trim().replace(" ", "").replace(',', '.').toDoubleOrNull()

        private fun isUrl(s: String): Boolean {
            val t = s.trim().lowercase()
            return (t.startsWith("http://") || t.startsWith("https://")) && t.length > t.indexOf("://") + 3 && ' ' !in t
        }
    }
}

@Dao
interface FoodDao {
    @Insert suspend fun insertFood(f: FoodEntity): Long
    @Update suspend fun updateFood(f: FoodEntity)
    @Query("DELETE FROM foods WHERE id = :id") suspend fun deleteFood(id: Long)
    @Query("SELECT * FROM foods WHERE id = :id") suspend fun food(id: Long): FoodEntity?
    @Query("SELECT * FROM foods ORDER BY name COLLATE NOCASE") suspend fun allFoods(): List<FoodEntity>
    @Query("SELECT COUNT(*) FROM foods") suspend fun foodCount(): Int

    @Query(
        """SELECT f.id, f.name, f.receiptName, f.sizeKg, f.imageUrl,
           (SELECT GROUP_CONCAT(s.store, ', ') FROM food_stores s WHERE s.foodId = f.id) AS stores
           FROM foods f ORDER BY f.name COLLATE NOCASE"""
    )
    fun foodList(): Flow<List<FoodListRow>>

    @Insert(onConflict = OnConflictStrategy.IGNORE) suspend fun insertStores(s: List<FoodStoreEntity>)
    @Query("DELETE FROM food_stores WHERE foodId = :foodId") suspend fun deleteStoresOf(foodId: Long)
    @Query("SELECT store FROM food_stores WHERE foodId = :foodId ORDER BY store COLLATE NOCASE") suspend fun storesOf(foodId: Long): List<String>
    /** Všechny dosud použité obchody – nabídka ve formuláři. */
    @Query("SELECT DISTINCT store FROM food_stores ORDER BY store COLLATE NOCASE") suspend fun usedStores(): List<String>

    @Insert(onConflict = OnConflictStrategy.IGNORE) suspend fun insertRelations(r: List<FoodRelationEntity>)
    @Query("DELETE FROM food_relations WHERE foodId = :foodId OR relatedId = :foodId") suspend fun deleteRelationsOf(foodId: Long)
    @Query("SELECT f.* FROM foods f JOIN food_relations r ON r.relatedId = f.id WHERE r.foodId = :foodId ORDER BY f.name COLLATE NOCASE")
    suspend fun relatedOf(foodId: Long): List<FoodEntity>

    @Transaction
    suspend fun detail(id: Long): FoodDetail? {
        val f = food(id) ?: return null
        return FoodDetail(f, storesOf(id), relatedOf(id))
    }

    /** Uloží novou (id = 0) nebo upraví existující potravinu i s obchody a příbuznými. Vrací id. */
    @Transaction
    suspend fun saveFood(id: Long, input: FoodInput): Long {
        val existing = if (id != 0L) food(id) else null
        val foodId = if (existing != null) {
            updateFood(input.toEntity(id, existing.createdAt))
            id
        } else {
            insertFood(input.toEntity())
        }
        deleteStoresOf(foodId)
        insertStores(input.cleanStores().map { FoodStoreEntity(foodId, it) })
        deleteRelationsOf(foodId)
        val related = input.relatedIds.distinct().filter { it != foodId && food(it) != null }
        insertRelations(related.flatMap { listOf(FoodRelationEntity(foodId, it), FoodRelationEntity(it, foodId)) })
        return foodId
    }
}
