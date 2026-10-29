package com.andrerinas.openheadunit.connection.wifi

/**
 * Which address a discovery sweep walks the /24 of.
 *
 * Both readings used to be the first interface `NetworkInterface.getNetworkInterfaces()` happened
 * to list, and head units carry a lot of them: on one unit every sweep walked an LTE stub's
 * `100.118.187.*` while the phone sat on `wlan0`, in every WiFi condition tried.
 */
object DiscoverySubnetPolicy {

    /** The network carrying traffic wins; the enumeration is what is left when it cannot be read. */
    fun address(stationIpv4: String?, firstInterfaceIpv4: String?): String? =
        stationIpv4?.takeIf { it.isNotBlank() } ?: firstInterfaceIpv4?.takeIf { it.isNotBlank() }

    /** Says which of the two [address] took, for the line the sweep prints. */
    fun source(stationIpv4: String?): String =
        if (!stationIpv4.isNullOrBlank()) "the joined WiFi network"
        else "the first interface that is up"

    /** The first three octets, or null when [ipv4] is not a dotted quad. */
    fun subnetOf(ipv4: String?): String? {
        val host = ipv4?.takeIf { it.isNotBlank() } ?: return null
        val parts = host.split('.')
        if (parts.size != 4 || parts.any { it.isEmpty() || it.toIntOrNull() !in 0..255 }) return null
        return parts.take(3).joinToString(".")
    }
}
