package cz.obchodsken.ui

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilledTonalButton
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.SnackbarHostState
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
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import androidx.core.content.FileProvider
import androidx.navigation.NavHostController
import cz.obchodsken.data.ImportOutcome
import cz.obchodsken.data.ReceiptWithCount
import cz.obchodsken.data.toLocalDateTime
import kotlinx.coroutines.launch
import java.io.File

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ReceiptsScreen(nav: NavHostController, snackbar: SnackbarHostState) {
    val repo = repo()
    val ctx = LocalContext.current
    val scope = rememberCoroutineScope()
    val receipts by repo.dao.receipts().collectAsState(initial = null)
    val importState by repo.importState.collectAsState()
    var processing by remember { mutableStateOf(false) }
    var photoUri by rememberSaveable { mutableStateOf<String?>(null) }

    val takePicture = rememberLauncherForActivityResult(ActivityResultContracts.TakePicture()) { ok ->
        val uri = photoUri?.let(Uri::parse)
        if (ok && uri != null) {
            scope.launch {
                processing = true
                val outcome = try { repo.importUri(uri) } catch (e: Throwable) { ImportOutcome.NotReceipt(e.message ?: "Chyba") }
                processing = false
                when (outcome) {
                    is ImportOutcome.Saved -> nav.openReceipt(outcome.id)
                    is ImportOutcome.Duplicate -> {
                        nav.openReceipt(outcome.id)
                        snackbar.showSnackbar("Tahle účtenka už je uložená.")
                    }
                    is ImportOutcome.NotReceipt -> snackbar.showSnackbar(outcome.reason)
                }
            }
        }
    }

    fun launchCamera() {
        val dir = File(ctx.cacheDir, "camera").apply { mkdirs() }
        val f = File(dir, "uctenka_${System.currentTimeMillis()}.jpg")
        val uri = FileProvider.getUriForFile(ctx, ctx.packageName + ".files", f)
        photoUri = uri.toString()
        takePicture.launch(uri)
    }

    val cameraPermission = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
        if (granted) launchCamera() else scope.launch { snackbar.showSnackbar("Bez přístupu ke kameře nejde fotit.") }
    }

    val pickFiles = rememberLauncherForActivityResult(ActivityResultContracts.OpenMultipleDocuments()) { uris ->
        uris.forEach {
            try { ctx.contentResolver.takePersistableUriPermission(it, Intent.FLAG_GRANT_READ_URI_PERMISSION) } catch (_: Exception) {}
        }
        repo.enqueue(uris)
    }
    val pickPhotos = rememberLauncherForActivityResult(ActivityResultContracts.PickMultipleVisualMedia()) { uris ->
        repo.enqueue(uris)
    }
    var showImportChoice by remember { mutableStateOf(false) }

    Column(Modifier.fillMaxSize()) {
        TopAppBar(title = { Text("Účtenky") }, windowInsets = WindowInsets(0.dp))
        Row(Modifier.padding(horizontal = 16.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Button(
                onClick = {
                    if (ContextCompat.checkSelfPermission(ctx, Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED) launchCamera()
                    else cameraPermission.launch(Manifest.permission.CAMERA)
                },
                enabled = !processing,
                modifier = Modifier.weight(1f),
            ) {
                Icon(AppIcons.Camera, null)
                Spacer(Modifier.width(8.dp))
                Text("Vyfotit")
            }
            FilledTonalButton(onClick = { showImportChoice = true }, modifier = Modifier.weight(1f)) {
                Icon(AppIcons.Gallery, null)
                Spacer(Modifier.width(8.dp))
                Text("Importovat")
            }
        }

        if (processing) {
            Row(Modifier.padding(16.dp), verticalAlignment = Alignment.CenterVertically) {
                CircularProgressIndicator(Modifier.size(24.dp))
                Spacer(Modifier.width(12.dp))
                Text("Čtu účtenku…")
            }
        }

        if (importState.total > 0) ImportCard(importState, onDismiss = repo::dismissImportState)

        val list = receipts
        when {
            list == null -> {}
            list.isEmpty() -> EmptyState(
                "Zatím žádné účtenky.\n\nVyfoť papírovou účtenku, nebo naimportuj screenshoty " +
                    "elektronických účtenek z Lidl Plus (můžeš jich vybrat i stovky najednou, " +
                    "nebo je do aplikace poslat přes Sdílet)."
            )
            else -> ReceiptList(list) { nav.openReceipt(it) }
        }
    }

    if (showImportChoice) {
        AlertDialog(
            onDismissRequest = { showImportChoice = false },
            title = { Text("Import účtenek") },
            text = {
                Text(
                    "Fotky / screenshoty účtenek se zpracují na pozadí. Duplicitní účtenky se přeskočí.\n\n" +
                        "Galerie: max. 100 najednou.\nSoubory: bez omezení (vyber třeba celou složku screenshotů)."
                )
            },
            confirmButton = {
                Button(onClick = {
                    showImportChoice = false
                    pickFiles.launch(arrayOf("image/*"))
                }) { Text("Ze souborů") }
            },
            dismissButton = {
                FilledTonalButton(onClick = {
                    showImportChoice = false
                    pickPhotos.launch(androidx.activity.result.PickVisualMediaRequest(ActivityResultContracts.PickVisualMedia.ImageOnly))
                }) { Text("Z galerie") }
            },
        )
    }
}

@Composable
private fun ImportCard(s: cz.obchodsken.data.ImportState, onDismiss: () -> Unit) {
    Card(
        Modifier.fillMaxWidth().padding(16.dp, 12.dp, 16.dp, 0.dp),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.secondaryContainer),
    ) {
        Column(Modifier.padding(12.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(
                    if (s.running) "Zpracovávám ${s.done} / ${s.total}…" else "Import dokončen",
                    fontWeight = FontWeight.Bold, modifier = Modifier.weight(1f),
                )
                if (!s.running) IconButton(onClick = onDismiss) { Icon(Icons.Default.Close, "Zavřít") }
            }
            if (s.running) {
                LinearProgressIndicator(progress = { if (s.total == 0) 0f else s.done.toFloat() / s.total }, modifier = Modifier.fillMaxWidth())
                Spacer(Modifier.height(4.dp))
            }
            Text(
                "Uloženo: ${s.saved}   Duplicity: ${s.duplicates}   Nepoznáno: ${s.failed}" +
                    if (s.withWarnings > 0) "\nK zkontrolování: ${s.withWarnings} (označené ⚠)" else "",
                style = MaterialTheme.typography.bodySmall,
            )
        }
    }
}

