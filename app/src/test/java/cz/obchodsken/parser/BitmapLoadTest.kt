package cz.obchodsken.parser

import cz.obchodsken.ocr.ReceiptOcr
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import org.robolectric.annotation.GraphicsMode

/** Načítání obrázků skutečným dekodérem Androidu (Robolectric native graphics). */
@RunWith(RobolectricTestRunner::class)
@GraphicsMode(GraphicsMode.Mode.NATIVE)
@Config(sdk = [34])
class BitmapLoadTest {
    private fun res(name: String) = { javaClass.classLoader!!.getResourceAsStream(name) }

    @Test fun tallScreenshotKeepsFullResolution() {
        val b = ReceiptOcr.loadBitmap(res("tall_screenshot.png"))
        assertNotNull(b)
        assertEquals(1080, b!!.width)
        assertEquals(5000, b.height)
    }

    @Test fun cameraPhotoIsScaledAndRotatedByExif() {
        val b = ReceiptOcr.loadBitmap(res("photo_exif90.jpg"))
        assertNotNull(b)
        // 4000x3000 na šířku, EXIF říká otočit o 90° -> na výšku, delší strana max 3000
        assertEquals(3000, b!!.height)
        assertEquals(2250, b.width)
    }

    @Test fun garbageReturnsNull() {
        assertNull(ReceiptOcr.loadBitmap { "není obrázek".byteInputStream() })
        assertNull(ReceiptOcr.loadBitmap { null })
    }
}
