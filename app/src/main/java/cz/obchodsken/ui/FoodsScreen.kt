package cz.obchodsken.ui

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.Search
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ExtendedFloatingActionButton
import androidx.compose.material3.FilterChip
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.InputChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.navigation.NavHostController
import cz.obchodsken.data.FoodEntity
import cz.obchodsken.data.FoodInput
import cz.obchodsken.parser.Category
import cz.obchodsken.parser.ProductNames
import kotlinx.coroutines.launch
import java.math.BigDecimal
import java.text.Collator
import java.util.Locale

/** Obchody nabízené ve formuláři vždy; další přibudou, jakmile je uživatel jednou zadá. */
private val defaultStores = listOf("Lidl", "Kaufland", "Albert", "Billa", "Penny", "Tesco", "Globus", "Rohlík")

/** Řazení podle české abecedy (SQLite by dal „Máslo“ až za „Mléko“). */
private val czech = Collator.getInstance(Locale.forLanguageTag("cs"))

fun NavHostController.openFood(id: Long) = navigate("food/$id")

fun formatKg(kg: Double): String = BigDecimal.valueOf(kg).stripTrailingZeros().toPlainString().replace('.', ',') + " kg"

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun FoodsScreen(nav: NavHostController) {
    val repo = repo()
    val all by repo.foods.foodList().collectAsState(initial = emptyList())
    var query by rememberSaveable { mutableStateOf("") }
    val q = ProductNames.stripDiacritics(query.lowercase().trim())
    val list = all.filter {
        q.isEmpty() || ProductNames.stripDiacritics("${it.name} ${it.receiptName} ${it.stores.orEmpty()}".lowercase()).contains(q)
    }.sortedWith(compareBy(czech) { it.name })
    Box(Modifier.fillMaxSize()) {
        Column(Modifier.fillMaxSize()) {
            TopAppBar(title = { Text("Potraviny (${all.size})") }, windowInsets = WindowInsets(0.dp))
            if (all.isNotEmpty()) OutlinedTextField(
                query, { query = it }, leadingIcon = { Icon(Icons.Default.Search, null) },
                placeholder = { Text("Hledat potravinu") }, singleLine = true,
                modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 4.dp),
            )
            if (all.isEmpty()) EmptyState("Databáze potravin je zatím prázdná. Přidej první potravinu tlačítkem dole.")
            LazyColumn(Modifier.fillMaxSize()) {
                items(list, key = { it.id }) { f ->
                    Row(
                        Modifier.fillMaxWidth().clickable { nav.openFood(f.id) }.padding(horizontal = 16.dp, vertical = 10.dp),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        ProductThumb(f.imageUrl, Category.OSTATNI)
                        Spacer(Modifier.width(12.dp))
                        Column(Modifier.weight(1f)) {
                            Text(f.name, style = MaterialTheme.typography.bodyLarge)
                            Text(
                                listOfNotNull("Na účtence: ${f.receiptName}", f.stores, f.sizeKg?.let(::formatKg)).joinToString(" · "),
                                style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                        }
                    }
                    HorizontalDivider()
                }
                item { Spacer(Modifier.height(80.dp)) }
            }
        }
        ExtendedFloatingActionButton(
            onClick = { nav.openFood(0) },
            icon = { Icon(Icons.Default.Add, null) },
            text = { Text("Přidat potravinu") },
            modifier = Modifier.align(Alignment.BottomEnd).padding(16.dp),
        )
    }
}

