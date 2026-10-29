package com.andrerinas.openheadunit.connection.wifi

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class WifiJoinKickPolicyTest {

    private val debounce = 1000L

    @Test
    fun `an event that is not a join never kicks, however long ago the last one was`() {
        // The broadcast below Lollipop also fires for CONNECTING and DISCONNECTED.
        assertFalse(WifiJoinKickPolicy.shouldKick(isConnected = false, nowMs = 900_000L, lastKickMs = 0L, debounceMs = debounce))
    }

    @Test
    fun `the first join kicks`() {
        assertTrue(WifiJoinKickPolicy.shouldKick(isConnected = true, nowMs = 5_000L, lastKickMs = 0L, debounceMs = debounce))
    }

    @Test
    fun `a repeat inside the window is ignored`() {
        assertFalse(WifiJoinKickPolicy.shouldKick(isConnected = true, nowMs = 5_999L, lastKickMs = 5_000L, debounceMs = debounce))
    }

    @Test
    fun `exactly the debounce gap kicks`() {
        assertTrue(WifiJoinKickPolicy.shouldKick(isConnected = true, nowMs = 6_000L, lastKickMs = 5_000L, debounceMs = debounce))
    }

    @Test
    fun `well past the window kicks`() {
        assertTrue(WifiJoinKickPolicy.shouldKick(isConnected = true, nowMs = 60_000L, lastKickMs = 5_000L, debounceMs = debounce))
    }

    @Test
    fun `a duplicate delivery at the same instant is debounced`() {
        assertFalse(WifiJoinKickPolicy.shouldKick(isConnected = true, nowMs = 5_000L, lastKickMs = 5_000L, debounceMs = debounce))
    }
}
