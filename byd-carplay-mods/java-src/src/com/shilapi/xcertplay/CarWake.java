package com.shilapi.xcertplay;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.os.SystemClock;
import android.util.Log;

/**
 * Opens DiPlay when the car comes on. BYD head units mostly wake from sleep instead of
 * rebooting, so BOOT_COMPLETED rarely arrives. The wheel-key accessibility service is
 * re-bound by the system after a wake (and may start activities from the background),
 * so it watches the screen coming back on, and a freshly started process, instead.
 */
public final class CarWake {
    private static final String TAG = "DiPlay-CarWake";
    private static final long SCREEN_OFF_MIN_MS = 60000;
    private static final long FRESH_PROCESS_MS = 30000;

    private static boolean attached;
    private static long screenOffAt = -1;

    private CarWake() {}

    public static boolean isBootAction(String action) {
        return "android.intent.action.BOOT_COMPLETED".equals(action)
                || "android.intent.action.QUICKBOOT_POWERON".equals(action)
                || "com.htc.intent.action.QUICKBOOT_POWERON".equals(action);
    }

    /** Called from WheelKeyService.onServiceConnected. */
    public static void attach(Context service) {
        try {
            final Context app = service.getApplicationContext();
            if (!attached) {
                attached = true;
                IntentFilter f = new IntentFilter();
                f.addAction(Intent.ACTION_SCREEN_ON);
                f.addAction(Intent.ACTION_SCREEN_OFF);
                app.registerReceiver(new BroadcastReceiver() {
                    public void onReceive(Context c, Intent i) {
                        String a = i.getAction();
                        long now = SystemClock.elapsedRealtime();
                        if (Intent.ACTION_SCREEN_OFF.equals(a)) {
                            screenOffAt = now;
                        } else if (Intent.ACTION_SCREEN_ON.equals(a)) {
                            long off = screenOffAt;
                            screenOffAt = -1;
                            if (off > 0 && now - off >= SCREEN_OFF_MIN_MS) launch(app, "screen on");
                        }
                    }
                }, f);
                if (freshProcess()) launch(app, "service started");
            }
        } catch (Throwable t) {
            Log.w(TAG, "attach failed", t);
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

    static void launch(Context c, String why) {
        try {
            boolean wanted = AirPlayPersistence.INSTANCE.loadAutoStartOnBoot(c);
            StartupDiagnosticSnapshot.INSTANCE.received(c, wanted);
            if (!wanted) return;
            Log.i(TAG, "opening DiPlay: " + why);
            Intent i = new Intent(c, DiPlayActivity.class);
            i.addFlags(0x34000000);
            try {
                c.startActivity(i);
                StartupDiagnosticSnapshot.INSTANCE.launchResult(c, null);
            } catch (RuntimeException e) {
                StartupDiagnosticSnapshot.INSTANCE.launchResult(c, e);
            }
        } catch (Throwable t) {
            Log.w(TAG, "launch failed", t);
        }
    }
}
