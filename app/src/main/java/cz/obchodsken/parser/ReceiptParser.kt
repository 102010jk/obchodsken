package cz.obchodsken.parser

import java.time.LocalDateTime
import kotlin.math.abs
import kotlin.math.roundToLong

/**
 * Převádí text účtenky (po řádcích) na strukturovaná data.
 *
 * Primárně laděno na Lidl (papírové i elektronické z Lidl Plus), ale stejná pravidla
 * ("název ... cena DPH") fungují i pro většinu ostatních českých obchodů.
 */
object ReceiptParser {

    private const val MONEY = """-?\d{1,6}[,.]\d{2}"""

    private val itemRe = Regex("""^(.*\p{L}.*?)\s+($MONEY)\s*([A-D8])?\s*\*?$""")
    private val priceOnlyRe = Regex("""^($MONEY)\s*([A-D8])?$""")
    private val qtyRe = Regex("""^(\d{1,3})\s*ks\.?\s*[xX×*]\s*(\d{1,6}[,.]\d{2})""", RegexOption.IGNORE_CASE)
    private val weightRe = Regex("""^(?:[A-Z]{1,2}[.:,]?\s+)?(\d{1,3}[,.]\d{1,3})\s*kg\.?\s*[xX×*]\s*(\d{1,6}[,.]\d{2})""", RegexOption.IGNORE_CASE)
    private val tareRe = Regex("""^PT\s*[:.]""", RegexOption.IGNORE_CASE)
    private val afterDiscountRe = Regex("""^Cena\s+po\s+slev\S*\s+($MONEY)""", RegexOption.IGNORE_CASE)
    private val discountRe = Regex("""^(.*?)\s*(-\s?\d{1,6}[,.]\d{2})\s*[A-D]?$""")
    private val discountWordRe = Regex("""^(.*(?:slev|akce|kup[oó]n).*?)\s+(\d{1,6}[,.]\d{2})$""", RegexOption.IGNORE_CASE)
    private val vatSummaryRe = Regex("""\bDPH\b""")
    private val articleRe = Regex("""^(\d{4,8})\s*(\p{L}.*)$""")
    private val dashRe = Regex("""^[-=_.\s]{6,}$""")

    private val totalRe = Regex("""K\s*PLATB\S*\s*:?\s*($MONEY)""", RegexOption.IGNORE_CASE)
    private val genericTotalRe = Regex("""^(?:CELKEM|K\s*[UÚ]HRAD\S*|Celkem\s+k\s+[uú]hrad\S*|Celkem\s+Kč)\s*:?\s*(?:Kč)?\s*($MONEY)""", RegexOption.IGNORE_CASE)
    private val sumaRe = Regex("""^SUMA\b.*?($MONEY)\s*$""", RegexOption.IGNORE_CASE)
    private val totalDiscountRe = Regex("""Celkov\S*\s+sleva\s+($MONEY)""", RegexOption.IGNORE_CASE)
    private val endItemsRe = Regex("""^(K\s*PLATB|SUMA\b|MEZISOU|CELKEM|K\s*[UÚ]HRAD|Celkov\S*\s+zaplac|Celkov\S*\s+sleva|Platba|Hotovost|Karta\b)""", RegexOption.IGNORE_CASE)
    private val receiptNoRe = Regex("""[ÚU]čtenka\s+č\S*\s*:?\s*(\d{3,})""", RegexOption.IGNORE_CASE)
    private val lidlKeyRe = Regex("""\b(\d{4})\s+(\d{5,7}\s*/\s*\d{2,3}\s*/\s*\d{2})\b""")

    private val dateDotRe = Regex("""\b(\d{2})\.(\d{2})\.(\d{2}|\d{4})\s+(\d{1,2}):(\d{2})(?::(\d{2}))?""")
    private val dateSlashRe = Regex("""\b(\d{2})/(\d{2})/(\d{2}|\d{4})\s+(\d{1,2}):(\d{2})(?::(\d{2}))?""")
    private val dateOnlyRe = Regex("""\b(\d{1,2})\.\s?(\d{1,2})\.\s?(20\d{2})\b""")

    private val stores = listOf(
        "lidl" to "Lidl", "kaufland" to "Kaufland", "albert" to "Albert", "billa" to "Billa",
        "penny" to "Penny", "tesco" to "Tesco", "globus" to "Globus", "makro" to "Makro",
        "rossmann" to "Rossmann", "dm drogerie" to "dm", "teta" to "Teta", "norma" to "Norma",
        "coop" to "Coop", "hruška" to "Hruška", "ikea" to "IKEA", "action" to "Action",
    )