private val months = listOf("Leden", "Únor", "Březen", "Duben", "Květen", "Červen", "Červenec", "Srpen", "Září", "Říjen", "Listopad", "Prosinec")
fun monthName(m: Int, y: Int) = months[m - 1] + " " + y

@Composable
private fun ReceiptList(list: List<ReceiptWithCount>, onOpen: (Long) -> Unit) {
    val grouped = list.groupBy { r -> r.purchasedAt?.toLocalDateTime()?.let { monthName(it.monthValue, it.year) } ?: "Bez data" }
    LazyColumn(Modifier.fillMaxSize()) {
        grouped.forEach { (month, rs) ->
            item(key = "h$month") {
                Row(Modifier.fillMaxWidth().padding(16.dp, 16.dp, 16.dp, 4.dp)) {
                    Text(month, style = MaterialTheme.typography.titleSmall, color = MaterialTheme.colorScheme.primary, modifier = Modifier.weight(1f))
                    Text(kc(rs.sumOf { it.total }), style = MaterialTheme.typography.titleSmall, color = MaterialTheme.colorScheme.primary)
                }
            }
            items(rs, key = { it.id }) { r ->
                Row(
                    Modifier.fillMaxWidth().clickable { onOpen(r.id) }.padding(horizontal = 16.dp, vertical = 10.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Column(Modifier.weight(1f)) {
                        Text(r.store + (r.branch?.let { " · $it" } ?: ""), style = MaterialTheme.typography.bodyLarge)
                        Text("${formatDateTime(r.purchasedAt)} · ${r.itemCount} pol.", style = MaterialTheme.typography.bodySmall)
                    }
                    if (r.warning != null) Icon(Icons.Default.Warning, "Zkontrolovat", tint = MaterialTheme.colorScheme.error, modifier = Modifier.size(18.dp))
                    Spacer(Modifier.width(8.dp))
                    Text(kc(r.total), style = MaterialTheme.typography.titleMedium)
                }
                HorizontalDivider()
            }
        }
    }
}
