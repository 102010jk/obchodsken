package cz.obchodsken.parser

import java.time.LocalDateTime
import kotlin.math.abs

/** Jedna rozpoznaná položka účtenky. Částky jsou v haléřích. */
data class ParsedItem(
    val rawName: String,
    val price: Long,
    val vat: String? = null,
    val quantity: Double = 1.0,
    val unit: String = "ks",
    val unitPrice: Long? = null,
    val discount: Long = 0,
    val discountLabel: String? = null,
    val articleCode: String? = null,
) {
    val finalPrice: Long get() = price - discount
}

data class ParsedReceipt(
    val store: String,
    val branch: String?,
    val purchasedAt: LocalDateTime?,
    val total: Long?,
    val subtotal: Long?,
    val totalDiscount: Long,
    val payment: String?,
    val receiptNumber: String?,
    val uniqueKey: String?,
    val items: List<ParsedItem>,
    val warnings: List<String>,
) {
    val itemsSum: Long get() = items.sumOf { it.finalPrice }
    val effectiveTotal: Long get() = total ?: subtotal ?: itemsSum
}

/** Řádek textu z OCR i s polohou v obrázku (v pixelech). */
data class OcrLine(
    val text: String,
    val left: Float,
    val top: Float,
    val right: Float,
    val bottom: Float,
    /** Sklon řádku ve stupních (0 = vodorovně). */
    val angle: Float = 0f,
) {
    val height: Float get() = bottom - top
    val cx: Float get() = (left + right) / 2
    val cy: Float get() = (top + bottom) / 2
}

object Money {
    private val re = Regex("""^(-)?\s*(\d{1,7})[,.](\d{2})$""")

    /** "89,90" -> 8990, "-3,49" -> -349 */
    fun parse(s: String): Long? {
        val m = re.matchEntire(s.trim().replace(" ", "")) ?: return null
        val v = m.groupValues[2].toLong() * 100 + m.groupValues[3].toLong()
        return if (m.groupValues[1] == "-") -v else v
    }

    fun format(h: Long, withCurrency: Boolean = true): String {
        val a = abs(h)
        val whole = (a / 100).toString().reversed().chunked(3).joinToString(" ").reversed()
        val s = (if (h < 0) "-" else "") + whole + "," + (a % 100).toString().padStart(2, '0')
        return if (withCurrency) "$s Kč" else s
    }
}
