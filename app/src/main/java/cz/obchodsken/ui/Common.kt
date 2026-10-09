package cz.obchodsken.ui

import android.os.Build
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.background
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowDropDown
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Checkbox
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.dynamicDarkColorScheme
import androidx.compose.material3.dynamicLightColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.graphics.vector.addPathNodes
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import cz.obchodsken.data.toLocalDateTime
import cz.obchodsken.parser.Category
import cz.obchodsken.parser.Money
import java.time.format.DateTimeFormatter

// ------------------------------------------------------------------ téma

private val LightColors = lightColorScheme(
    primary = Color(0xFF0050AA), onPrimary = Color.White,
    primaryContainer = Color(0xFFD6E3FF), onPrimaryContainer = Color(0xFF001B3E),
    secondary = Color(0xFF6B5E00), secondaryContainer = Color(0xFFFFF000), onSecondaryContainer = Color(0xFF201C00),
)
private val DarkColors = darkColorScheme(
    primary = Color(0xFFA9C7FF), onPrimary = Color(0xFF003064),
    secondary = Color(0xFFDDC800), secondaryContainer = Color(0xFF524700),
)

@Composable
fun ObchodskenTheme(content: @Composable () -> Unit) {
    val dark = isSystemInDarkTheme()
    val ctx = LocalContext.current
    val colors = when {
        Build.VERSION.SDK_INT >= Build.VERSION_CODES.S -> if (dark) dynamicDarkColorScheme(ctx) else dynamicLightColorScheme(ctx)
        dark -> DarkColors
        else -> LightColors
    }
    MaterialTheme(colorScheme = colors, content = content)
}

// ------------------------------------------------------------------ ikony (ty nejsou v material-icons-core)

private fun icon(name: String, path: String): ImageVector =
    ImageVector.Builder(name, 24.dp, 24.dp, 24f, 24f)
        .addPath(addPathNodes(path), fill = SolidColor(Color.Black))
        .build()

object AppIcons {
    val Camera = icon(
        "camera",
        "M12,12m-3.2,0a3.2,3.2 0,1 1,6.4 0a3.2,3.2 0,1 1,-6.4 0M9,2L7.17,4H4c-1.1,0 -2,0.9 -2,2v12c0,1.1 0.9,2 2,2h16c1.1,0 2,-0.9 2,-2V6c0,-1.1 -0.9,-2 -2,-2h-3.17L15,2H9zM12,17c-2.76,0 -5,-2.24 -5,-5s2.24,-5 5,-5 5,2.24 5,5 -2.24,5 -5,5z",
    )
    val Gallery = icon(
        "gallery",
        "M22,16V4c0,-1.1 -0.9,-2 -2,-2H8c-1.1,0 -2,0.9 -2,2v12c0,1.1 0.9,2 2,2h12c1.1,0 2,-0.9 2,-2zM11,12l2.03,2.71L16,11l4,5H8l3,-4zM2,6v14c0,1.1 0.9,2 2,2h14v-2H4V6H2z",
    )
    val Barcode = icon("barcode", "M2,4h2v16H2zM5,4h1v16H5zM7,4h2v16H7zM10,4h1v16h-1zM13,4h2v16h-2zM16,4h1v16h-1zM18,4h1v16h-1zM20,4h2v16h-2z")
    val Food = icon(
        "food",
        "M11,9H9V2H7v7H5V2H3v7c0,2.12 1.66,3.84 3.75,3.97V22h2.5v-9.03C11.34,12.84 13,11.12 13,9V2h-2V9zM16,6v8h2.5v8H21V2C18.24,2 16,4.24 16,6z",
    )
    val Chart = icon("chart", "M5,9.2h3V19H5zM10.6,5h2.8v14h-2.8zM16.2,13H19v6h-2.8z")
    val Receipt = icon(
        "receipt",
        "M18,17H6v-2h12v2zM18,13H6v-2h12v2zM18,9H6V7h12v2zM3,22l1.5,-1.5L6,22l1.5,-1.5L9,22l1.5,-1.5L12,22l1.5,-1.5L15,22l1.5,-1.5L18,22l1.5,-1.5L21,22V2l-1.5,1.5L18,2l-1.5,1.5L15,2l-1.5,1.5L12,2l-1.5,1.5L9,2 7.5,3.5 6,2 4.5,3.5 3,2v20z",
    )
    val Image = icon(
        "image",
        "M21,19V5c0,-1.1 -0.9,-2 -2,-2H5c-1.1,0 -2,0.9 -2,2v14c0,1.1 0.9,2 2,2h14c1.1,0 2,-0.9 2,-2zM8.5,13.5l2.5,3.01L14.5,12l4.5,6H5l3.5,-4.5z",
    )
}

