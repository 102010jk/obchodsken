package cz.obchodsken.ui

import android.content.Intent
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Share
import androidx.compose.material3.Card
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.core.content.FileProvider
import cz.obchodsken.data.toEpochMillis
import cz.obchodsken.parser.Category
import kotlinx.coroutines.launch
import java.time.LocalDate

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun StatsScreen(snackbar: SnackbarHostState) {
    val repo = repo()
    val ctx = LocalContext.current
    val scope = rememberCoroutineScope()
    // 0 = tento měsíc, 1 = posledních 12 měsíců, 2 = vše
    var range by rememberSaveable { mutableIntStateOf(0) }
    val from: Long? = remember(range) {
        val today = LocalDate.now()
        when (range) {
            0 -> today.withDayOfMonth(1).atStartOfDay().toEpochMillis()
            1 -> today.minusMonths(12).atStartOfDay().toEpochMillis()
            else -> null
        }
    }
    val total by repo.dao.totalSpent(from).collectAsState(initial = 0L)
    val saved by repo.dao.totalSaved(from).collectAsState(initial = 0L)
    val cats by repo.dao.categorySums(from).collectAsState(initial = emptyList())
    val months by repo.dao.monthSums().collectAsState(initial = emptyList())

    Column(Modifier.fillMaxSize()) {
        TopAppBar(
            title = { Text("Přehled útrat") },
            windowInsets = WindowInsets(0.dp),
            actions = {
                IconButton(onClick = {
                    scope.launch {
                        val f = repo.exportCsv()
                        val uri = FileProvider.getUriForFile(ctx, ctx.packageName + ".files", f)
                        val send = Intent(Intent.ACTION_SEND).apply {
                            type = "text/csv"
                            putExtra(Intent.EXTRA_STREAM, uri)
                            addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
                        }
                        try {
                            ctx.startActivity(Intent.createChooser(send, "Export položek (CSV)"))
                        } catch (e: Exception) {
                            snackbar.showSnackbar("Export se nepovedl: ${e.message}")
                        }
                    }
                }) { Icon(Icons.Default.Share, "Export CSV") }
            },
        )
        Column(Modifier.verticalScroll(rememberScrollState()).padding(16.dp)) {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                listOf("Tento měsíc", "12 měsíců", "Vše").forEachIndexed { i, l ->
                    FilterChip(selected = range == i, onClick = { range = i }, label = { Text(l) })
                }
            }
            Spacer(Modifier.height(8.dp))
            Card(Modifier.fillMaxWidth()) {
                Column(Modifier.padding(16.dp)) {
                    Text("Utraceno", style = MaterialTheme.typography.bodyMedium)
                    Text(kc(total), style = MaterialTheme.typography.headlineMedium, fontWeight = FontWeight.Bold)
                    if (saved > 0) Text("Na slevách ušetřeno ${kc(saved)}", color = MaterialTheme.colorScheme.primary)
                }
            }

            Spacer(Modifier.height(16.dp))
            Text("Podle kategorií", style = MaterialTheme.typography.titleMedium)
            Spacer(Modifier.height(8.dp))
            val maxCat = cats.maxOfOrNull { it.spent }?.coerceAtLeast(1) ?: 1
            if (cats.isEmpty()) Text("Zatím žádná data.", style = MaterialTheme.typography.bodySmall)
            cats.forEach { c ->
                val cat = Category.of(c.category)
                Column(Modifier.padding(vertical = 4.dp)) {
                    Row {
                        Text("${cat.emoji} ${cat.label}", modifier = Modifier.weight(1f))
                        Text(kc(c.spent), fontWeight = FontWeight.Bold)
                    }
                    Bar(c.spent.toFloat() / maxCat)
                }
            }

            Spacer(Modifier.height(16.dp))
            Text("Po měsících", style = MaterialTheme.typography.titleMedium)
            Spacer(Modifier.height(8.dp))
            val maxMonth = months.maxOfOrNull { it.spent }?.coerceAtLeast(1) ?: 1
            months.forEach { m ->
                val (y, mo) = m.month.split("-").map { it.toInt() }
                Column(Modifier.padding(vertical = 4.dp)) {
                    Row {
                        Text(monthName(mo, y), modifier = Modifier.weight(1f))
                        Text("${m.receipts} nákupů · ", style = MaterialTheme.typography.bodySmall, modifier = Modifier.align(Alignment.CenterVertically))
                        Text(kc(m.spent), fontWeight = FontWeight.Bold)
                    }
                    Bar(m.spent.toFloat() / maxMonth)
                }
            }
        }
    }
}

@Composable
private fun Bar(fraction: Float) {
    Box(
        Modifier.fillMaxWidth().height(8.dp)
            .background(MaterialTheme.colorScheme.surfaceVariant, RoundedCornerShape(4.dp)),
    ) {
        Box(
            Modifier.fillMaxHeight().fillMaxWidth(fraction.coerceIn(0.01f, 1f))
                .background(MaterialTheme.colorScheme.primary, RoundedCornerShape(4.dp)),
        )
    }
}
