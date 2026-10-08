package cz.obchodsken.parser

import kotlin.math.abs

/**
 * Vyhledávání názvů z účtenek tolerantní k chybám OCR:
 * ignoruje diakritiku, zaměňuje podobné znaky (l/1/I, O/0) a snese 1–2 překlepy.
 */
class NameMatcher<T>(entries: Iterable<Pair<String, T>>) {
    private val exact = HashMap<String, T>()
    private val buckets = HashMap<String, MutableList<Pair<String, T>>>()

    init {
        for ((name, value) in entries) add(name, value)
    }

    fun add(name: String, value: T) {
        val k = fold(name)
        if (k.isEmpty()) return
        exact.putIfAbsent(k, value)
        buckets.getOrPut(k.take(2)) { mutableListOf() }.add(k to value)
    }

    val size: Int get() = exact.size

    fun find(name: String): T? {
        val k = fold(name)
        if (k.isEmpty()) return null
        exact[k]?.let { return it }
        if (k.length < 6) return null
        val maxDist = if (k.length >= 16) 2 else 1
        var best: T? = null
        var bestD = Int.MAX_VALUE
        for ((ck, v) in buckets[k.take(2)].orEmpty()) {
            if (abs(ck.length - k.length) > maxDist) continue
            val d = levenshtein(k, ck, maxDist)
            if (d < bestD) {
                bestD = d
                best = v
            }
        }
        return if (bestD <= maxDist) best else null
    }

    companion object {
        /** Klíč pro porovnání. */
        fun fold(s: String): String = ProductNames.key(s)
            .replace(" ", "")
            .map {
                when (it) {
                    'l', 'i', '|', '!' -> '1'
                    'o' -> '0'
                    else -> it
                }
            }
            .joinToString("")

        /** Levenshtein s předčasným ukončením, když vzdálenost určitě přesáhne [limit]. */
        fun levenshtein(a: String, b: String, limit: Int): Int {
            var prev = IntArray(b.length + 1) { it }
            var cur = IntArray(b.length + 1)
            for (i in 1..a.length) {
                cur[0] = i
                var rowMin = cur[0]
                for (j in 1..b.length) {
                    val cost = if (a[i - 1] == b[j - 1]) 0 else 1
                    cur[j] = minOf(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost)
                    if (cur[j] < rowMin) rowMin = cur[j]
                }
                if (rowMin > limit) return limit + 1
                val t = prev; prev = cur; cur = t
            }
            return prev[b.length]
        }
    }
}
