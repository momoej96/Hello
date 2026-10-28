package com.andrerinas.openheadunit.byd;

import android.content.Context;
import android.content.Intent;
import android.os.SystemClock;
import android.util.Log;

import com.andrerinas.openheadunit.app.BootCompleteReceiver;

/**
 * Starts DiAuto again when the car comes on. BYD head units mostly wake from sleep instead of
 * rebooting, so BOOT_COMPLETED rarely arrives, but the system re-binds the wheel-key service
 * (and starts the process for it). A freshly started process is treated like a boot and handed
 * to DiAuto's own boot receiver, which follows DiAuto's Auto-start settings. While DiAuto's
 * service keeps running, its own screen-on wake detection takes over.
 */
final class CarWake {
    private static final String TAG = "DiAuto-CarWake";
    private static final long FRESH_PROCESS_MS = 30000;

    private static boolean attached;

    private CarWake() {}

    static void attach(Context service) {
        if (attached) return;
        attached = true;
        try {
            if (!freshProcess()) return;
            Log.i(TAG, "process started with the wheel-key service: running boot auto-start");
            new BootCompleteReceiver().onReceive(service.getApplicationContext(),
                    new Intent("android.intent.action.QUICKBOOT_POWERON"));
        } catch (Throwable t) {
            Log.w(TAG, "auto-start failed", t);
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
