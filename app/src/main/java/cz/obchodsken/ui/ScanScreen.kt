package cz.obchodsken.ui

import android.Manifest
import android.content.pm.PackageManager
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.annotation.OptIn
import androidx.camera.core.CameraSelector
import androidx.camera.core.ExperimentalGetImage
import androidx.camera.core.ImageAnalysis
import androidx.camera.core.Preview
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.camera.view.PreviewView
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
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
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilledTonalButton
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.core.content.ContextCompat
import androidx.lifecycle.compose.LocalLifecycleOwner
import androidx.navigation.NavHostController
import coil.compose.AsyncImage
import com.google.mlkit.vision.barcode.BarcodeScannerOptions
import com.google.mlkit.vision.barcode.BarcodeScanning
import com.google.mlkit.vision.barcode.common.Barcode
import com.google.mlkit.vision.common.InputImage
import cz.obchodsken.data.Repository
import cz.obchodsken.data.finalPrice
import cz.obchodsken.parser.Category
import kotlinx.coroutines.launch
import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicBoolean

@kotlin.OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ScanScreen(nav: NavHostController) {
    val ctx = LocalContext.current
    val repo = repo()
    var hasPermission by remember {
        mutableStateOf(ContextCompat.checkSelfPermission(ctx, Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED)
    }
    val permLauncher = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { hasPermission = it }
    LaunchedEffect(Unit) { if (!hasPermission) permLauncher.launch(Manifest.permission.CAMERA) }

    var code by rememberSaveable { mutableStateOf<String?>(null) }
    var result by remember { mutableStateOf<Repository.BarcodeResult?>(null) }
    var loading by remember { mutableStateOf(false) }
    var manual by remember { mutableStateOf("") }
    var refresh by remember { mutableStateOf(0) }

    LaunchedEffect(code, refresh) {
        val c = code ?: return@LaunchedEffect
        loading = true
        result = try { repo.lookupBarcode(c) } catch (e: Exception) { null }
        loading = false
    }

    Column(Modifier.fillMaxSize()) {
        TopAppBar(title = { Text("Skenovat čárový kód") }, windowInsets = WindowInsets(0.dp))
        val c = code
        if (c == null) {
            Box(Modifier.fillMaxWidth().weight(1f).padding(16.dp)) {
                if (hasPermission) {
                    BarcodeCamera(onCode = { code = it })
                    Box(
                        Modifier.align(Alignment.Center).size(260.dp, 140.dp)
                            .border(3.dp, Color(0xFFFFF000), RoundedCornerShape(12.dp)),
                    )
                    Text(
                        "Namiř na čárový kód produktu",
                        color = Color.White,
                        modifier = Modifier.align(Alignment.BottomCenter).padding(12.dp)
                            .background(Color(0x99000000), RoundedCornerShape(8.dp)).padding(8.dp),
                    )
                } else {
                    Column(Modifier.align(Alignment.Center), horizontalAlignment = Alignment.CenterHorizontally) {
                        Text("Pro skenování je potřeba přístup ke kameře.")
                        Button(onClick = { permLauncher.launch(Manifest.permission.CAMERA) }) { Text("Povolit kameru") }
                    }
                }
            }
            Row(Modifier.padding(16.dp), verticalAlignment = Alignment.CenterVertically) {
                OutlinedTextField(
                    manual, { manual = it.filter(Char::isDigit) }, label = { Text("…nebo zadej číslo kódu") },
                    singleLine = true, keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                    modifier = Modifier.weight(1f),
                )
                Spacer(Modifier.width(8.dp))
                Button(enabled = manual.length >= 6, onClick = { code = manual; manual = "" }) { Text("Hledat") }
            }
        } else {
            Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp)) {
                Text("Kód: $c", style = MaterialTheme.typography.bodySmall)
                Spacer(Modifier.height(8.dp))
                when {
                    loading -> Row(verticalAlignment = Alignment.CenterVertically) {
                        CircularProgressIndicator(Modifier.size(24.dp))
                        Spacer(Modifier.width(12.dp))
                        Text("Hledám produkt…")
                    }
                    else -> ProductResult(c, result, repo, nav, onChanged = { refresh++ })
                }
                Spacer(Modifier.height(16.dp))
                Button(onClick = { code = null; result = null }, modifier = Modifier.fillMaxWidth()) {
                    Text("Skenovat další")
                }
            }
        }
    }
}

