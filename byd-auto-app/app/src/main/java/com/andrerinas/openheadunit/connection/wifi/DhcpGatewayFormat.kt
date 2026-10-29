package com.andrerinas.openheadunit.connection.wifi

/**
 * Turns `DhcpInfo.gateway` into an address to dial.
 *
 * The field is a raw int packed least-significant byte first, so it needs the host's byte order
 * undone on a big-endian device. Unset reads as 0, which is not an address.
 */
object DhcpGatewayFormat {

    fun toDottedQuad(rawGateway: Int, swapBytes: Boolean): String? {
        if (rawGateway == 0) return null
        val value = if (swapBytes) Integer.reverseBytes(rawGateway) else rawGateway
        return "${value and 0xFF}.${(value shr 8) and 0xFF}." +
            "${(value shr 16) and 0xFF}.${(value shr 24) and 0xFF}"
    }
}