// ------------------------------------------------------------------ formátování

private val dateFmt = DateTimeFormatter.ofPattern("d. M. yyyy")
private val dateTimeFmt = DateTimeFormatter.ofPattern("d. M. yyyy HH:mm")

fun formatDate(millis: Long?): String = millis?.let { dateFmt.format(it.toLocalDateTime()) } ?: "bez data"
fun formatDateTime(millis: Long?): String = millis?.let { dateTimeFmt.format(it.toLocalDateTime()) } ?: "bez data"
fun kc(h: Long): String = Money.format(h)

fun formatQty(q: Double, unit: String): String =
    if (unit == "kg") String.format("%.3f kg", q).replace('.', ',')
    else if (q == Math.floor(q)) "${q.toLong()} ks" else "$q $unit"

/** "89,90" / "89.9" / "89" -> haléře */
fun parseUserPrice(s: String): Long? {
    val t = s.trim().replace(" ", "").replace("Kč", "").replace('.', ',')
    if (t.isEmpty()) return null
    val parts = t.split(',')
    return try {
        val whole = parts[0].ifEmpty { "0" }.toLong()
        val frac = parts.getOrNull(1)?.padEnd(2, '0')?.take(2)?.toLong() ?: 0
        val sign = if (whole < 0 || t.startsWith("-")) -1 else 1
        sign * (kotlin.math.abs(whole) * 100 + frac)
    } catch (e: NumberFormatException) {
        null
    }
}

// ------------------------------------------------------------------ společné komponenty

@Composable
fun CategoryBadge(category: Category, modifier: Modifier = Modifier) {
    Surface(
        shape = RoundedCornerShape(50),
        color = MaterialTheme.colorScheme.surfaceVariant,
        modifier = modifier,
    ) {
        Text(
            "${category.emoji} ${category.label}",
            style = MaterialTheme.typography.labelSmall,
            modifier = Modifier.padding(horizontal = 8.dp, vertical = 2.dp),
        )
    }
}

@Composable
fun CategoryPicker(value: Category, onChange: (Category) -> Unit) {
    var open by remember { mutableStateOf(false) }
    Box {
        OutlinedButton(onClick = { open = true }, modifier = Modifier.fillMaxWidth()) {
            Text("${value.emoji} ${value.label}", modifier = Modifier.weight(1f))
            Icon(Icons.Default.ArrowDropDown, null)
        }
        DropdownMenu(expanded = open, onDismissRequest = { open = false }) {
            Category.entries.forEach { c ->
                DropdownMenuItem(text = { Text("${c.emoji} ${c.label}") }, onClick = { onChange(c); open = false })
            }
        }
    }
}

data class ItemEdit(val name: String, val category: Category, val price: Long, val discount: Long, val applyToAll: Boolean)