@Composable
private fun ProductResult(
    code: String,
    res: Repository.BarcodeResult?,
    repo: Repository,
    nav: NavHostController,
    onChanged: () -> Unit,
) {
    val scope = rememberCoroutineScope()
    var linking by remember { mutableStateOf(false) }
    var naming by remember { mutableStateOf(false) }
    val p = res?.product

    if (p == null) {
        Card(Modifier.fillMaxWidth()) {
            Column(Modifier.padding(16.dp)) {
                Text("Produkt jsem v databázi nenašel", style = MaterialTheme.typography.titleMedium)
                if (res?.offline == true) Text("(nejsi připojený k internetu?)", style = MaterialTheme.typography.bodySmall)
                Spacer(Modifier.height(8.dp))
                Text("Můžeš ho pojmenovat sám a propojit s položkou z účtenek – příště ho aplikace pozná i offline.")
                Spacer(Modifier.height(8.dp))
                Button(onClick = { naming = true }) { Text("Pojmenovat produkt") }
            }
        }
    } else {
        Card(Modifier.fillMaxWidth()) {
            Column(Modifier.padding(16.dp)) {
                Row {
                    if (p.imageUrl != null) {
                        AsyncImage(
                            model = p.imageUrl, contentDescription = null, contentScale = ContentScale.Fit,
                            modifier = Modifier.size(96.dp),
                        )
                        Spacer(Modifier.width(12.dp))
                    }
                    Column(Modifier.weight(1f)) {
                        Text(p.name, style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
                        p.brand?.let { Text(it, style = MaterialTheme.typography.bodyMedium) }
                        p.quantity?.let { Text(it, style = MaterialTheme.typography.bodySmall) }
                        Spacer(Modifier.height(4.dp))
                        CategoryBadge(Category.of(p.category))
                    }
                }
                p.nutriscore?.let {
                    Spacer(Modifier.height(8.dp))
                    Text("Nutri-Score: ${it.uppercase()}", fontWeight = FontWeight.Bold, color = nutriColor(it))
                }
                p.ingredients?.let {
                    Spacer(Modifier.height(8.dp))
                    Text("Složení: " + it.take(400) + if (it.length > 400) "…" else "", style = MaterialTheme.typography.bodySmall)
                }
                Spacer(Modifier.height(4.dp))
                Text("Zdroj: ${p.source}", style = MaterialTheme.typography.labelSmall)
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    TextButton(onClick = { naming = true }) { Text("Přejmenovat") }
                }
            }
        }

        Spacer(Modifier.height(12.dp))
        Card(Modifier.fillMaxWidth()) {
            Column(Modifier.padding(16.dp)) {
                Text("Na tvých účtenkách", style = MaterialTheme.typography.titleMedium)
                if (p.linkedRawKey == null) {
                    if (res?.suggestions.orEmpty().isNotEmpty()) {
                        Text("Je to některá z těchto položek?", style = MaterialTheme.typography.bodySmall)
                        res?.suggestions.orEmpty().forEach { s ->
                            FilledTonalButton(
                                onClick = { scope.launch { repo.linkProduct(code, s.rawKey); onChanged() } },
                                modifier = Modifier.fillMaxWidth(),
                            ) { Text("${s.name}  (${s.count}×)") }
                        }
                    } else {
                        Text("Zatím nepropojeno s žádnou položkou.", style = MaterialTheme.typography.bodySmall)
                    }
                    OutlinedButton(onClick = { linking = true }) { Text("Vybrat položku z účtenek") }
                } else {
                    val h = res?.history.orEmpty()
                    if (h.isEmpty()) {
                        Text("Propojeno, ale zatím žádný nákup.", style = MaterialTheme.typography.bodySmall)
                    } else {
                        val avg = h.sumOf { it.finalPrice } / h.size
                        Text("Koupeno ${h.size}×, průměrně ${kc(avg)}, naposledy ${formatDate(h.first().purchasedAt)}")
                        Text("Na účtence jako: ${h.first().rawName}", style = MaterialTheme.typography.bodySmall)
                        Spacer(Modifier.height(8.dp))
                        h.take(10).forEach { i ->
                            Row(Modifier.fillMaxWidth().padding(vertical = 4.dp)) {
                                Text(formatDate(i.purchasedAt) + " · " + (i.branch ?: i.store), modifier = Modifier.weight(1f), style = MaterialTheme.typography.bodySmall)
                                Text(kc(i.finalPrice), style = MaterialTheme.typography.bodySmall)
                            }
                            HorizontalDivider()
                        }
                        TextButton(onClick = { nav.openProduct(h.first().name) }) { Text("Celá historie cen") }
                    }
                    TextButton(onClick = { scope.launch { repo.linkProduct(code, null); onChanged() } }) { Text("Zrušit propojení") }
                }
            }
        }
    }

    if (linking) {
        var names by remember { mutableStateOf<List<cz.obchodsken.data.RawNameCount>>(emptyList()) }
        LaunchedEffect(Unit) { names = repo.rawNames() }
        SearchPickerDialog(
            title = "Která položka to je?",
            items = names,
            label = { it.name },
            sublabel = { "${it.rawName} · ${it.count}×" },
            onDismiss = { linking = false },
            onPick = { picked ->
                linking = false
                scope.launch {
                    if (p == null) repo.saveManualProduct(code, picked.name, Category.OSTATNI, picked.rawKey)
                    else repo.linkProduct(code, picked.rawKey)
                    onChanged()
                }
            },
        )
    }
    if (naming) {
        ItemEditDialog(
            title = "Název produktu", rawName = null, initialName = p?.name ?: "",
            initialCategory = Category.of(p?.category), initialPrice = 0, initialDiscount = 0,
            showApplyToAll = false, showPrice = false, onDismiss = { naming = false }, onDelete = null,
            onSave = { e ->
                naming = false
                scope.launch {
                    repo.saveManualProduct(code, e.name, e.category, null)
                    onChanged()
                }
            },
        )
    }
}

