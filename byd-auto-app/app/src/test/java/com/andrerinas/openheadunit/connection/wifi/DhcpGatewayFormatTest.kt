package com.andrerinas.openheadunit.connection.wifi

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertNull
import org.junit.Test

class DhcpGatewayFormatTest {

    /** Packs an address the way `DhcpInfo.gateway` carries it: first octet in the low byte. */
    private fun packed(a: Int, b: Int, c: Int, d: Int): Int =
        a or (b shl 8) or (c shl 16) or (d shl 24)

    @Test
    fun `an unset gateway is not an address, whichever byte order is asked for`() {
        assertNull(DhcpGatewayFormat.toDottedQuad(0, swapBytes = false))
        assertNull(DhcpGatewayFormat.toDottedQuad(0, swapBytes = true))
    }

    @Test
    fun `a little-endian gateway decodes without swapping`() {
        // The phone's hotspot, which is what mode 1 dials.
        assertEquals("192.168.43.1", DhcpGatewayFormat.toDottedQuad(packed(192, 168, 43, 1), swapBytes = false))
    }

    @Test
    fun `the same address decodes when the raw int is reversed and swapping is asked for`() {
        val raw = packed(192, 168, 43, 1)
        assertEquals("192.168.43.1", DhcpGatewayFormat.toDottedQuad(Integer.reverseBytes(raw), swapBytes = true))
    }

    @Test
    fun `not swapping a reversed int gives the wrong address`() {
        // Documents the failure this guards against rather than asserting a particular wrong value.
        val raw = packed(192, 168, 43, 1)
        assertNotEquals("192.168.43.1", DhcpGatewayFormat.toDottedQuad(Integer.reverseBytes(raw), swapBytes = false))
    }

    @Test
    fun `a zero octet inside the address is not mistaken for an unset gateway`() {
        assertEquals("10.0.2.2", DhcpGatewayFormat.toDottedQuad(packed(10, 0, 2, 2), swapBytes = false))
    }

    @Test
    fun `the high octet is masked rather than sign-extended`() {
        // 255 in the last octet makes the raw int negative; a shift without the mask would show it.
        assertEquals("192.168.1.255", DhcpGatewayFormat.toDottedQuad(packed(192, 168, 1, 255), swapBytes = false))
    }
}
