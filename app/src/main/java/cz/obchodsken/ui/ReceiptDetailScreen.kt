package cz.obchodsken.ui

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Column
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
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.MoreVert
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.unit.dp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import androidx.navigation.NavHostController
import coil.compose.AsyncImage
import cz.obchodsken.data.ItemEntity
import cz.obchodsken.data.finalPrice
import cz.obchodsken.parser.Category
import kotlinx.coroutines.launch
import java.io.File

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ReceiptDetailScreen(id: Long, nav: NavHostController) {
    val repo = repo()
    val scope = rememberCoroutineScope()
    val receipt by repo.dao.receiptFlow(id).collectAsState(initial = null)
    val items by repo.dao.itemsFlow(id).collectAsState(initial = emptyList())
    var editing by remember { mutableStateOf<ItemEntity?>(null) }
    var adding by remember { mutableStateOf(false) }
    var menu by remember { mutableStateOf(false) }
    var showImage by remember { mutableStateOf(false) }
    var showText by remember { mutableStateOf(false) }
    var confirmDelete by remember { mutableStateOf(false) }
    var confirmReparse by remember { mutableStateOf(false) }

    val r = receipt
    Column(Modifier.fillMaxSize()) {
        TopAppBar(
            title = { Text(r?.store ?: "Účtenka") },
            windowInsets = WindowInsets(0.dp),
            navigationIcon = { IconButton(onClick = { nav.popBackStack() }) { Icon(Icons.AutoMirrored.Filled.ArrowBack, "Zpět") } },
            actions = {
                if (r?.imagePath != null) IconButton(onClick = { showImage = true }) { Icon(AppIcons.Image, "Fotka") }
                IconButton(onClick = { menu = true }) { Icon(Icons.Default.MoreVert, "Více") }
                DropdownMenu(menu, { menu = false }) {
                    DropdownMenuItem(text = { Text("Text z OCR") }, onClick = { menu = false; showText = true })
                    DropdownMenuItem(text = { Text("Znovu zpracovat") }, onClick = { menu = false; confirmReparse = true })
                    DropdownMenuItem(
                        text = { Text("Smazat účtenku") },
                        leadingIcon = { Icon(Icons.Default.Delete, null) },
                        onClick = { menu = false; confirmDelete = true },
                    )
                }
            },
        )
        if (r == null) return@Column

        LazyColumn(Modifier.fillMaxSize()) {
            item {
                Card(Modifier.fillMaxWidth().padding(16.dp)) {
                    Column(Modifier.padding(16.dp)) {
                        r.branch?.let { Text(it, style = MaterialTheme.typography.bodyMedium) }
                        Text(formatDateTime(r.purchasedAt), style = MaterialTheme.typography.bodyMedium)
                        Spacer(Modifier.height(8.dp))
                        Row(verticalAlignment = Alignment.Bottom) {
                            Text("Celkem", modifier = Modifier.weight(1f))
                            Text(kc(r.total), style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold)
                        }
                        if (r.totalDiscount > 0) Text(
                            "Ušetřeno na slevách: ${kc(r.totalDiscount)}",
                            color = MaterialTheme.colorScheme.primary, style = MaterialTheme.typography.bodySmall,
                        )
                        r.payment?.let { Text("Platba: $it", style = MaterialTheme.typography.bodySmall) }
                    }
                }
            }
            r.warning?.let { w ->
                item {
                    Card(
                        Modifier.fillMaxWidth().padding(horizontal = 16.dp),
                        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.errorContainer),
                    ) {
                        Row(Modifier.padding(12.dp)) {
                            Icon(Icons.Default.Warning, null, tint = MaterialTheme.colorScheme.onErrorContainer)
                            Spacer(Modifier.width(8.dp))
                            Text(
                                w + "\nKlepnutím na položku ji opravíš, fotku zobrazíš ikonou nahoře.",
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onErrorContainer,
                            )
                        }
                    }
                }
            }
            items(items, key = { it.id }) { item ->
                ItemRow(item) { editing = item }
                HorizontalDivider()
            }
            item {
                Row(Modifier.fillMaxWidth().padding(16.dp)) {
                    Text("Součet položek", modifier = Modifier.weight(1f), style = MaterialTheme.typography.bodySmall)
                    Text(kc(items.sumOf { it.finalPrice }), style = MaterialTheme.typography.bodySmall)
                }
                OutlinedButton(onClick = { adding = true }, modifier = Modifier.padding(horizontal = 16.dp)) {
                    Icon(Icons.Default.Add, null)
                    Text("Přidat položku")
                }
                Spacer(Modifier.height(32.dp))
            }
        }
    }

    editing?.let { item ->
        ItemEditDialog(
            title = "Upravit položku",
            rawName = item.rawName,
            initialName = item.name,
            initialCategory = Category.of(item.category),
            initialPrice = item.price,
            initialDiscount = item.discount,
            showApplyToAll = true,
            onDismiss = { editing = null },
            onDelete = { scope.launch { repo.deleteItem(item) }; editing = null },
            onSave = { e ->
                scope.launch {
                    repo.updateItem(
                        item.copy(name = e.name, category = e.category.name, price = e.price, discount = e.discount),
                        e.applyToAll,
                    )
                }
                editing = null
            },
        )
    }
    if (adding) {
        ItemEditDialog(
            title = "Nová položka", rawName = null, initialName = "", initialCategory = Category.OSTATNI,
            initialPrice = 0, initialDiscount = 0, showApplyToAll = false,
            onDismiss = { adding = false }, onDelete = null,
            onSave = { e -> scope.launch { repo.addItem(id, e.name, e.price - e.discount, e.category) }; adding = false },
        )
    }
    if (confirmDelete) {
        AlertDialog(
            onDismissRequest = { confirmDelete = false },
            title = { Text("Smazat účtenku?") },
            text = { Text("Účtenka i všechny její položky budou smazány.") },
            confirmButton = {
                TextButton(onClick = {
                    confirmDelete = false
                    scope.launch { repo.deleteReceipt(id); nav.popBackStack() }
                }) { Text("Smazat") }
            },
            dismissButton = { TextButton(onClick = { confirmDelete = false }) { Text("Zrušit") } },
        )
    }
    if (confirmReparse) {
        AlertDialog(
            onDismissRequest = { confirmReparse = false },
            title = { Text("Znovu zpracovat?") },
            text = { Text("Položky se znovu načtou z textu účtenky. Ruční úpravy u této účtenky se ztratí (naučené názvy zůstanou).") },
            confirmButton = {
                TextButton(onClick = { confirmReparse = false; scope.launch { repo.reparse(id) } }) { Text("Zpracovat") }
            },
            dismissButton = { TextButton(onClick = { confirmReparse = false }) { Text("Zrušit") } },
        )
    }
    if (showText && r != null) {
        AlertDialog(
            onDismissRequest = { showText = false },
            title = { Text("Text z OCR") },
            text = {
                Text(
                    r.ocrText, fontFamily = FontFamily.Monospace, style = MaterialTheme.typography.bodySmall,
                    modifier = Modifier.verticalScroll(rememberScrollState()),
                )
            },
            confirmButton = { TextButton(onClick = { showText = false }) { Text("Zavřít") } },
        )
    }
    if (showImage && r?.imagePath != null) {
        Dialog(onDismissRequest = { showImage = false }, properties = DialogProperties(usePlatformDefaultWidth = false)) {
            Card(Modifier.fillMaxSize().padding(8.dp)) {
                Column {
                    TextButton(onClick = { showImage = false }) { Text("Zavřít") }
                    Column(Modifier.verticalScroll(rememberScrollState())) {
                        AsyncImage(
                            model = File(r.imagePath), contentDescription = "Účtenka",
                            contentScale = ContentScale.FillWidth, modifier = Modifier.fillMaxWidth(),
                        )
                    }
                }
            }
        }
    }
}

@Composable
private fun ItemRow(item: ItemEntity, onClick: () -> Unit) {
    Row(
        Modifier.fillMaxWidth().clickable(onClick = onClick).padding(horizontal = 16.dp, vertical = 10.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Column(Modifier.weight(1f)) {
            Text(item.name, style = MaterialTheme.typography.bodyLarge)
            val details = buildList {
                if (item.rawName != item.name) add(item.rawName)
                if (item.quantity != 1.0 || item.unit == "kg") {
                    add(formatQty(item.quantity, item.unit) + (item.unitPrice?.let { " × " + kc(it) + "/" + item.unit } ?: ""))
                }
                item.discountLabel?.let { if (item.discount > 0) add("$it −${kc(item.discount)}") }
            }
            if (details.isNotEmpty()) Text(details.joinToString(" · "), style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            Spacer(Modifier.height(2.dp))
            CategoryBadge(Category.of(item.category))
        }
        Column(horizontalAlignment = Alignment.End) {
            Text(kc(item.finalPrice), style = MaterialTheme.typography.titleMedium)
            if (item.discount > 0) Text(
                kc(item.price), style = MaterialTheme.typography.bodySmall,
                textDecoration = TextDecoration.LineThrough, color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}