private fun nutriColor(g: String) = when (g.lowercase()) {
    "a" -> Color(0xFF038141); "b" -> Color(0xFF85BB2F); "c" -> Color(0xFFE6A800)
    "d" -> Color(0xFFEE8100); else -> Color(0xFFE63E11)
}

@OptIn(ExperimentalGetImage::class)
@Composable
private fun BarcodeCamera(onCode: (String) -> Unit) {
    val ctx = LocalContext.current
    val owner = LocalLifecycleOwner.current
    val executor = remember { Executors.newSingleThreadExecutor() }
    val found = remember { AtomicBoolean(false) }
    val scanner = remember {
        BarcodeScanning.getClient(
            BarcodeScannerOptions.Builder().setBarcodeFormats(
                Barcode.FORMAT_EAN_13, Barcode.FORMAT_EAN_8, Barcode.FORMAT_UPC_A, Barcode.FORMAT_UPC_E,
                Barcode.FORMAT_CODE_128, Barcode.FORMAT_CODE_39, Barcode.FORMAT_ITF, Barcode.FORMAT_QR_CODE,
            ).build()
        )
    }
    val providerFuture = remember { ProcessCameraProvider.getInstance(ctx) }
    DisposableEffect(Unit) {
        onDispose {
            try { providerFuture.get().unbindAll() } catch (_: Exception) {}
            executor.shutdown()
            scanner.close()
        }
    }
    AndroidView(
        modifier = Modifier.fillMaxSize(),
        factory = { c ->
            val pv = PreviewView(c)
            providerFuture.addListener({
                val provider = providerFuture.get()
                val preview = Preview.Builder().build().also { it.setSurfaceProvider(pv.surfaceProvider) }
                val analysis = ImageAnalysis.Builder()
                    .setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST)
                    .build()
                analysis.setAnalyzer(executor) { proxy ->
                    val media = proxy.image
                    if (media == null || found.get()) {
                        proxy.close()
                        return@setAnalyzer
                    }
                    scanner.process(InputImage.fromMediaImage(media, proxy.imageInfo.rotationDegrees))
                        .addOnSuccessListener { codes ->
                            val v = codes.firstNotNullOfOrNull { it.rawValue?.takeIf { s -> s.isNotBlank() } }
                            if (v != null && found.compareAndSet(false, true)) {
                                ContextCompat.getMainExecutor(c).execute { onCode(v) }
                            }
                        }
                        .addOnCompleteListener { proxy.close() }
                }
                try {
                    provider.unbindAll()
                    provider.bindToLifecycle(owner, CameraSelector.DEFAULT_BACK_CAMERA, preview, analysis)
                } catch (_: Exception) {
                }
            }, ContextCompat.getMainExecutor(c))
            pv
        },
    )
}
