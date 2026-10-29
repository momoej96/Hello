package com.andrerinas.openheadunit.byd;

import android.content.Context;
import android.content.Intent;
import android.util.Log;

/**
 * Fixes from the Qin Plus DM-i logs (2026-10-29):
 * - Opening the app while Android Auto is connecting sent a manual "poke". The poke re-armed the
 *   Native AA listeners in the middle of the live session, and the phone then reconnected over
 *   Bluetooth about three times a second (114 times in 37 s). Bluetooth and Wi-Fi share the head
 *   unit's 2.4 GHz chip, so video and audio starved. Pokes are now ignored while a session is up.
 * - "Bluetooth settings" crashed the app: BYD has no android.settings.SETTINGS screen.
 */
public final class AapGuard {
    private static final String TAG = "DiAuto-AapGuard";
    private static volatile boolean session;

    private AapGuard() {}

    /** AapService.t0: connection established (WifiLock taken). */
    public static void sessionStarted() {
        session = true;
    }

    /** AapService.u1: connection gone or service stopping (WifiLock released). */
    public static void sessionEnded() {
        session = false;
    }

    /** True when a manual Native AA poke must be skipped because a session is running. */
    public static boolean skipPoke() {
        if (session) Log.i(TAG, "Android Auto is already connected: ignoring the poke so the session stays up");
        return session;
    }

    /** HomeFragment.openBluetoothSettings fallback when BLUETOOTH_SETTINGS is missing. */
    public static void openBluetoothFallback(Object fragment) {
        Context c = null;
        try {
            c = (Context) fragment.getClass().getMethod("getContext").invoke(fragment);
        } catch (Throwable ignored) {
        }
        if (c == null) return;
        String[] actions = {"android.settings.SETTINGS", "android.settings.WIRELESS_SETTINGS"};
        for (String a : actions) {
            try {
                c.startActivity(new Intent(a));
                return;
            } catch (Throwable ignored) {
            }
        }
        String[] packages = {"com.byd.carsettings", "com.byd.systemsettings", "com.android.settings"};
        for (String p : packages) {
            try {
                Intent i = c.getPackageManager().getLaunchIntentForPackage(p);
                if (i != null) {
                    c.startActivity(i);
                    return;
                }
            } catch (Throwable ignored) {
            }
        }
        CarActions.toast(c, "Open Bluetooth from the car's own settings");
    }
}
