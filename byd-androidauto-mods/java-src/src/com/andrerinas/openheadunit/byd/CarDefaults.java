package com.andrerinas.openheadunit.byd;

import android.content.Context;
import android.content.SharedPreferences;
import android.util.Log;

/**
 * One-time settings for the BYD Qin Plus DM-i (MT6765, Android 9), from its log: SurfaceView
 * (TextureView showed 23 of 85 decoded frames) and a 30 fps limit (half the data over the
 * shared Wi-Fi radio). Applied once; the person can change them back in DiAuto's settings.
 */
public final class CarDefaults {
    private static final String DONE = "car_defaults_v1";

    private CarDefaults() {}

    /** Called first thing in App.onCreate. */
    public static void apply(Context c) {
        try {
            SharedPreferences mine = CarActions.prefs(c);
            AvBuffer.load(c);
            if (mine.getBoolean(DONE, false)) return;
            c.getSharedPreferences("settings", 0).edit()
                    .putInt("view-mode", 0)
                    .putInt("fps-limit", 30)
                    .apply();
            mine.edit().putBoolean(DONE, true).apply();
            Log.i("DiAuto-CarDefaults", "applied: SurfaceView, 30 fps");
        } catch (Throwable ignored) {
        }
    }
}
