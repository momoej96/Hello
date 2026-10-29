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
        watch(service);
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

    // ---- wheel-key service watchdog (the same approach as Diplus's "Auto-enable button control") ----
    //
    // Every 5 s while DiPlay's process runs: if the service is allowed in settings but not bound,
    // first turn it off and on in the system settings over ADB, and if it is still not bound after
    // that, force-stop DiPlay and open it again from the ADB shell (the manual fix). An ADB call that
    // gets no answer (ADB not ready yet after a wake) is simply retried on the next tick.

    private static final long TICK_MS = 5000;
    private static final int TOGGLE_AFTER_TICKS = 2;      // stuck for ~10 s
    private static final int RESTART_AFTER_TICKS = 4;     // still stuck ~10 s after the toggle
    private static final long RESTART_MIN_GAP_MS = 10 * 60 * 1000;

    private static android.os.Handler watchHandler;
    private static Context watchContext;
    private static int stuckTicks;
    private static boolean toggled;

    /** Starts the watchdog once per process; safe to call from anywhere, any number of times. */
    public static synchronized void watch(Context context) {
        try {
            if (watchHandler != null) return;
            watchContext = context.getApplicationContext();
            android.os.HandlerThread thread = new android.os.HandlerThread("DiPlay-WheelWatch");
            thread.start();
            watchHandler = new android.os.Handler(thread.getLooper());
            lastTickAt = SystemClock.elapsedRealtime();
            watchHandler.postDelayed(TICK, TICK_MS);
            IntentFilter f = new IntentFilter();
            f.addAction(Intent.ACTION_SCREEN_ON);
            f.addAction(Intent.ACTION_SCREEN_OFF);
            watchContext.registerReceiver(new BroadcastReceiver() {
                public void onReceive(Context c, Intent i) {
                    long now = SystemClock.elapsedRealtime();
                    if (Intent.ACTION_SCREEN_OFF.equals(i.getAction())) {
                        wakeScreenOffAt = now;
                    } else if (Intent.ACTION_SCREEN_ON.equals(i.getAction())) {
                        long off = wakeScreenOffAt;
                        wakeScreenOffAt = -1;
                        if (off > 0 && now - off >= WAKE_SCREEN_OFF_MS) {
                            onWake(watchContext, off, "screen was off " + (now - off) / 1000 + " s");
                        }
                    }
                }
            }, f, null, watchHandler);
            Log.i(TAG, "wheel-key watchdog started");
        } catch (Throwable t) {
            Log.w(TAG, "watch failed", t);
        }
    }

    private static final Runnable TICK = new Runnable() {
        public void run() {
            try {
                // The handler's clock stops while the head unit sleeps; the real clock doesn't.
                long now = SystemClock.elapsedRealtime();
                long last = lastTickAt;
                lastTickAt = now;
                if (now - last > WAKE_GAP_MS) onWake(watchContext, last, "head unit slept " + (now - last) / 1000 + " s");
                wakeRestartTick(watchContext);
                tick(watchContext);
            } catch (Throwable t) {
                Log.w(TAG, "watchdog tick failed", t);
            }
            watchHandler.postDelayed(this, TICK_MS);
        }
    };

    private static void tick(Context c) {
        if (!serviceStuck(c)) {
            if (stuckTicks >= TOGGLE_AFTER_TICKS) note(c, "Wheel key service running again");
            stuckTicks = 0;
            toggled = false;
            return;
        }
        stuckTicks++;
        if (stuckTicks < TOGGLE_AFTER_TICKS) return;
        if (!toggled) {
            if (toggleService(c)) {
                toggled = true;
                note(c, "Wheel key service stuck: turned it off and on");
            }
            return;
        }
        if (stuckTicks < RESTART_AFTER_TICKS) return;
        long now = System.currentTimeMillis();
        long last = CarActions.prefs(c).getLong("carwake_restart_at", 0);
        if (now - last < RESTART_MIN_GAP_MS) return;
        String pkg = c.getPackageName();
        String out = CarActions.adb(c, "echo READY");
        if (out == null) return;                     // ADB not ready yet: try again next tick
        CarActions.prefs(c).edit().putLong("carwake_restart_at", now).commit();
        note(c, "Wheel key service stuck: restarting DiPlay");
        restartDiPlay(c);
    }

    /** Removes DiPlay's service from enabled_accessibility_services and adds it back. False if ADB didn't answer. */
    private static boolean toggleService(Context c) {
        String self = new android.content.ComponentName(c, WheelKeyService.class).flattenToString();
        String current = CarActions.adb(c, "settings get secure enabled_accessibility_services");
        if (current == null) return false;
        StringBuilder without = new StringBuilder();
        for (String part : current.trim().split(":")) {
            String s = part.trim();
            if (s.length() == 0 || "null".equals(s)) continue;
            android.content.ComponentName cn = android.content.ComponentName.unflattenFromString(s);
            if (cn != null && cn.flattenToString().equals(self)) continue;
            if (without.length() > 0) without.append(':');
            without.append(s);
        }
        String with = without.length() > 0 ? without + ":" + self : self;
        CarActions.adb(c, "settings put secure enabled_accessibility_services '" + without + "'");
        try {
            Thread.sleep(800);
        } catch (InterruptedException ignored) {
        }
        return CarActions.adb(c, "settings put secure enabled_accessibility_services '" + with
                + "'; settings put secure accessibility_enabled 1; echo DONE") != null;
    }

    // ---- restart after the car wakes ----
    //
    // After a car off/on the wheel keys can stay dead in a process that lived through the sleep, while the
    // service still looks bound (nothing for the watchdog above to see). A force-stop and reopen always fixes
    // it, so when DiPlay's own process survived the sleep it does that once, automatically. A process that
    // started after the wake is left alone.

    private static final long WAKE_SCREEN_OFF_MS = 10000;
    private static final long WAKE_GAP_MS = 20000;
    private static final long WAKE_WINDOW_MS = 90000;
    private static final long WAKE_RESTART_MIN_GAP_MS = 2 * 60 * 1000;
    static final String KEY_WAKE_RESTART = "carwake_wake_restart";

    private static long lastTickAt;
    private static long wakeScreenOffAt = -1;
    private static long wakePendingSince = -1;
    private static String wakeWhy;

    public static boolean wakeRestartEnabled(Context c) {
        return CarActions.prefs(c).getBoolean(KEY_WAKE_RESTART, true);
    }

    private static long processStart() {
        try {
            return ((Number) android.os.Process.class.getMethod("getStartElapsedRealtime").invoke(null)).longValue();
        } catch (Throwable t) {
            return 0;
        }
    }

    /** sleptFrom: elapsedRealtime when the car went off (screen off, or the last tick before the sleep). */
    private static void onWake(Context c, long sleptFrom, String why) {
        if (!wakeRestartEnabled(c)) return;
        if (processStart() >= sleptFrom) return;                     // started after the wake: fine
        try {
            if (!WheelKeyService.Companion.enabledInSettings(c)) return;
        } catch (Throwable t) {
            return;
        }
        if (wakePendingSince > 0) return;
        wakePendingSince = SystemClock.elapsedRealtime();
        wakeWhy = why;
        Log.i(TAG, "car woke (" + why + "), restart pending");
    }

    private static void wakeRestartTick(Context c) {
        if (wakePendingSince < 0) return;
        if (SystemClock.elapsedRealtime() - wakePendingSince > WAKE_WINDOW_MS) {
            note(c, "Car woke (" + wakeWhy + "), but ADB didn't answer in time");
            wakePendingSince = -1;
            return;
        }
        long now = System.currentTimeMillis();
        if (now - CarActions.prefs(c).getLong("carwake_wake_restart_at", 0) < WAKE_RESTART_MIN_GAP_MS) {
            wakePendingSince = -1;
            return;
        }
        if (CarActions.adb(c, "echo READY") == null) return;         // ADB not ready yet: next tick
        CarActions.prefs(c).edit().putLong("carwake_wake_restart_at", now).commit();
        wakePendingSince = -1;
        note(c, "Car woke (" + wakeWhy + "): restarting DiPlay for the wheel keys");
        restartDiPlay(c);
    }

    private static void restartDiPlay(Context c) {
        String pkg = c.getPackageName();
        CarActions.adb(c, "setsid sh -c 'sleep 1; am force-stop " + pkg + "; sleep 1; am start -n " + pkg + "/"
                + DiPlayActivity.class.getName() + "' </dev/null >/dev/null 2>&1 &");
    }

    /** "Refresh wheel keys" button: the manual force-stop and reopen. */
    public static void refreshNow(final Context context) {
        final Context c = context.getApplicationContext();
        new Thread(new Runnable() {
            public void run() {
                if (CarActions.adb(c, "echo READY") == null) {
                    CarActions.toast(c, "ADB isn't answering, so DiPlay can't restart itself");
                    return;
                }
                note(c, "Wheel keys refreshed by hand: restarting DiPlay");
                restartDiPlay(c);
            }
        }, "DiPlay-RefreshKeys").start();
    }

    // ---- car Bluetooth: start the watchdog and open DiPlay ----

    /** Called first from PhoneBluetoothReceiver.onReceive (a manifest receiver, so it runs even when DiPlay is closed). */
    public static void onBluetooth(Context context, Intent intent) {
        try {
            if (intent == null || !"android.bluetooth.device.action.ACL_CONNECTED".equals(intent.getAction())) return;
            final Context app = context.getApplicationContext();
            watch(app);
            watchHandler.postDelayed(new Runnable() {
                public void run() {
                    if (carPlayRunning()) return;
                    if (serviceStuck(app)) {
                        note(app, "Car Bluetooth: wheel key service stuck, repairing");
                        return;
                    }
                    note(app, "Car Bluetooth: wheel key service running");
                    launch(app, "car Bluetooth");
                }
            }, 2000);
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
