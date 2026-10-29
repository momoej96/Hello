package com.andrerinas.openheadunit.connection.wifi.modes.nativeaa.zbt

/**
 * Whether to repeat the handshake's opening message while the phone has said nothing.
 *
 * On this unit's own radio an accept proves the phone is there, so a message that goes out is a
 * message that arrived. On the module there is no accept: the daemon owns the Android Auto server,
 * and our first message can go out before the phone's channel exists on the far side, where it is
 * dropped with nobody told. Repeating is the only cover for that, and it is why the vendor's own
 * client repeats too.
 *
 * One answer from the phone retires it: from then on the exchange has its own stage deadlines.
 */
object ZbtRetransmitPolicy {

    /**
     * Gap between repeats. The vendor's client retries about 2.1 s apart, and this stays well
     * inside the phone's own wait for a first message.
     */
    const val INTERVAL_MS = 2_500L

    /**
     * @param enabled the transport has no accept to prove the phone is there
     * @param phoneHasAnswered anything at all has come back
     * @param lastSentAtMs when the opening message last went out, or 0 if it has not yet
     * @param nowMs the current elapsed-time reading
     */
    fun shouldResend(
        enabled: Boolean,
        phoneHasAnswered: Boolean,
        lastSentAtMs: Long,
        nowMs: Long
    ): Boolean {
        if (!enabled || phoneHasAnswered) return false
        // The first copy is the handshake's own send. Nothing to repeat until it has happened,
        // which is also what keeps this inert when the version exchange is switched off.
        if (lastSentAtMs == 0L) return false
        // A clock that moved backwards reads as too soon, rather than firing every pass.
        return nowMs - lastSentAtMs >= INTERVAL_MS
    }
}
