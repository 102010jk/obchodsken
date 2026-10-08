package cz.obchodsken.ocr

import android.content.Context
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Matrix
import android.net.Uri
import androidx.exifinterface.media.ExifInterface
import com.google.android.gms.tasks.Task
import com.google.mlkit.vision.common.InputImage
import com.google.mlkit.vision.text.TextRecognition
import com.google.mlkit.vision.text.latin.TextRecognizerOptions
import cz.obchodsken.parser.OcrLine
import cz.obchodsken.parser.ReceiptParser
import cz.obchodsken.parser.RowBuilder
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException
import java.io.InputStream
import kotlin.math.atan2

suspend fun <T> Task<T>.await(): T = suspendCancellableCoroutine { cont ->
    addOnSuccessListener { cont.resume(it) }
    addOnFailureListener { cont.resumeWithException(it) }
    addOnCanceledListener { cont.cancel() }
}

data class OcrResult(val rows: List<String>, val bitmap: Bitmap)

/** Rozpoznání textu účtenky na zařízení (ML Kit, offline). */
class ReceiptOcr {
    private val recognizer = TextRecognition.getClient(TextRecognizerOptions.DEFAULT_OPTIONS)

    suspend fun recognize(source: Bitmap): OcrResult {
        var best = OcrResult(recognizeRows(source), source)
        var bestScore = ReceiptParser.score(best.rows)
        // Účtenka vyfocená bokem / vzhůru nohama: zkusíme otočit a vezmeme nejlepší výsledek.
        if (bestScore < 12) {
            for (deg in listOf(90f, 270f, 180f)) {
                val rotated = rotate(source, deg)
                val rows = recognizeRows(rotated)
                val sc = ReceiptParser.score(rows)
                if (sc > bestScore) {
                    if (best.bitmap !== source) best.bitmap.recycle()
                    best = OcrResult(rows, rotated)
                    bestScore = sc
                } else {
                    rotated.recycle()
                }
                if (bestScore >= 12) break
            }
        }
        return best
    }

    private suspend fun recognizeRows(bitmap: Bitmap): List<String> =
        RowBuilder.buildRows(recognizeLines(bitmap))

    /** Dlouhé screenshoty (Lidl Plus) se rozřežou na překrývající se díly, ať je text dost velký. */
    private suspend fun recognizeLines(bitmap: Bitmap): List<OcrLine> {
        val w = bitmap.width
        val h = bitmap.height
        if (h <= w * 2 || h <= 2600) return recognizeTile(bitmap, 0)

        val tileH = (w * 1.5f).toInt().coerceAtLeast(1200)
        val overlap = 220
        val out = mutableListOf<OcrLine>()
        var y = 0
        while (y < h) {
            val th = minOf(tileH, h - y)
            val tile = Bitmap.createBitmap(bitmap, 0, y, w, th)
            val first = y == 0
            val last = y + th >= h
            val lo = if (first) Float.NEGATIVE_INFINITY else y + overlap / 2f
            val hi = if (last) Float.POSITIVE_INFINITY else y + th - overlap / 2f
            out += recognizeTile(tile, y).filter { it.cy >= lo && it.cy < hi }
            if (tile !== bitmap) tile.recycle()
            if (last) break
            y += th - overlap
        }
        return out
    }

    private suspend fun recognizeTile(bitmap: Bitmap, offsetY: Int): List<OcrLine> {
        val text = recognizer.process(InputImage.fromBitmap(bitmap, 0)).await()
        val out = mutableListOf<OcrLine>()
        for (block in text.textBlocks) for (line in block.lines) {
            val box = line.boundingBox ?: continue
            val cp = line.cornerPoints
            val angle = if (cp != null && cp.size >= 2) {
                Math.toDegrees(atan2((cp[1].y - cp[0].y).toDouble(), (cp[1].x - cp[0].x).toDouble())).toFloat()
            } else 0f
            out += OcrLine(
                text = line.text,
                left = box.left.toFloat(),
                top = (box.top + offsetY).toFloat(),
                right = box.right.toFloat(),
                bottom = (box.bottom + offsetY).toFloat(),
                angle = angle,
            )
        }
        return out
    }

    companion object {
        fun rotate(b: Bitmap, deg: Float): Bitmap {
            if (deg == 0f) return b
            val m = Matrix().apply { postRotate(deg) }
            return Bitmap.createBitmap(b, 0, 0, b.width, b.height, m, true)
        }

        /**
         * Načte obrázek, otočí podle EXIF a zmenší: fotky na max. 3000 px,
         * vysoké screenshoty na šířku max. 1440 px.
         */
        fun loadBitmap(context: Context, uri: Uri): Bitmap? =
            loadBitmap { context.contentResolver.openInputStream(uri) }

        /** [open] musí pokaždé vrátit nový stream (obrázek se čte víckrát: rozměry, data, EXIF). */
        fun loadBitmap(open: () -> InputStream?): Bitmap? {
            val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
            // Při inJustDecodeBounds vrací decodeStream vždy null – výsledek je jen v bounds.
            (open() ?: return null).use { BitmapFactory.decodeStream(it, null, bounds) }
            if (bounds.outWidth <= 0 || bounds.outHeight <= 0) return null
            val tall = bounds.outHeight > bounds.outWidth * 2
            val limit = if (tall) 1440 else 3000
            val dim = if (tall) bounds.outWidth else maxOf(bounds.outWidth, bounds.outHeight)
            var sample = 1
            while (dim / (sample * 2) >= limit) sample *= 2
            val opts = BitmapFactory.Options().apply {
                inSampleSize = sample
                inPreferredConfig = Bitmap.Config.ARGB_8888
            }
            var bmp = (open() ?: return null).use { BitmapFactory.decodeStream(it, null, opts) } ?: return null
            val curDim = if (tall) bmp.width else maxOf(bmp.width, bmp.height)
            if (curDim > limit) {
                val f = limit.toFloat() / curDim
                val scaled = Bitmap.createScaledBitmap(bmp, (bmp.width * f).toInt(), (bmp.height * f).toInt(), true)
                if (scaled !== bmp) bmp.recycle()
                bmp = scaled
            }
            val orientation = try {
                open()?.use { ExifInterface(it).getAttributeInt(ExifInterface.TAG_ORIENTATION, ExifInterface.ORIENTATION_NORMAL) }
                    ?: ExifInterface.ORIENTATION_NORMAL
            } catch (e: Exception) {
                ExifInterface.ORIENTATION_NORMAL
            }
            val deg = when (orientation) {
                ExifInterface.ORIENTATION_ROTATE_90 -> 90f
                ExifInterface.ORIENTATION_ROTATE_180 -> 180f
                ExifInterface.ORIENTATION_ROTATE_270 -> 270f
                else -> 0f
            }
            val rotated = rotate(bmp, deg)
            if (rotated !== bmp) bmp.recycle()
            return rotated
        }
    }
}
