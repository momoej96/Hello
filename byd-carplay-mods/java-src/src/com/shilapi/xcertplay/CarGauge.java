package com.shilapi.xcertplay;

import android.content.Context;
import android.os.Handler;
import android.os.Looper;
import android.widget.LinearLayout;
import android.widget.TextView;

import java.util.ArrayList;
import java.util.Arrays;

import kotlin.jvm.functions.Function0;
import kotlin.jvm.functions.Function1;

/**
 * What the dashboard-map gauge shows: engine water temperature (default) or speed.
 * The temperature comes from BYDAutoStatisticDevice.getWaterTemperature(), the same
 * source Diplus uses for its "发动机水温" reading. It is read in DiPlay's process when
 * BYD allows it, otherwise as the shell user over ADB, at most every 2 seconds.
 */
public final class CarGauge {
    static final String KEY = "cluster_gauge";
    static final int WATER = 0;
    static final int SPEED = 1;
    private static final String[] NAMES = {"Engine water temperature", "Speed"};
    private static final long REFRESH_MS = 2000;
    private static final Handler MAIN = new Handler(Looper.getMainLooper());

    private static volatile Integer cached;
    private static volatile long cachedAt;
    private static volatile boolean fetching;
    private static volatile boolean shellWorks;
    private static volatile String status = "Water temperature: not read yet";

    private CarGauge() {}

    public static boolean showsWaterTemp(Context c) {
        try {
            return CarActions.prefs(c).getInt(KEY, WATER) == WATER;
        } catch (Throwable t) {
            return false;
        }
    }

    public static String unit(Context c) {
        return showsWaterTemp(c) ? "°C" : "km/h";
    }

    /** Raw value from the car; throws when it can't be read. Used in-app and by CarAcShell. */
    static int readRaw(Context c) throws Exception {
        Object dev = Class.forName("android.hardware.bydauto.statistic.BYDAutoStatisticDevice")
                .getMethod("getInstance", Context.class)
                .invoke(null, c instanceof PermissiveContext ? c : new PermissiveContext(c));
        if (dev == null) throw new IllegalStateException("no statistic device");
        Object r = dev.getClass().getMethod("getWaterTemperature").invoke(dev);
        if (!(r instanceof Number)) throw new IllegalStateException("no value");
        return ((Number) r).intValue();
    }

    private static Integer usable(int raw) {
        return (raw < -40 || raw > 150) ? null : Integer.valueOf(raw);
    }

    /** Latest engine water temperature in °C, or null; never blocks the caller. */
    public static Integer waterTemp(Context c) {
        if (System.currentTimeMillis() - cachedAt > REFRESH_MS) refreshAsync(c, null);
        return cached;
    }

    static void refreshAsync(final Context context, final Runnable done) {
        if (fetching) return;
        fetching = true;
        final Context c = context.getApplicationContext();
        new Thread(new Runnable() {
            public void run() {
                try {
                    refreshNow(c);
                } finally {
                    fetching = false;
                    cachedAt = System.currentTimeMillis();
                    if (done != null) MAIN.post(done);
                }
            }
        }, "DiPlay-WaterTemp").start();
    }

    // ---- direct service call, the way DiPlay already reads speed and gear ----

    private static volatile int fid = Integer.MIN_VALUE;
    private static volatile String fidName;
    private static volatile int[] devTypes;

    /** Finds the water-temperature feature id by name in the car's BYDAutoFeatureIds. */
    private static void discover(Context c) {
        if (fid != Integer.MIN_VALUE) return;
        try {
            Class<?> ids = Class.forName("android.hardware.bydauto.BYDAutoFeatureIds");
            java.util.List<Class<?>> classes = new java.util.ArrayList<Class<?>>();
            classes.add(ids);
            classes.addAll(Arrays.asList(ids.getClasses()));
            String best = null;
            int bestVal = 0;
            int bestScore = -1;
            for (Class<?> k : classes) {
                for (java.lang.reflect.Field f : k.getFields()) {
                    String n = f.getName().toUpperCase();
                    if (f.getType() != int.class || !n.contains("WATER") || !n.contains("TEMP")) continue;
                    int score = (n.contains("STATISTIC") ? 2 : 0) + (n.contains("ENGINE") ? 1 : 0);
                    if (score > bestScore) {
                        bestScore = score;
                        best = k.getSimpleName() + "." + f.getName();
                        bestVal = f.getInt(null);
                    }
                }
            }
            if (best != null) {
                fid = bestVal;
                fidName = best;
            }
        } catch (Throwable ignored) {
        }
        java.util.LinkedHashSet<Integer> types = new java.util.LinkedHashSet<Integer>();
        try {
            Object dev = Class.forName("android.hardware.bydauto.statistic.BYDAutoStatisticDevice")
                    .getMethod("getInstance", Context.class)
                    .invoke(null, new PermissiveContext(c.getApplicationContext()));
            for (Class<?> k = dev.getClass(); k != null && k != Object.class; k = k.getSuperclass()) {
                for (java.lang.reflect.Field f : k.getDeclaredFields()) {
                    if (f.getType() != int.class || java.lang.reflect.Modifier.isStatic(f.getModifiers())) continue;
                    f.setAccessible(true);
                    int v = f.getInt(dev);
                    if (v >= 1000 && v <= 1100) types.add(Integer.valueOf(v));
                }
            }
        } catch (Throwable ignored) {
        }
        types.add(Integer.valueOf(1014));
        int[] out = new int[types.size()];
        int i = 0;
        for (Integer v : types) out[i++] = v.intValue();
        devTypes = out;
    }

