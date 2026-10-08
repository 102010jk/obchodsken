package cz.obchodsken.parser

import kotlin.math.abs
import kotlin.math.cos
import kotlin.math.sin

/**
 * OCR vrací text po blocích – název zboží vlevo a cena vpravo bývají v různých blocích.
 * Tady se řádky poskládají zpět podle výšky, takže vznikne "Zahradní směs 89,90 B".
 */
object RowBuilder {

    fun buildRows(lines: List<OcrLine>): List<String> {
        val usable = lines.filter { it.text.isNotBlank() && it.height > 0 }
        if (usable.isEmpty()) return emptyList()

        // Mírně nakřivo vyfocená účtenka: středy řádků otočíme zpět o medián sklonu.
        val angles = usable.filter { it.text.length >= 4 }.map { it.angle }.sorted()
        val skew = if (angles.isEmpty()) 0f else angles[angles.size / 2]
        val rad = Math.toRadians(-skew.toDouble())
        val c = cos(rad).toFloat()
        val s = sin(rad).toFloat()

        data class P(val line: OcrLine, val x: Float, val y: Float)

        val pts = usable.map { P(it, it.cx * c - it.cy * s, it.cx * s + it.cy * c) }
        val heights = usable.map { it.height }.sorted()
        val medianH = heights[heights.size / 2]
        val tolerance = medianH * 0.5f

        val rows = mutableListOf<MutableList<P>>()
        val rowY = mutableListOf<Float>()
        for (p in pts.sortedBy { it.y }) {
            val idx = rowY.indices.lastOrNull { abs(rowY[it] - p.y) <= tolerance }
            if (idx != null) {
                rows[idx].add(p)
                rowY[idx] = rows[idx].map { it.y }.average().toFloat()
            } else {
                rows.add(mutableListOf(p))
                rowY.add(p.y)
            }
        }
        return rows.indices.sortedBy { rowY[it] }.map { i ->
            rows[i].sortedBy { it.x }.joinToString(" ") { it.line.text.trim() }
        }
    }
}
