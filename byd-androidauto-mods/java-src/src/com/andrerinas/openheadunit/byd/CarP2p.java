package com.andrerinas.openheadunit.byd;

import android.content.Context;
import android.util.Log;

/**
 * WiFi Direct operating channel for Android 9 units.
 *
 * Third car log (Qin Plus DM-i, no phone hotspot): the car's Wi-Fi station was off, the group came
 * up on a channel the driver chose (Android 9 doesn't report which), and the S24 failed to join it
 * every time (WifiConnectStatus -11, 5 tries in 4 minutes). With the phone's hotspot on, the
 * station sat on 2.4 GHz channel 1/11 and the group followed it there, and the phone joined at
 * once. So the group is pinned to a 2.4 GHz channel the phone always scans. DiAuto already
 * requests an operating channel this way (setWifiP2pChannels) for its "5 GHz on Android 9"
 * option, and falls back to the driver's choice by itself if the unit refuses.
 */
public final class CarP2p {
    public static final String KEY = "p2p_channel";
    /** 0 = DiAuto's own choice. */
    public static final int[] CHANNELS = {0, 1, 6, 11, 36, 40, 44, 48, 149};
    static final int DEFAULT = 6;

    private CarP2p() {}

    /** Called where DiAuto picks the operating channel; returns ours when one is set. */
    public static int channel(int diAutoChoice) {
        try {
            Class<?> at = Class.forName("android.app.ActivityThread");
            Context c = (Context) at.getMethod("currentApplication").invoke(null);
            int ch = c == null ? DEFAULT : CarActions.prefs(c).getInt(KEY, DEFAULT);
            if (ch <= 0) return diAutoChoice;
            Log.i("DiAuto-CarP2p", "WiFi Direct operating channel " + ch + " (DiAuto would use " + diAutoChoice + ")");
            return ch;
        } catch (Throwable t) {
            return diAutoChoice;
        }
    }

    static String name(int ch) {
        if (ch == 0) return "Automatic (DiAuto)";
        return (ch <= 14 ? "2.4 GHz" : "5 GHz") + " · channel " + ch;
    }
}