    /** Second 32-bit word of a "Result: Parcel(00000000 00000055 ...)" reply, or null. */
    private static Integer parcelInt(String out) {
        if (out == null) return null;
        int a = out.indexOf("Parcel(");
        if (a < 0) return null;
        String[] words = out.substring(a + 7).trim().split("\\s+");
        if (words.length < 2) return null;
        try {
            if (Long.parseLong(words[0], 16) != 0) return null;
            return Integer.valueOf((int) Long.parseLong(words[1], 16));
        } catch (NumberFormatException e) {
            return null;
        }
    }

    /** Returns a status suffix on failure, or null after storing a reading. */
    private static String serviceRoute(Context c) {
        discover(c);
        if (fid == Integer.MIN_VALUE) return "no WATER_TEMP id in this firmware";
        StringBuilder why = new StringBuilder(fidName + "=" + fid);
        for (int dev : devTypes) {
            Integer raw = parcelInt(CarActions.adb(c, "service call autoservice 5 i32 " + dev + " i32 " + fid));
            if (raw != null && isTemperature(raw.intValue())) {
                cached = raw;
                status = "Water temperature: " + raw + " °C (service " + dev + ", " + fidName + ")";
                return null;
            }
            why.append(" · ").append(dev).append("→").append(raw == null ? "no value" : String.valueOf(raw));
        }
        return why.toString();
    }

    private static volatile boolean granted;

    /** BYD answers with negative codes (e.g. -10011) instead of throwing when access is refused. */
    private static boolean isTemperature(int raw) {
        return raw >= -40 && raw <= 150;
    }

    private static void grantStatistic(Context c) {
        String pkg = c.getPackageName();
        CarActions.adb(c, "pm grant " + pkg + " android.permission.BYDAUTO_STATISTIC_COMMON 2>&1; pm grant "
                + pkg + " android.permission.BYDAUTO_STATISTIC_GET 2>&1; echo DONE");
    }

    private static void refreshNow(Context c) {
        String inApp = null;
        if (!shellWorks) {
            try {
                int raw = readRaw(c.getApplicationContext());
                if (!isTemperature(raw) && !granted) {
                    granted = true;
                    grantStatistic(c);
                    raw = readRaw(c.getApplicationContext());
                }
                if (isTemperature(raw)) {
                    cached = Integer.valueOf(raw);
                    status = "Water temperature: " + raw + " °C (read in app)";
                    return;
                }
                inApp = "car code " + raw;
            } catch (Throwable t) {
                inApp = CarAc.reason(t);
            }
        }
        String service = serviceRoute(c);
        if (service == null) return;
        String apk = c.getApplicationInfo().sourceDir;
        String out = CarActions.adb(c, "CLASSPATH=" + apk + " app_process /system/bin "
                + CarAcShell.class.getName() + " water 0 0 2>&1");
        String line = null;
        if (out != null) {
            for (String l : out.split("\n")) if (l.startsWith("CARAC|")) line = l.trim();
        }
        String adbWhy;
        if (line != null) {
            String[] f = line.split("\\|");
            if (f.length >= 3 && "OK".equals(f[1])) {
                try {
                    int raw = Integer.parseInt(f[2].trim());
                    if (isTemperature(raw)) {
                        shellWorks = true;
                        cached = Integer.valueOf(raw);
                        status = "Water temperature: " + raw + " °C (read over ADB)";
                        return;
                    }
                    adbWhy = "car code " + raw;
                } catch (NumberFormatException e) {
                    adbWhy = f[2];
                }
            } else {
                adbWhy = f.length > 2 ? f[2] : line;
            }
        } else {
            adbWhy = out == null ? "not available" : "no answer";
        }
        shellWorks = false;
        cached = null;
        status = "Water temperature: no reading. App: " + inApp + " · Service: " + service + " · Shell: " + adbWhy;
    }

    public static void settings(final DiPlayActivity a, LinearLayout card) {
        try {
            DiPlayActivity.choice$default(a, card, "Gauge shows",
                    new ArrayList<String>(Arrays.asList(NAMES)),
                    showsWaterTemp(a) ? WATER : SPEED, false, false, false,
                    new Function1() {
                        public Object invoke(Object p) {
                            CarActions.prefs(a).edit().putInt(KEY, ((Number) p).intValue()).apply();
                            return kotlin.Unit.INSTANCE;
                        }
                    }, 0x60, null);
            final TextView note = DiPlayActivity.diplayNote(a, card, status);
            final Runnable show = new Runnable() {
                public void run() {
                    if (note != null) note.setText(status);
                }
            };
            DiPlayActivity.diplayButton(a, card, "Check water temperature", new Function0() {
                public Object invoke() {
                    if (note != null) note.setText("Water temperature: reading…");
                    shellWorks = false;
                    granted = false;
                    refreshAsync(a, show);
                    return kotlin.Unit.INSTANCE;
                }
            });
        } catch (Throwable ignored) {
        }
    }
}
