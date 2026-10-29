package com.andrerinas.openheadunit.connection.wifi

/**
 * Whether a WiFi event is a join worth starting a discovery sweep for.
 *
 * Both API tiers ask this — `NetworkCallback.onAvailable` above Lollipop and
 * `NETWORK_STATE_CHANGED_ACTION` below it — so the debounce cannot drift between them. Both fire
 * repeatedly for one join, and the broadcast also fires for states that are not a join at all.
 */
object WifiJoinKickPolicy {

    fun shouldKick(
        isConnected: Boolean,
        nowMs: Long,
        lastKickMs: Long,
        debounceMs: Long
    ): Boolean = isConnected && nowMs - lastKickMs >= debounceMs
}
