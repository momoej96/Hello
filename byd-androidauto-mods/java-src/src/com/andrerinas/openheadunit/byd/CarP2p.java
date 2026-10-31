package com.andrerinas.openheadunit.byd;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.net.wifi.WifiInfo;
import android.net.wifi.WifiManager;
import android.os.Handler;
import android.os.Looper;
import android.util.Log;

import java.lang.ref.WeakReference;
import java.lang.reflect.Field;
import java.lang.reflect.Method;

/**
 * Keeps Android Auto's WiFi Direct group on the channel the car's Wi-Fi radio is already using.
 *
 * The Qin Plus DM-i's radio can't serve two channels at once. Log of 2026-10-29: the group was
 * made at 09:46:48 while the car's Wi-Fi was still unconnected; at 09:47:00 the car joined a
 * network on channel 6. The phone then failed to join seven times in a row (-11). At 09:51:49
 * DiAuto's watchdog finally recreated the group, it came up on the car's channel, and the phone
 * joined within 4 s. The watchdog had held back for four minutes, because the phone retries
 * every ~41 s and stays in a handshake for 35 s of each.
 *
 * So: the group uses the car Wi-Fi's channel when it is connected (otherwise 2.4 GHz channel 6,
 * which every phone scans; the unit has no 5 GHz), the group is recreated as soon as the phone
 * reports it could not join (in the 2 s gap before it tries again), and again whenever the car's
 * Wi-Fi moves to another channel while no session is running.
 */
public final class CarP2p {
    private static final String TAG = "DiAuto-CarP2p";
    public static final String KEY = "p2p_channel_v2";
    /** 0 = follow the car's Wi-Fi (else 6); -1 = DiAuto's own choice; otherwise a fixed channel. */
    public static final int[] CHANNELS = {0, 1, 6, 11, -1};
    static final int DEFAULT = 0;
    static final int FALLBACK = 6;
    private static final long WIFI_SETTLE_MS = 3000;

    private static final Handler MAIN = new Handler(Looper.getMainLooper());
    private static volatile WeakReference<Object> manager = new WeakReference<Object>(null);
    private static volatile int groupChannel;
    private static boolean receiverOn;
    private static Runnable pendingRecreate;

    private CarP2p() {}

    static String name(int ch) {
        if (ch == 0) return "Follow car Wi-Fi (else channel 6)";
        if (ch < 0) return "DiAuto's own choice";
        return "2.4 GHz · channel " + ch;
    }

    static Context app() {
        try {
            Class<?> at = Class.forName("android.app.ActivityThread");
            return (Context) at.getMethod("currentApplication").invoke(null);
        } catch (Throwable t) {
            return null;
        }
    }

    private static int pref(Context c) {
        return c == null ? DEFAULT : CarActions.prefs(c).getInt(KEY, DEFAULT);
    }

    /** Channel of the car's own Wi-Fi connection, or 0 when it isn't connected. */
    static int stationChannel(Context c) {
        try {
            WifiManager wm = (WifiManager) c.getApplicationContext().getSystemService(Context.WIFI_SERVICE);
            WifiInfo info = wm == null ? null : wm.getConnectionInfo();
            if (info == null || info.getNetworkId() == -1) return 0;
            int mhz = ((Number) WifiInfo.class.getMethod("getFrequency").invoke(info)).intValue();
            return toChannel(mhz);
        } catch (Throwable t) {
            return 0;
        }
    }

    static int toChannel(int mhz) {
        if (mhz == 2484) return 14;
        if (mhz >= 2412 && mhz <= 2472) return (mhz - 2407) / 5;
        if (mhz >= 5000 && mhz <= 5900) return (mhz - 5000) / 5;
        return 0;
    }

    /**
     * Called where DiAuto picks the group's operating channel (WifiDirectManager, below
     * Android 10). {@code wifiDirectManager} is that y0.l2 instance.
     */
    public static int channel(int diAutoChoice, Object wifiDirectManager) {
        try {
            Context c = app();
            if (wifiDirectManager != null) manager = new WeakReference<Object>(wifiDirectManager);
            watchWifi(c);
            int p = pref(c);
            int ch;
            String why;
            if (p < 0) {
                ch = diAutoChoice;
                why = "DiAuto's own choice";
            } else if (p > 0) {
                ch = p;
                why = "fixed in BYD car controls";
            } else {
                int sta = c == null ? 0 : stationChannel(c);
                ch = sta > 0 ? sta : FALLBACK;
                why = sta > 0 ? "same channel as the car's Wi-Fi" : "car Wi-Fi not connected";
            }
            groupChannel = ch;
            log("WiFi Direct group on channel " + ch + " (" + why + ")");
            return ch;
        } catch (Throwable t) {
            return diAutoChoice;
        }
    }

    /** NativeAA logs "Handshake failed — ..." here. A join failure gets a fresh group at once. */
    public static void handshakeFailed(String message) {
        try {
            if (message == null || !message.contains("join failure")) return;
            if (pref(app()) < 0) return;
            recreate("the phone could not join", 0);
        } catch (Throwable ignored) {
        }
    }

    private static synchronized void watchWifi(Context c) {
        if (receiverOn || c == null) return;
        receiverOn = true;
        IntentFilter f = new IntentFilter(WifiManager.NETWORK_STATE_CHANGED_ACTION);
        c.getApplicationContext().registerReceiver(new BroadcastReceiver() {
            public void onReceive(Context ctx, Intent i) {
                stationChanged(ctx);
            }
        }, f);
    }

    static void stationChanged(Context c) {
        if (pref(c) != 0 || manager.get() == null || groupChannel == 0) return;
        int sta = stationChannel(c);
        int want = sta > 0 ? sta : FALLBACK;
        if (want == groupChannel) return;
        recreate("the car's Wi-Fi is now on channel " + (sta > 0 ? sta : 0), WIFI_SETTLE_MS);
    }

    private static synchronized void recreate(final String reason, long delayMs) {
        if (pendingRecreate != null) MAIN.removeCallbacks(pendingRecreate);
        pendingRecreate = new Runnable() {
            public void run() {
                synchronized (CarP2p.class) {
                    pendingRecreate = null;
                }
                recreateNow(reason);
            }
        };
        MAIN.postDelayed(pendingRecreate, delayMs);
    }

    /** Calls WifiDirectManager.S0 (DiAuto's own "recover the Native AA group"), keeping it from giving up. */
    static void recreateNow(String reason) {
        Object m = manager.get();
        if (m == null) return;
        if (AapGuard.sessionActive()) {
            log("not recreating the group (" + reason + "): Android Auto is connected");
            return;
        }
        try {
            Field g = m.getClass().getDeclaredField("G");
            g.setAccessible(true);
            if (g.getInt(m) >= 3) g.setInt(m, 0);
        } catch (Throwable ignored) {
        }
        try {
            Method s0 = m.getClass().getDeclaredMethod("S0", String.class);
            s0.setAccessible(true);
            log("recreating the WiFi Direct group: " + reason);
            s0.invoke(m, reason);
        } catch (Throwable t) {
            Log.w(TAG, "could not recreate the group", t);
        }
    }

    private static void log(String s) {
        Log.i(TAG, s);
        try {
            g1.a.a.n("CarP2p: " + s);
        } catch (Throwable ignored) {
        }
    }
}
