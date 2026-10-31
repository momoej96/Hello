package com.andrerinas.openheadunit.byd;

import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.net.wifi.WifiConfiguration;
import android.net.wifi.WifiManager;
import android.os.Handler;
import android.os.Looper;
import android.os.SystemClock;
import android.util.Log;

/**
 * The car's own short-lived Wi-Fi network for Android Auto: Android's local-only hotspot.
 *
 * Why: on the Qin Plus DM-i the phone only ever joined the WiFi Direct group while the car's
 * Wi-Fi was connected to some network (the phone's hotspot); otherwise it failed with -11 every
 * time, on every channel tried. A normal access point is what the car does reliably (its
 * hotspot came up as ap0 in the logs), and joining one is the most ordinary thing a phone does.
 * DiAuto's own "Local hotspot" refuses anything but 5 GHz, which this unit doesn't have, and its
 * "Hotspot" mode needs the name and password typed in, because apps may not read the system
 * hotspot settings. A local-only hotspot needs neither: the app starts it itself (no internet
 * sharing, no settings) and Android hands the app its random name and password, which are
 * written into DiAuto's "hotspot name/password" fields so its Hotspot mode sends them to the
 * phone. If the unit refuses a local-only hotspot, DiAuto goes back to WiFi Direct by itself.
 */
public final class LocalHotspot {
    private static final String TAG = "DiAuto-LocalHotspot";
    static final String KEY_FAILED = "lohs_failed";
    static final int TRANSPORT_WIFI_DIRECT = 0;
    static final int TRANSPORT_HOTSPOT = 1;
    private static final long RESTART_MS = 3000;
    private static final long START_TIMEOUT_MS = 15000;
    private static final int GIVE_UP_AFTER = 3;

    private static final Handler MAIN = new Handler(Looper.getMainLooper());

    /** Kept alive for as long as the hotspot should stay up (closing it stops the hotspot). */
    private static Object reservation;
    private static boolean starting;
    private static long startedAt;
    private static int failures;
    private static String ssid;

    private LocalHotspot() {}

    static SharedPreferences settings(Context c) {
        return c.getSharedPreferences("settings", 0);
    }

    static boolean wanted(Context c) {
        return settings(c).getInt("native-ap-transport", TRANSPORT_HOTSPOT) == TRANSPORT_HOTSPOT
                && !CarActions.prefs(c).getBoolean(KEY_FAILED, false);
    }

    public static synchronized boolean running() {
        return reservation != null;
    }

    public static synchronized String ssid() {
        return ssid;
    }

    /**
     * Called when DiAuto's Hotspot mode starts and whenever it asks for the access point again.
     * Starts the local-only hotspot if it isn't up. Android 9 only starts one for an app in the
     * foreground, so the request goes through a transparent activity.
     */
    public static void ensure(Context context) {
        final Context c = context.getApplicationContext() != null ? context.getApplicationContext() : context;
        synchronized (LocalHotspot.class) {
            if (!wanted(c) || reservation != null) return;
            if (starting && SystemClock.elapsedRealtime() - startedAt < START_TIMEOUT_MS) return;
            starting = true;
            startedAt = SystemClock.elapsedRealtime();
        }
        log(c, "starting the car's local Wi-Fi network for Android Auto");
        try {
            Intent i = new Intent(c, HotspotActivity.class);
            i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | 0x00010000 /* NO_ANIMATION */ | 0x00800000 /* EXCLUDE_FROM_RECENTS */);
            c.startActivity(i);
        } catch (Throwable t) {
            startFailed(c, "could not open the starter: " + t);
        }
    }

    /** Runs inside HotspotActivity, which is in the foreground. */
    static void requestNow(final Context c) {
        try {
            WifiManager wm = (WifiManager) c.getApplicationContext().getSystemService(Context.WIFI_SERVICE);
            wm.startLocalOnlyHotspot(new WifiManager.LocalOnlyHotspotCallback() {
                @Override
                public void onStarted(WifiManager.LocalOnlyHotspotReservation r) {
                    WifiConfiguration cfg = null;
                    try {
                        cfg = r.getWifiConfiguration();
                    } catch (Throwable ignored) {
                    }
                    started(c, r, cfg == null ? null : cfg.SSID, cfg == null ? null : cfg.preSharedKey);
                }

                @Override
                public void onStopped() {
                    stopped(c);
                }

                @Override
                public void onFailed(int reason) {
                    startFailed(c, reasonName(reason));
                }
            }, MAIN);
        } catch (Throwable t) {
            startFailed(c, t.getClass().getSimpleName() + ": " + t.getMessage());
        }
    }

    static String reasonName(int reason) {
        switch (reason) {
            case 1: return "no channel";
            case 2: return "generic error";
            case 3: return "incompatible mode (tethering on, or app not in the foreground)";
            case 4: return "tethering not allowed";
            default: return "reason " + reason;
        }
    }

    static String unquote(String s) {
        if (s == null) return null;
        if (s.length() >= 2 && s.startsWith("\"") && s.endsWith("\"")) return s.substring(1, s.length() - 1);
        return s;
    }

    static void started(Context c, Object r, String rawSsid, String rawPsk) {
        String name = unquote(rawSsid);
        String pass = unquote(rawPsk);
        synchronized (LocalHotspot.class) {
            starting = false;
            reservation = r;
            failures = 0;
            ssid = name;
        }
        if (name == null || name.length() == 0) {
            log(c, "local network is up but Android gave no name for it; DiAuto will look it up itself");
            return;
        }
        // DiAuto's Hotspot mode sends these to the phone. Interface left automatic (ap0 here).
        settings(c).edit()
                .putString("hotspot-ssid", name)
                .putString("hotspot-password", pass == null ? "" : pass)
                .putString("hotspot-interface", "")
                .apply();
        log(c, "local network up: " + name + " (2.4 GHz, no internet needed); its name and password are handed to the phone");
    }

    static void stopped(final Context c) {
        synchronized (LocalHotspot.class) {
            reservation = null;
            starting = false;
            ssid = null;
        }
        log(c, "local network stopped by the system; starting it again in 3 s");
        MAIN.postDelayed(new Runnable() {
            public void run() {
                ensure(c);
            }
        }, RESTART_MS);
    }

    static void startFailed(final Context c, String why) {
        int n;
        synchronized (LocalHotspot.class) {
            starting = false;
            reservation = null;
            n = ++failures;
        }
        if (n >= GIVE_UP_AFTER) {
            CarActions.prefs(c).edit().putBoolean(KEY_FAILED, true).apply();
            settings(c).edit().putInt("native-ap-transport", TRANSPORT_WIFI_DIRECT).apply();
            log(c, "this car refused a local network " + n + " times (" + why + "); switching Android Auto back to WiFi Direct");
            return;
        }
        log(c, "local network did not start (" + why + "), try " + n + "/" + GIVE_UP_AFTER + "; retrying in 3 s");
        MAIN.postDelayed(new Runnable() {
            public void run() {
                ensure(c);
            }
        }, RESTART_MS);
    }

    /** Lets the person try the local network again after an automatic fallback. */
    static void reset(Context c) {
        synchronized (LocalHotspot.class) {
            failures = 0;
        }
        CarActions.prefs(c).edit().putBoolean(KEY_FAILED, false).apply();
        settings(c).edit().putInt("native-ap-transport", TRANSPORT_HOTSPOT).apply();
    }

    private static void log(Context c, String s) {
        Log.i(TAG, s);
        try {
            g1.a.a.n("LocalHotspot(BYD): " + s);
        } catch (Throwable ignored) {
        }
    }
}