    fun normalizeRow(row: String): String = row
        .replace('—', '-').replace('–', '-').replace('−', '-')
        .replace('×', 'x')
        .replace('|', ' ')
        .replace(Regex("""(\d)\s*,\s+(\d)"""), "$1,$2")
        .replace(Regex("""(\d)\s+,(\d)"""), "$1,$2")
        .replace(Regex("""(^|\s)-\s+(\d)"""), "$1-$2")
        .replace(Regex("""\s+"""), " ")
        .trim()

    fun parse(rows: List<String>): ParsedReceipt {
        val lines = rows.map(::normalizeRow).filter { it.isNotEmpty() }
        val full = lines.joinToString("\n")
        val lower = full.lowercase()
        val store = stores.firstOrNull { lower.contains(it.first) }?.second ?: "Neznámý obchod"

        val items = mutableListOf<ParsedItem>()
        var pendingName: String? = null
        var itemsEnded = false
        var total: Long? = null
        var subtotal: Long? = null
        var totalDiscount = 0L
        var payment: String? = null
        var branch: String? = null
        val warnings = mutableListOf<String>()

        fun updateLast(f: (ParsedItem) -> ParsedItem) {
            if (items.isNotEmpty()) items[items.lastIndex] = f(items.last())
        }

        for ((i, line) in lines.withIndex()) {
            // --- hlavička / patička (platí kdekoli) ---
            if (branch == null && line.contains("provozovna", ignoreCase = true)) {
                val after = line.substringAfter(':', "").trim()
                branch = (after.ifEmpty { lines.getOrNull(i + 1) ?: "" })
                    .replace(Regex("""\s+,"""), ",").trim().ifEmpty { null }
                continue
            }
            totalRe.find(line)?.let { if (total == null) total = Money.parse(it.groupValues[1]) }
            if (total == null) genericTotalRe.find(line)?.let { total = Money.parse(it.groupValues[1]) }
            sumaRe.find(line)?.let { subtotal = Money.parse(it.groupValues[1]) }
            totalDiscountRe.find(line)?.let { totalDiscount = Money.parse(it.groupValues[1]) ?: 0 }
            if (payment == null) {
                when {
                    line.startsWith("Karta", true) || line.contains("Visa", true) || line.contains("Mastercard", true) -> payment = "Karta"
                    line.startsWith("Hotovost", true) -> payment = "Hotovost"
                }
            }

            if (itemsEnded) continue
            if (endItemsRe.containsMatchIn(line) || (dashRe.matches(line) && items.isNotEmpty())) {
                if (items.isNotEmpty()) itemsEnded = true
                continue
            }
            if (vatSummaryRe.containsMatchIn(line)) {
                if (items.isNotEmpty()) itemsEnded = true
                continue
            }
            if (line == "Kč" || line == "Kc" || tareRe.containsMatchIn(line)) continue

            // --- položky ---
            val qm = qtyRe.find(line)
            if (qm != null) {
                val q = qm.groupValues[1].toDouble()
                val up = Money.parse(qm.groupValues[2])
                updateLast { it.copy(quantity = q, unit = "ks", unitPrice = up) }
                pendingName = null
                continue
            }
            val wm = weightRe.find(line)
            if (wm != null) {
                val q = wm.groupValues[1].replace(',', '.').toDouble()
                val up = Money.parse(wm.groupValues[2])
                updateLast { it.copy(quantity = q, unit = "kg", unitPrice = up) }
                pendingName = null
                continue
            }
            val am = afterDiscountRe.find(line)
            if (am != null) {
                val after = Money.parse(am.groupValues[1])
                // Když OCR přehlédlo řádek se slevou, dopočítáme ji z "Cena po slevě".
                if (after != null) updateLast {
                    if (it.price - it.discount != after && after in 0..it.price)
                        it.copy(discount = it.price - after, discountLabel = it.discountLabel ?: "Sleva")
                    else it
                }
                continue
            }
            val disc = discountRe.matchEntire(line)?.let { it.groupValues[1] to it.groupValues[2] }
                ?: discountWordRe.matchEntire(line)?.let { it.groupValues[1] to it.groupValues[2] }
            if (disc != null && items.isNotEmpty() &&
                (disc.second.trim().startsWith("-") || disc.first.contains("slev", true))
            ) {
                val amount = abs(Money.parse(disc.second.replace(" ", "")) ?: 0)
                val label = disc.first.trim().ifEmpty { "Sleva" }
                updateLast { it.copy(discount = it.discount + amount, discountLabel = label) }
                pendingName = null
                continue
            }

            val m = itemRe.matchEntire(line)
            if (m != null) {
                val price = Money.parse(m.groupValues[2]) ?: continue
                items += makeItem(m.groupValues[1], price, m.groupValues[3])
                pendingName = null
                continue
            }
            val po = priceOnlyRe.matchEntire(line)
            if (po != null && pendingName != null) {
                val price = Money.parse(po.groupValues[1]) ?: continue
                items += makeItem(pendingName!!, price, po.groupValues[2])
                pendingName = null
                continue
            }
            pendingName = if (line.any { it.isLetter() } && line.length > 2) line else null
        }

        // --- datum, číslo účtenky, unikátní klíč ---
        val date = findDate(full)
        val receiptNo = receiptNoRe.find(full)?.groupValues?.get(1)
        val lidlKey = lidlKeyRe.findAll(full).lastOrNull()?.let {
            it.groupValues[1] + " " + it.groupValues[2].replace(" ", "")
        }
        val effTotal = total ?: subtotal
        val uniqueKey = when {
            lidlKey != null && date != null -> "$store|$lidlKey|${date.toLocalDate()}"
            date != null && effTotal != null -> "$store|${date.withSecond(0)}|$effTotal"
            else -> null
        }

        // --- kontrola součtu ---
        val sum = items.sumOf { it.finalPrice }
        val reference = subtotal ?: total
        if (items.isEmpty()) {
            warnings += "Nenašel jsem žádné položky – zkontroluj fotku nebo je doplň ručně."
        } else if (reference != null && abs(reference - sum) > 1) {
            warnings += "Součet položek ${Money.format(sum)} nesedí s celkem ${Money.format(reference)} – některá položka se možná špatně přečetla."
        }
        if (total == null && subtotal == null) warnings += "Nenašel jsem celkovou částku."
        if (date == null) warnings += "Nenašel jsem datum nákupu."

        return ParsedReceipt(
            store = store,
            branch = branch,
            purchasedAt = date,
            total = total,
            subtotal = subtotal,
            totalDiscount = if (totalDiscount > 0) totalDiscount else items.sumOf { it.discount },
            payment = payment,
            receiptNumber = receiptNo,
            uniqueKey = uniqueKey,
            items = items.toList(),
            warnings = warnings,
        )
    }

