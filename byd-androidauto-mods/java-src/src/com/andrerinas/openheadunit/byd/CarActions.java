package com.andrerinas.openheadunit.byd;

import android.content.Context;
import android.content.SharedPreferences;
import android.os.Handler;
import android.os.Looper;
import android.widget.Toast;

/**
 * Shared helpers for the mod's classes: its prefs, toasts and the ADB shell. The car controls
 * (keys, AC, climate screen) that used to live here were removed in mod9.
 */
public final class CarActions {
    /** Kept from mod1-mod8 so values saved by earlier builds (ADB port, hotspot state) carry over. */
    static final String PREFS = "byd_car_controls";

    private static final Handler MAIN = new Handler(Looper.getMainLooper());

    private CarActions() {}

    static SharedPreferences prefs(Context c) {
        return c.getSharedPreferences(PREFS, 0);
    }

    public static void toast(final Context c, final String text) {
        MAIN.post(new Runnable() {
            public void run() {
                try {
                    Toast.makeText(c.getApplicationContext(), text, Toast.LENGTH_SHORT).show();
                } catch (Throwable ignored) {
                }
            }
        });
    }

    static String adb(Context c, String command) {
        try {
            return LocalAdb.shell(c, command);
        } catch (Throwable t) {
            return null;
        }
    }
}
