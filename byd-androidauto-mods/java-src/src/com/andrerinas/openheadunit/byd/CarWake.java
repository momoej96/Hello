package com.andrerinas.openheadunit.byd;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.os.SystemClock;
import android.util.Log;

import com.andrerinas.openheadunit.app.BootCompleteReceiver;

/**
 * Starts DiAuto again when the car comes on. BYD head units mostly wake from sleep instead of
 * rebooting, so BOOT_COMPLETED rarely arrives. Two cases, both handed to DiAuto's own boot
 * receiver (QUICKBOOT_POWERON), which follows DiAuto's Auto-start settings:
 * - the car killed the process while asleep: the system starts it again to re-bind the
 *   wheel-key service, so a freshly started process is treated like a boot;
 * - the process survived: the screen comes on after being off for a while (the service keeps a
 *   SCREEN_ON receiver registered for that).
 */
final class CarWake {
    private static final String TAG = "DiAuto-CarWake";
    private static final long FRESH_PROCESS_MS = 30000;
    /** Shorter screen-off spells (a dimmed screen, a quick off/on) are not a car start. */
    private static final long ASLEEP_MS = 60000;

    private static boolean attached;
    private static BroadcastReceiver screen;
    private static long screenOffAt;

    private CarWake() {}

    static synchronized void attach(Context service) {
        if (screen == null) {
            screen = new BroadcastReceiver() {
                public void onReceive(Context c, Intent i) {
                    screenChanged(c, i.getAction());
                }
            };
            IntentFilter f = new IntentFilter(Intent.ACTION_SCREEN_ON);
            f.addAction(Intent.ACTION_SCREEN_OFF);
            try {
                service.getApplicationContext().registerReceiver(screen, f);
            } catch (Throwable t) {
                screen = null;
                Log.w(TAG, "screen receiver failed", t);
            }
        }
        if (attached) return;
        attached = true;
        if (freshProcess()) start(service, "the car started the app");
    }

    static synchronized void detach(Context service) {
        if (screen == null) return;
        try {
            service.getApplicationContext().unregisterReceiver(screen);
        } catch (Throwable ignored) {
        }
        screen = null;
    }

    private static void screenChanged(Context c, String action) {
        long now = SystemClock.elapsedRealtime();
        if (Intent.ACTION_SCREEN_OFF.equals(action)) {
            screenOffAt = now;
        } else if (Intent.ACTION_SCREEN_ON.equals(action)) {
            long off = screenOffAt;
            screenOffAt = 0;
            if (off != 0 && now - off >= ASLEEP_MS && !AapGuard.sessionActive()) {
                start(c, "the car woke up after " + (now - off) / 1000 + " s");
            }
        }
    }

    private static void start(Context c, String why) {
        StatusLine.note("Starting with the car: " + why);
        try {
            new BootCompleteReceiver().onReceive(c.getApplicationContext(),
                    new Intent("android.intent.action.QUICKBOOT_POWERON"));
        } catch (Throwable t) {
            Log.w(TAG, "auto-start failed", t);
            StatusLine.note("Start with the car failed: " + t);
        }
    }

    private static boolean freshProcess() {
        try {
            long start = ((Number) android.os.Process.class.getMethod("getStartElapsedRealtime")
                    .invoke(null)).longValue();
            return SystemClock.elapsedRealtime() - start < FRESH_PROCESS_MS;
        } catch (Throwable t) {
            return false;
        }
    }
}