    private fun makeItem(rawName: String, price: Long, vat: String?): ParsedItem {
        var name = rawName.trim().trimEnd('.', ':').trim()
        var code: String? = null
        articleRe.matchEntire(name)?.let {
            code = it.groupValues[1]
            name = it.groupValues[2].trim()
        }
        val v = vat?.takeIf { it.isNotEmpty() }?.let { if (it == "8") "B" else it }
        return ParsedItem(rawName = name, price = price, vat = v, articleCode = code)
    }

    fun findDate(text: String): LocalDateTime? {
        // Lidl: dole "07.10.26 18:39:41" (přesnější, se sekundami), u karty "07/10/26 18:40".
        for (re in listOf(dateDotRe, dateSlashRe)) {
            val m = re.findAll(text).lastOrNull() ?: continue
            val g = m.groupValues
            toDate(g[1], g[2], g[3], g[4], g[5], g[6])?.let { return it }
        }
        dateOnlyRe.find(text)?.let { toDate(it.groupValues[1], it.groupValues[2], it.groupValues[3], "0", "0", "")?.let { d -> return d } }
        return null
    }

    private fun toDate(d: String, mo: String, y: String, h: String, mi: String, s: String): LocalDateTime? = try {
        val year = y.toInt().let { if (it < 100) 2000 + it else it }
        LocalDateTime.of(year, mo.toInt(), d.toInt(), h.toInt(), mi.toInt(), s.toIntOrNull() ?: 0)
    } catch (e: Exception) {
        null
    }

    /** Skóre "jak moc to vypadá jako účtenka" – používá se pro výběr správného natočení fotky. */
    fun score(rows: List<String>): Int {
        val norm = rows.map(::normalizeRow)
        var s = norm.count { itemRe.matches(it) } * 2
        val text = norm.joinToString("\n")
        if (totalRe.containsMatchIn(text)) s += 5
        if (text.contains("DPH", true)) s += 2
        if (text.contains("Lidl", true)) s += 2
        return s
    }

    fun unitPriceOf(item: ParsedItem): Long =
        item.unitPrice ?: if (item.quantity > 0) (item.finalPrice / item.quantity).roundToLong() else item.finalPrice
}
