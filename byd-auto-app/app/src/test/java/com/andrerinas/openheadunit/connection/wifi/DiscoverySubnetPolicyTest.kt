package com.andrerinas.openheadunit.connection.wifi

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class DiscoverySubnetPolicyTest {

    /** The measured failure: an LTE stub is listed first, so every sweep walked its subnet. */
    @Test
    fun `the joined network beats whatever the kernel lists first`() {
        assertEquals(
            "10.182.90.90",
            DiscoverySubnetPolicy.address(stationIpv4 = "10.182.90.90", firstInterfaceIpv4 = "100.118.187.4")
        )
        assertEquals("10.182.90", DiscoverySubnetPolicy.subnetOf("10.182.90.90"))
    }

    @Test
    fun `a unit whose WiFi cannot be read keeps the old answer`() {
        assertEquals(
            "100.118.187.4",
            DiscoverySubnetPolicy.address(stationIpv4 = null, firstInterfaceIpv4 = "100.118.187.4")
        )
    }

    @Test
    fun `a blank reading is not an address`() {
        assertEquals(
            "192.168.1.5",
            DiscoverySubnetPolicy.address(stationIpv4 = "", firstInterfaceIpv4 = "192.168.1.5")
        )
        assertNull(DiscoverySubnetPolicy.address(stationIpv4 = null, firstInterfaceIpv4 = null))
    }

    @Test
    fun `the source names which reading was used`() {
        assertEquals("the joined WiFi network", DiscoverySubnetPolicy.source("10.182.90.90"))
        assertEquals("the first interface that is up", DiscoverySubnetPolicy.source(null))
    }

    @Test
    fun `anything that is not a dotted quad has no subnet`() {
        assertNull(DiscoverySubnetPolicy.subnetOf(null))
        assertNull(DiscoverySubnetPolicy.subnetOf("fe80::1"))
        assertNull(DiscoverySubnetPolicy.subnetOf("10.182.90"))
        assertNull(DiscoverySubnetPolicy.subnetOf("10.182.90.999"))
    }
}
