package com.andrerinas.openheadunit.byd;

import android.content.Context;
import android.content.SharedPreferences;
import android.os.Build;
import android.util.Log;

/**
 * Settings for the BYD Qin Plus DM-i (MT6765, Android 9): connect over Wi-Fi by itself, starting with the car.
 *
 * Every start: the Native AA transport is the head unit hotspot, which LocalHotspot fills with the
 * car's own local-only network, and the "5 GHz on Android 9" requests are off (the unit has no
 * 5 GHz). A fallback to WiFi Direct after the car refused the local network lasts until the next
 * start only, so every start tries the local network first again.
 * Once: SurfaceView (TextureView showed 23 of 85 decoded frames), 30 fps, and auto-start on
 * boot / screen-on, so getting in the car is enough.
 */
public final class CarDefaults {
    private static final String TAG = "DiAuto-CarDefaults";
    private static final String DONE_V1 = "car_defaults_v1";
    private static final String DONE_V2 = "car_defaults_v2";

    private CarDefaults() {}

    /** Called first thing in App.onCreate. */
    public static void apply(Context c) {
        StatusLine.attach(c);
        try {
            SharedPreferences mine = CarActions.prefs(c);
            mine.edit().putBoolean(LocalHotspot.KEY_FAILED, false).apply();
            SharedPreferences.Editor s = c.getSharedPreferences("settings", 0).edit();
            s.putInt("native-ap-transport", LocalHotspot.TRANSPORT_HOTSPOT)
                    .putBoolean("p2p-legacy-5ghz", false)
                    .putBoolean("p2p-legacy-5ghz-upper", false);
            if (!mine.getBoolean(DONE_V1, false)) {
                s.putInt("view-mode", 0).putInt("fps-limit", 30);
            }
            s.apply();
            if (!mine.getBoolean(DONE_V2, false)) {
                autoStart(c);
                mine.edit().putBoolean(DONE_V1, true).putBoolean(DONE_V2, true).apply();
                Log.i(TAG, "applied: car local network, no 5 GHz, SurfaceView, 30 fps, auto-start on boot and screen-on");
            }
        } catch (Throwable ignored) {
        }
    }

    private static void autoStart(Context c) {
        Context store = c;
        try {
            if (Build.VERSION.SDK_INT >= 24) {
                store = (Context) Context.class.getMethod("createDeviceProtectedStorageContext").invoke(c);
            }
        } catch (Throwable ignored) {
        }
        String name = store != c ? "settings_device_protected" : "settings";
        store.getSharedPreferences(name, 0).edit()
                .putBoolean("auto-start-on-boot", true)
                .putBoolean("auto-start-on-screen-on", true)
                .apply();
    }
}
