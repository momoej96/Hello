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

    // ---- car Bluetooth: repair the wheel-key service, then open DiPlay ----

    private static final long REPAIR_MIN_GAP_MS = 5 * 60 * 1000;
    private static volatile long lastRepair;

    /** Called first from PhoneBluetoothReceiver.onReceive (a manifest receiver, so it runs even when DiPlay is closed). */
    public static void onBluetooth(Context context, Intent intent) {
        try {
            if (intent == null || !"android.bluetooth.device.action.ACL_CONNECTED".equals(intent.getAction())) return;
            final Context app = context.getApplicationContext();
            new Thread(new Runnable() {
                public void run() {
                    try {
                        repairThenOpen(app);
                    } catch (Throwable t) {
                        Log.w(TAG, "bluetooth repair failed", t);
                    }
                }
            }, "DiPlay-CarWake-BT").start();
        } catch (Throwable t) {
            Log.w(TAG, "onBluetooth failed", t);
        }
    }

    private static boolean serviceStuck(Context c) {
        try {
            return WheelKeyService.Companion.enabledInSettings(c) && !WheelKeyService.Companion.connected();
        } catch (Throwable t) {
            return false;
        }
    }

    private static boolean carPlayRunning() {
        try {
            return CarPlayBackgroundSession.INSTANCE.hasSession();
        } catch (Throwable t) {
            return false;
        }
    }

    private static void note(Context c, String text) {
        Log.i(TAG, text);
        try {
            CarActions.prefs(c).edit().putString("carwake_last", text + " · "
                    + new java.text.SimpleDateFormat("HH:mm:ss", java.util.Locale.US).format(new java.util.Date()))
                    .apply();
        } catch (Throwable ignored) {
        }
    }

    public static String lastNote(Context c) {
        try {
            return CarActions.prefs(c).getString("carwake_last", null);
        } catch (Throwable t) {
            return null;
        }
    }

    static void repairThenOpen(Context c) throws InterruptedException {
        Thread.sleep(2000);
        if (carPlayRunning()) return;
        if (!serviceStuck(c)) {
            note(c, "Bluetooth: wheel key service already running");
            launch(c, "car Bluetooth");
            return;
        }
        long now = System.currentTimeMillis();
        if (now - lastRepair < REPAIR_MIN_GAP_MS
                || now - CarActions.prefs(c).getLong("carwake_repair_at", 0) < REPAIR_MIN_GAP_MS) {
            note(c, "Bluetooth: service stuck, repaired recently, skipped");
            return;
        }
        lastRepair = now;
        CarActions.prefs(c).edit().putLong("carwake_repair_at", now).commit();

        // 1) Turn the service off and on in the system settings so the system binds it again.
        String self = new android.content.ComponentName(c, WheelKeyService.class).flattenToString();
        String current = CarActions.adb(c, "settings get secure enabled_accessibility_services");
        if (current != null) {
            current = current.trim();
            StringBuilder without = new StringBuilder();
            for (String part : current.split(":")) {
                android.content.ComponentName cn = android.content.ComponentName.unflattenFromString(part.trim());
                if (part.trim().length() == 0 || "null".equals(part.trim())) continue;
                if (cn != null && cn.flattenToString().equals(self)) continue;
                if (without.length() > 0) without.append(':');
                without.append(part.trim());
            }
            String with = without.length() > 0 ? without + ":" + self : self;
            CarActions.adb(c, "settings put secure enabled_accessibility_services '"
                    + (without.length() > 0 ? without.toString() : "") + "'");
            Thread.sleep(800);
            CarActions.adb(c, "settings put secure enabled_accessibility_services '" + with
                    + "'; settings put secure accessibility_enabled 1");
            for (int i = 0; i < 6; i++) {
                Thread.sleep(500);
                if (!serviceStuck(c)) {
                    note(c, "Bluetooth: wheel key service restarted from settings");
                    launch(c, "car Bluetooth");
                    return;
                }
            }
        }
        // 2) Same as the manual fix (and what Diplus does): force-stop DiPlay and open it again.
        //    Runs detached in the ADB shell, so it survives this process being stopped.
        note(c, "Bluetooth: wheel key service stuck, restarting DiPlay");
        String pkg = c.getPackageName();
        CarActions.adb(c, "nohup sh -c 'sleep 1; am force-stop " + pkg + "; sleep 1; am start -n " + pkg + "/"
                + DiPlayActivity.class.getName() + "' >/dev/null 2>&1 &");
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