@Composable
fun ItemEditDialog(
    title: String,
    rawName: String?,
    initialName: String,
    initialCategory: Category,
    initialPrice: Long,
    initialDiscount: Long,
    showApplyToAll: Boolean,
    showPrice: Boolean = true,
    onDismiss: () -> Unit,
    onDelete: (() -> Unit)?,
    onSave: (ItemEdit) -> Unit,
) {
    var name by remember { mutableStateOf(initialName) }
    var cat by remember { mutableStateOf(initialCategory) }
    var price by remember { mutableStateOf(if (initialPrice != 0L) Money.format(initialPrice, false).replace(" ", "") else "") }
    var discount by remember { mutableStateOf(if (initialDiscount != 0L) Money.format(initialDiscount, false).replace(" ", "") else "") }
    var all by remember { mutableStateOf(true) }
    val priceVal = if (showPrice) parseUserPrice(price) else 0L
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(title) },
        text = {
            Column {
                if (rawName != null) {
                    Text("Na účtence: $rawName", style = MaterialTheme.typography.bodySmall)
                    Spacer(Modifier.height(8.dp))
                }
                OutlinedTextField(name, { name = it }, label = { Text("Název") }, singleLine = true, modifier = Modifier.fillMaxWidth())
                Spacer(Modifier.height(8.dp))
                CategoryPicker(cat) { cat = it }
                if (showPrice) Row(Modifier.padding(top = 8.dp)) {
                    OutlinedTextField(
                        price, { price = it }, label = { Text("Cena") }, singleLine = true,
                        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
                        isError = priceVal == null, modifier = Modifier.weight(1f),
                    )
                    Spacer(Modifier.width(8.dp))
                    OutlinedTextField(
                        discount, { discount = it }, label = { Text("Sleva") }, singleLine = true,
                        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
                        modifier = Modifier.weight(1f),
                    )
                }
                if (showApplyToAll) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Checkbox(all, { all = it })
                        Text("Zapamatovat a použít u všech účtenek", style = MaterialTheme.typography.bodySmall)
                    }
                }
                if (onDelete != null) {
                    TextButton(onClick = onDelete) { Text("Smazat položku", color = MaterialTheme.colorScheme.error) }
                }
            }
        },
        confirmButton = {
            TextButton(
                enabled = name.isNotBlank() && priceVal != null,
                onClick = {
                    onSave(ItemEdit(name.trim(), cat, priceVal ?: 0, kotlin.math.abs(parseUserPrice(discount) ?: 0), all && showApplyToAll))
                },
            ) { Text("Uložit") }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Zrušit") } },
    )
}

/** Fotka produktu, nebo aspoň ikona kategorie. */
@Composable
fun ProductThumb(imageUrl: String?, category: Category, size: androidx.compose.ui.unit.Dp = 48.dp) {
    Surface(
        shape = RoundedCornerShape(8.dp),
        color = MaterialTheme.colorScheme.surfaceVariant,
        modifier = Modifier.size(size),
    ) {
        Box(contentAlignment = Alignment.Center) {
            Text(category.emoji, style = MaterialTheme.typography.titleLarge)
            if (imageUrl != null) {
                coil.compose.AsyncImage(
                    model = imageUrl, contentDescription = null,
                    contentScale = androidx.compose.ui.layout.ContentScale.Crop,
                    modifier = Modifier.size(size).background(Color.White),
                )
            }
        }
    }
}

@Composable
fun EmptyState(text: String, modifier: Modifier = Modifier) {
    Box(modifier.fillMaxWidth().padding(32.dp), contentAlignment = Alignment.Center) {
        Text(text, style = MaterialTheme.typography.bodyLarge, color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
}

/** Jednoduchý výběr ze seznamu s vyhledáváním. */
@Composable
fun <T> SearchPickerDialog(
    title: String,
    items: List<T>,
    label: (T) -> String,
    sublabel: (T) -> String?,
    header: String? = null,
    onDismiss: () -> Unit,
    onPick: (T) -> Unit,
) {
    var q by remember { mutableStateOf("") }
    val norm = cz.obchodsken.parser.ProductNames.stripDiacritics(q.lowercase())
    val filtered = items.filter {
        norm.isBlank() || cz.obchodsken.parser.ProductNames.stripDiacritics((label(it) + " " + (sublabel(it) ?: "")).lowercase()).contains(norm)
    }.take(100)
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(title) },
        text = {
            Column {
                if (header != null) Text(header, style = MaterialTheme.typography.bodySmall)
                OutlinedTextField(q, { q = it }, label = { Text("Hledat") }, singleLine = true, modifier = Modifier.fillMaxWidth())
                LazyColumn(Modifier.height(320.dp)) {
                    items(filtered) { item ->
                        TextButton(onClick = { onPick(item) }, modifier = Modifier.fillMaxWidth()) {
                            Column(Modifier.fillMaxWidth()) {
                                Text(label(item))
                                sublabel(item)?.let { Text(it, style = MaterialTheme.typography.bodySmall) }
                            }
                        }
                    }
                }
            }
        },
        confirmButton = { TextButton(onClick = onDismiss) { Text("Zavřít") } },
    )
}