/** Formulář pro novou (id = 0) nebo existující potravinu. */
@OptIn(ExperimentalMaterial3Api::class, ExperimentalLayoutApi::class)
@Composable
fun FoodEditScreen(id: Long, nav: NavHostController) {
    val repo = repo()
    val scope = rememberCoroutineScope()

    var loaded by rememberSaveable { mutableStateOf(id == 0L) }
    var name by rememberSaveable { mutableStateOf("") }
    var receiptName by rememberSaveable { mutableStateOf("") }
    var stores by rememberSaveable { mutableStateOf(listOf<String>()) }
    var sizeKg by rememberSaveable { mutableStateOf("") }
    var relatedIds by rememberSaveable { mutableStateOf(listOf<Long>()) }
    var imageUrl by rememberSaveable { mutableStateOf("") }
    var storeUrl by rememberSaveable { mutableStateOf("") }
    var newStore by rememberSaveable { mutableStateOf("") }
    var showErrors by rememberSaveable { mutableStateOf(false) }

    var allFoods by remember { mutableStateOf(listOf<FoodEntity>()) }
    var usedStores by remember { mutableStateOf(listOf<String>()) }
    var picking by remember { mutableStateOf(false) }
    var confirmDelete by remember { mutableStateOf(false) }

    LaunchedEffect(id) {
        allFoods = repo.foods.allFoods().sortedWith(compareBy(czech) { it.name })
        usedStores = repo.foods.usedStores()
        if (!loaded) {
            val d = repo.foods.detail(id)
            if (d == null) { nav.popBackStack(); return@LaunchedEffect }
            name = d.food.name
            receiptName = d.food.receiptName
            stores = d.stores
            sizeKg = d.food.sizeKg?.let { formatKg(it).removeSuffix(" kg") }.orEmpty()
            relatedIds = d.related.map { it.id }
            imageUrl = d.food.imageUrl.orEmpty()
            storeUrl = d.food.storeUrl.orEmpty()
            loaded = true
        }
    }

    val input = FoodInput(name, receiptName, stores, sizeKg, relatedIds, imageUrl, storeUrl)
    val errors = if (showErrors) input.errors() else emptyMap()
    fun save() {
        if (input.errors().isNotEmpty()) { showErrors = true; return }
        scope.launch {
            repo.foods.saveFood(id, input)
            nav.popBackStack()
        }
    }

    Column(Modifier.fillMaxSize()) {
        TopAppBar(
            title = { Text(if (id == 0L) "Nová potravina" else "Upravit potravinu", maxLines = 1) },
            windowInsets = WindowInsets(0.dp),
            navigationIcon = { IconButton(onClick = { nav.popBackStack() }) { Icon(Icons.AutoMirrored.Filled.ArrowBack, "Zpět") } },
            actions = {
                if (id != 0L) IconButton(onClick = { confirmDelete = true }) { Icon(Icons.Default.Delete, "Smazat") }
                TextButton(onClick = ::save, enabled = loaded) { Text("Uložit") }
            },
        )
        if (!loaded) return@Column
        Column(
            Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(horizontal = 16.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            SectionLabel("Povinné")
            FormField(name, { name = it }, "Název potraviny *", errors["name"], placeholder = "Kukuřičné kuřecí prsní řízky")
            FormField(receiptName, { receiptName = it }, "Název na účtence *", errors["receiptName"], placeholder = "Kukuř.kuře.prs.ř.")

            Text("Obchody *", style = MaterialTheme.typography.bodyMedium)
            val offered = (defaultStores + usedStores + stores).distinctBy { it.lowercase() }
            FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                offered.forEach { s ->
                    val selected = stores.any { it.equals(s, ignoreCase = true) }
                    FilterChip(
                        selected = selected,
                        onClick = { stores = if (selected) stores.filterNot { it.equals(s, ignoreCase = true) } else stores + s },
                        label = { Text(s) },
                    )
                }
            }
            Row(verticalAlignment = Alignment.CenterVertically) {
                OutlinedTextField(
                    newStore, { newStore = it }, label = { Text("Jiný obchod") }, singleLine = true,
                    modifier = Modifier.weight(1f),
                )
                Spacer(Modifier.width(8.dp))
                OutlinedButton(
                    enabled = newStore.isNotBlank(),
                    onClick = {
                        val s = newStore.trim()
                        if (stores.none { it.equals(s, ignoreCase = true) }) stores = stores + s
                        newStore = ""
                    },
                ) { Text("Přidat") }
            }
            errors["stores"]?.let { Text(it, color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodySmall) }

            SectionLabel("Nepovinné")
            FormField(
                sizeKg, { sizeKg = it }, "Velikost (kg)", errors["sizeKg"], placeholder = "0,5",
                keyboard = KeyboardOptions(keyboardType = KeyboardType.Decimal),
            )

            Text("Příbuzné potraviny", style = MaterialTheme.typography.bodyMedium)
            val byId = allFoods.associateBy { it.id }
            FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                relatedIds.forEach { rid ->
                    InputChip(
                        selected = false,
                        onClick = { relatedIds = relatedIds - rid },
                        label = { Text(byId[rid]?.name ?: "?") },
                        trailingIcon = { Icon(Icons.Default.Close, "Odebrat") },
                    )
                }
            }
            val candidates = allFoods.filter { it.id != id && it.id !in relatedIds }
            OutlinedButton(onClick = { picking = true }, enabled = candidates.isNotEmpty()) {
                Icon(Icons.Default.Add, null)
                Spacer(Modifier.width(4.dp))
                Text(if (allFoods.none { it.id != id }) "Zatím není s čím propojit" else "Přidat příbuznou potravinu")
            }

            Row(verticalAlignment = Alignment.CenterVertically) {
                FormField(
                    imageUrl, { imageUrl = it }, "Odkaz na obrázek", errors["imageUrl"], placeholder = "https://…",
                    keyboard = KeyboardOptions(keyboardType = KeyboardType.Uri), modifier = Modifier.weight(1f),
                )
                if (imageUrl.isNotBlank() && errors["imageUrl"] == null) {
                    Spacer(Modifier.width(8.dp))
                    ProductThumb(imageUrl.trim(), Category.OSTATNI, 56.dp)
                }
            }
            FormField(
                storeUrl, { storeUrl = it }, "Odkaz na produkt v obchodě", errors["storeUrl"], placeholder = "https://www.lidl.cz/p/…",
                keyboard = KeyboardOptions(keyboardType = KeyboardType.Uri),
            )

            Button(onClick = ::save, modifier = Modifier.fillMaxWidth().padding(vertical = 16.dp)) { Text("Uložit") }
        }
    }

    if (picking) {
        SearchPickerDialog(
            title = "Příbuzná potravina",
            items = allFoods.filter { it.id != id && it.id !in relatedIds },
            label = { it.name },
            sublabel = { "Na účtence: ${it.receiptName}" },
            onDismiss = { picking = false },
            onPick = { relatedIds = relatedIds + it.id; picking = false },
        )
    }
    if (confirmDelete) {
        AlertDialog(
            onDismissRequest = { confirmDelete = false },
            title = { Text("Smazat potravinu?") },
            text = { Text("„$name“ se smaže z databáze potravin i ze seznamů příbuzných u ostatních potravin.") },
            confirmButton = {
                TextButton(onClick = {
                    confirmDelete = false
                    scope.launch { repo.foods.deleteFood(id); nav.popBackStack() }
                }) { Text("Smazat", color = MaterialTheme.colorScheme.error) }
            },
            dismissButton = { TextButton(onClick = { confirmDelete = false }) { Text("Zrušit") } },
        )
    }
}

@Composable
private fun SectionLabel(text: String) {
    Text(text, style = MaterialTheme.typography.titleSmall, color = MaterialTheme.colorScheme.primary, modifier = Modifier.padding(top = 12.dp))
}

@Composable
private fun FormField(
    value: String,
    onChange: (String) -> Unit,
    label: String,
    error: String?,
    placeholder: String? = null,
    keyboard: KeyboardOptions = KeyboardOptions.Default,
    modifier: Modifier = Modifier.fillMaxWidth(),
) {
    OutlinedTextField(
        value, onChange,
        label = { Text(label) },
        placeholder = placeholder?.let { { Text(it) } },
        isError = error != null,
        supportingText = error?.let { { Text(it) } },
        singleLine = true,
        keyboardOptions = keyboard,
        modifier = modifier,
    )
}
