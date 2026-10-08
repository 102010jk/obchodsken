package cz.obchodsken.ui

import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.Edit
import androidx.compose.material.icons.filled.Search
import androidx.compose.material3.Card
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilterChip
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.navigation.NavHostController
import cz.obchodsken.data.finalPrice
import cz.obchodsken.parser.Category
import cz.obchodsken.parser.ProductNames
import kotlinx.coroutines.launch

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ProductsScreen(nav: NavHostController) {
    val repo = repo()
    val all by repo.dao.productSummaries().collectAsState(initial = emptyList())
    var query by rememberSaveable { mutableStateOf("") }
    var cat by rememberSaveable { mutableStateOf<String?>(null) }
    val q = ProductNames.stripDiacritics(query.lowercase().trim())
    val list = all.filter {
        (cat == null || it.category == cat) &&
            (q.isEmpty() || ProductNames.stripDiacritics(it.name.lowercase()).contains(q))
    }

    Column(Modifier.fillMaxSize()) {
        val unmatched by repo.dao.unmatchedCount().collectAsState(initial = 0)
        val ctx = androidx.compose.ui.platform.LocalContext.current
        val scope = rememberCoroutineScope()
        TopAppBar(
            title = { Text("Položky (${all.size})") },
            windowInsets = WindowInsets(0.dp),
            actions = {
                if (unmatched > 0) androidx.compose.material3.TextButton(onClick = {
                    scope.launch {
                        val f = repo.exportUnmatched()
                        val uri = androidx.core.content.FileProvider.getUriForFile(ctx, ctx.packageName + ".files", f)
                        val send = android.content.Intent(android.content.Intent.ACTION_SEND).apply {
                            type = "text/plain"
                            putExtra(android.content.Intent.EXTRA_STREAM, uri)
                            addFlags(android.content.Intent.FLAG_GRANT_READ_URI_PERMISSION)
                        }
                        ctx.startActivity(android.content.Intent.createChooser(send, "Nerozpoznané produkty"))
                    }
                }) { Text("Nerozpoznané: $unmatched") }
            },
        )
        OutlinedTextField(
            query, { query = it }, leadingIcon = { Icon(Icons.Default.Search, null) },
            placeholder = { Text("Hledat produkt") }, singleLine = true,
            modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp),
        )
        val present = all.map { it.category }.toSet()
        Row(
            Modifier.horizontalScroll(rememberScrollState()).padding(horizontal = 16.dp, vertical = 8.dp),
            horizontalArrangement = Arrangement.spacedBy(6.dp),
        ) {
            FilterChip(selected = cat == null, onClick = { cat = null }, label = { Text("Vše") })
            Category.entries.filter { it.name in present }.forEach { c ->
                FilterChip(selected = cat == c.name, onClick = { cat = if (cat == c.name) null else c.name }, label = { Text("${c.emoji} ${c.label}") })
            }
        }
        if (all.isEmpty()) EmptyState("Až přidáš účtenky, uvidíš tu všechny koupené produkty, kolikrát jsi je koupil a za kolik.")
        LazyColumn(Modifier.fillMaxSize()) {
            items(list, key = { it.name }) { p ->
                Row(
                    Modifier.fillMaxWidth().clickable { nav.openProduct(p.name) }.padding(horizontal = 16.dp, vertical = 10.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Column(Modifier.weight(1f)) {
                        Text(p.name, style = MaterialTheme.typography.bodyLarge)
                        Text(
                            "${Category.of(p.category).emoji} ${p.count}× · celkem ${kc(p.spent)} · naposledy ${formatDate(p.lastAt)}",
                            style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                    Text(kc(p.lastPrice), style = MaterialTheme.typography.titleSmall)
                }
                HorizontalDivider()
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ProductDetailScreen(name: String, nav: NavHostController) {
    val repo = repo()
    val scope = rememberCoroutineScope()
    val history by repo.dao.historyByName(name).collectAsState(initial = emptyList())
    var editing by remember { mutableStateOf(false) }
    Column(Modifier.fillMaxSize()) {
        TopAppBar(
            title = { Text(name, maxLines = 1) },
            windowInsets = WindowInsets(0.dp),
            navigationIcon = { IconButton(onClick = { nav.popBackStack() }) { Icon(Icons.AutoMirrored.Filled.ArrowBack, "Zpět") } },
            actions = { if (history.isNotEmpty()) IconButton(onClick = { editing = true }) { Icon(Icons.Default.Edit, "Přejmenovat") } },
        )
        if (history.isEmpty()) return@Column
        val first = history.first()
        val perUnit = history.map { i ->
            if (i.quantity > 0) (i.finalPrice / i.quantity).toLong() else i.finalPrice
        }
        val unitLabel = if (first.unit == "kg") "/kg" else "/ks"
        LazyColumn(Modifier.fillMaxSize()) {
            item {
                Card(Modifier.fillMaxWidth().padding(16.dp)) {
                    Column(Modifier.padding(16.dp)) {
                        CategoryBadge(Category.of(first.category))
                        Spacer(Modifier.height(8.dp))
                        Text("Na účtence: " + history.map { it.rawName }.distinct().joinToString(", "), style = MaterialTheme.typography.bodySmall)
                        Spacer(Modifier.height(8.dp))
                        Text("Koupeno ${history.size}× · utraceno ${kc(history.sumOf { it.finalPrice })}", fontWeight = FontWeight.Bold)
                        Text("Cena$unitLabel: průměr ${kc(perUnit.average().toLong())}, min ${kc(perUnit.min())}, max ${kc(perUnit.max())}")
                        val discounted = history.count { it.discount > 0 }
                        if (discounted > 0) Text("Ve slevě ${discounted}×, ušetřeno ${kc(history.sumOf { it.discount })}", color = MaterialTheme.colorScheme.primary)
                    }
                }
                Text("Historie nákupů", style = MaterialTheme.typography.titleSmall, modifier = Modifier.padding(horizontal = 16.dp))
            }
            items(history.zip(perUnit), key = { it.first.id }) { (i, pu) ->
                Row(
                    Modifier.fillMaxWidth().clickable { nav.openReceipt(i.receiptId) }.padding(horizontal = 16.dp, vertical = 10.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Column(Modifier.weight(1f)) {
                        Text(formatDate(i.purchasedAt) + " · " + i.store + (i.branch?.let { " $it" } ?: ""))
                        Text(
                            formatQty(i.quantity, i.unit) + " · ${kc(pu)}$unitLabel" + if (i.discount > 0) " · sleva ${kc(i.discount)}" else "",
                            style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                    Text(kc(i.finalPrice), style = MaterialTheme.typography.titleSmall)
                }
                HorizontalDivider()
            }
        }
    }
    if (editing && history.isNotEmpty()) {
        val first = history.first()
        ItemEditDialog(
            title = "Přejmenovat produkt", rawName = first.rawName, initialName = name,
            initialCategory = Category.of(first.category), initialPrice = 0, initialDiscount = 0,
            showApplyToAll = false, showPrice = false, onDismiss = { editing = false }, onDelete = null,
            onSave = { e ->
                editing = false
                scope.launch {
                    history.map { it.rawKey }.distinct().forEach { rk ->
                        repo.dao.upsertMapping(cz.obchodsken.data.NameMappingEntity(rk, e.name, e.category.name))
                        repo.dao.renameAll(rk, e.name, e.category.name)
                    }
                    nav.popBackStack()
                    nav.openProduct(e.name)
                }
            },
        )
    }
}
