package com.shilapi.xcertplay;

import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.os.Handler;
import android.os.Looper;
import android.widget.Toast;

import com.shilapi.xcertplay.hud.BydAdbShell;

import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;

/** Car functions run from wheel-key slots. AC calls mirror Diplus (BYDAutoAcDevice). */
public final class CarActions {
    public static final int NONE = 0;
    public static final int AC_POWER = 1;
    public static final int AC_AUTO = 2;
    public static final int AC_RECIRC = 3;
    public static final int AC_DEFROST = 4;
    public static final int CLIMATE_SCREEN = 5;
    public static final int CLIMATE_APP = 6;

    /** Order matters: saved settings keep the index, so new actions are only appended. */
    public static final String[] NAMES = {
        "None",
        "AC on / off",
        "AC Auto on / off",
        "Recirculation inside / outside",
        "Windscreen defrost",
        "Open climate screen",
        "Open climate app",
        "AC on (Auto)",
        "AC off",
        "Temperature up",
        "Temperature down",
        "Fan speed up",
        "Fan speed down",
        "Recirculation: inside",
        "Recirculation: outside air",
        "Fan only on / off",
        "Fan only on",
        "Fan only off",
        "Airflow: face",
        "Airflow: face + feet",
        "Airflow: feet",
        "Airflow: feet + defrost",
        "Airflow: face + feet + defrost",
        "Airflow: face + defrost",
        "Music: play / pause",
        "Music: next song",
        "Music: previous song",
    };

    /** First index of the media actions and their Android media key codes (85, 87, 88). */
    private static final int MEDIA_FIRST = 24;
    private static final int[] MEDIA_KEYS = {85, 87, 88};

    /** AC command per action index (null = not an AC command). */
    private static final String[] AC_CMD = {
        null, "power", "auto", "recirc", "defrost", null, null,
        "on", "off", "tempup", "tempdown", "fanup", "fandown", "in", "out",
        "vent", "venton", "ventoff",
        "wind1", "wind2", "wind3", "wind4", "wind6", "wind7",
    };

    public static final String[] AC_PERMISSIONS = {
        "android.permission.BYDAUTO_AC_COMMON",
        "android.permission.BYDAUTO_AC_GET",
        "android.permission.BYDAUTO_AC_SET",
    };

    static final String PREFS = "diplay_audio";
    static final String KEY_SCREEN = "climate_screen";
    private static final String KEY_PREV_WIND = "carkey_prev_wind";
    private static final String KEY_LAST_AUTO = "carkey_last_auto";

    private static final Handler MAIN = new Handler(Looper.getMainLooper());
    private static BydAdbShell shell;

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

    static synchronized String adb(Context c, String command) {
        try {
            if (shell == null) shell = new BydAdbShell("DiPlay-CarKeys");
            return shell.run(c.getApplicationContext(), command);
        } catch (Throwable t) {
            return null;
        }
    }

    /** Runs an action on a worker thread; never throws. */
    public static void run(final Context context, final int action) {
        final Context c = context.getApplicationContext();
        Thread t = new Thread(new Runnable() {
            public void run() {
                try {
                    runNow(c, action);
                } catch (Throwable e) {
                    toast(c, "Car command failed");
                }
            }
        }, "DiPlay-CarAction");
        t.start();
    }

    static void runNow(Context c, int action) throws Exception {
        if (action == CLIMATE_SCREEN) {
            openScreen(c);
        } else if (action == CLIMATE_APP) {
            ClimateShortcut.openApp(c);
        } else if (action >= MEDIA_FIRST && action < MEDIA_FIRST + MEDIA_KEYS.length) {
            mediaKey(c, MEDIA_KEYS[action - MEDIA_FIRST]);
        } else if (action > 0 && action < AC_CMD.length && AC_CMD[action] != null) {
            acRun(c, AC_CMD[action]);
        }
    }

    // ---- music ----

    /** Sends a media key to whatever player is active (CarPlay audio, a music app), like a headset button. */
    private static void mediaKey(Context c, int code) throws Exception {
        Object am = c.getSystemService(Context.AUDIO_SERVICE);
        Method m = am.getClass().getMethod("dispatchMediaKeyEvent", android.view.KeyEvent.class);   // API 19+, hidden from the old compile jar
        long now = android.os.SystemClock.uptimeMillis();
        m.invoke(am, new android.view.KeyEvent(now, now, android.view.KeyEvent.ACTION_DOWN, code, 0));
        m.invoke(am, new android.view.KeyEvent(now, now + 40, android.view.KeyEvent.ACTION_UP, code, 0));
    }

    // ---- BYD AC ----

    /**
     * Runs an AC command as the shell user over ADB (BYD refuses AC_GET/AC_SET to apps);
     * falls back to calling it in-process when ADB is unavailable.
     */
    private static void acRun(Context c, String cmd) {
        SharedPreferences p = prefs(c);
        int prev = p.getInt(KEY_PREV_WIND, -1);
        int last = p.getInt(KEY_LAST_AUTO, 1);
        // 1) In DiPlay's own process: quickest, no ADB round trip.
        String inApp;
        try {
            String[] r = CarAc.run(c, cmd, prev, last);
            p.edit().putInt(KEY_PREV_WIND, parse(r[1], prev)).putInt(KEY_LAST_AUTO, parse(r[2], last)).apply();
            toast(c, r[0]);
            return;
        } catch (Throwable t) {
            inApp = CarAc.reason(t);
        }
        // 2) As the shell user over ADB, the way DiPlay's other car tools run.
        String apk = c.getApplicationInfo().sourceDir;
        String out = adb(c, "CLASSPATH=" + apk + " app_process /system/bin "
                + CarAcShell.class.getName() + " " + cmd + " " + prev + " " + last + " 2>&1");
        String line = null;
        if (out != null) {
            for (String l : out.split("\n")) {
                if (l.startsWith("CARAC|")) line = l.trim();
            }
        }
        if (line != null) {
            String[] f = line.split("\\|");
            if (f.length >= 5 && "OK".equals(f[1])) {
                p.edit().putInt(KEY_PREV_WIND, parse(f[3], prev)).putInt(KEY_LAST_AUTO, parse(f[4], last)).apply();
                toast(c, f[2]);
                return;
            }
            toast(c, "AC command failed: " + inApp + " / shell: " + (f.length > 2 ? f[2] : line));
            return;
        }
        toast(c, "AC command failed: " + inApp + (out == null ? " / ADB not available" : ""));
    }

    private static int parse(String s, int fallback) {
        try {
            return Integer.parseInt(s.trim());
        } catch (Throwable t) {
            return fallback;
        }
    }

    // ---- climate screen ----

    /** BYD's own climate screen, used when nothing was captured. */
    static final String BYD_CLIMATE = "com.byd.airconditioning/.mainactivity.FullScreenMainActivity";

    static String defaultScreen(Context c) {
        try {
            ComponentName cn = ComponentName.unflattenFromString(BYD_CLIMATE);
            c.getPackageManager().getActivityInfo(cn, 0);
            return BYD_CLIMATE;
        } catch (Throwable t) {
            return null;
        }
    }

    private static void openScreen(Context c) {
        String comp = prefs(c).getString(KEY_SCREEN, "");
        if (comp == null || comp.length() == 0) comp = defaultScreen(c);
        if (comp == null || comp.length() == 0) {
            toast(c, "Capture the climate screen in Settings first");
            return;
        }
        ComponentName cn = ComponentName.unflattenFromString(comp);
        if (cn == null) {
            toast(c, "Capture the climate screen again");
            return;
        }
        try {
            Intent i = new Intent();
            i.setComponent(cn);
            i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            c.startActivity(i);
            toast(c, "Opening climate");
            return;
        } catch (Throwable ignored) {
        }
        // Not exported to other apps: start it from the shell instead.
        String out = adb(c, "am start -n " + cn.flattenToShortString());
        if (out != null && !out.contains("Error")) {
            toast(c, "Opening climate");
        } else {
            toast(c, "Couldn't open the climate screen");
        }
    }

    /**
     * Reads the most recent task that is not DiPlay from the recents list and returns its
     * activity as package/class, or null.
     */
    public static String captureScreen(Context c) {
        String out = adb(c, "dumpsys activity recents");
        if (out == null || out.length() == 0) return null;
        String self = c.getPackageName();
        String[] blocks = out.split("Recent #");
        for (int b = 1; b < blocks.length; b++) {
            String comp = component(blocks[b]);
            if (comp == null) continue;
            if (comp.startsWith(self + "/")) continue;
            return comp;
        }
        return null;
    }

    private static String component(String block) {
        String[] keys = {"realActivity=", "cmp="};
        for (String key : keys) {
            int i = block.indexOf(key);
            if (i < 0) continue;
            int s = i + key.length();
            int e = s;
            while (e < block.length()) {
                char ch = block.charAt(e);
                if (ch == ' ' || ch == '}' || ch == '\n' || ch == '\r' || ch == ',') break;
                e++;
            }
            String comp = block.substring(s, e).trim();
            if (comp.indexOf('/') > 0) {
                ComponentName cn = ComponentName.unflattenFromString(comp);
                if (cn != null) return cn.flattenToShortString();
            }
        }
        return null;
    }

    // ---- permission ----

    private static int checkPermission(Context c, String p) {
        try {
            Method m = Context.class.getMethod("checkSelfPermission", String.class);
            Object r = m.invoke(c, p);
            return r instanceof Integer ? ((Integer) r).intValue() : -1;
        } catch (Throwable t) {
            return -1;
        }
    }

    public static boolean acAllowed(Context c) {
        return checkPermission(c, AC_PERMISSIONS[0]) == 0;
    }

    /** One line per permission, e.g. "AC_COMMON ✓  AC_GET ✓  AC_SET ✗". */
    public static String acStatus(Context c) {
        StringBuilder b = new StringBuilder();
        for (String p : AC_PERMISSIONS) {
            if (b.length() > 0) b.append("   ");
            b.append(p.substring(p.indexOf("BYDAUTO_") + 8));
            b.append(checkPermission(c, p) == 0 ? " ✓" : " ✗");
        }
        return b.toString();
    }

    /** Grants the AC permissions from the ADB shell. Returns the shell's complaints, or "" when all went through. */
    public static String grantAc(Context c) {
        StringBuilder problems = new StringBuilder();
        String pkg = c.getPackageName();
        for (String p : AC_PERMISSIONS) {
            String out = adb(c, "pm grant " + pkg + " " + p + " 2>&1; echo DONE");
            if (out == null) {
                return "ADB not available";
            }
            String o = out.replace("DONE", "").trim();
            if (o.length() > 0 && checkPermission(c, p) != 0) {
                if (problems.length() > 0) problems.append(" | ");
                problems.append(p.substring(p.indexOf("BYDAUTO_") + 8)).append(": ")
                        .append(o.length() > 70 ? o.substring(0, 70) : o);
            }
        }
        return problems.toString();
    }

    public static void requestAc(android.app.Activity a) {
        try {
            Method m = android.app.Activity.class.getMethod(
                    "requestPermissions", String[].class, int.class);
            m.invoke(a, (Object) AC_PERMISSIONS, Integer.valueOf(0x5a1));
        } catch (Throwable t) {
            openAppInfo(a);
        }
    }

    public static void openAppInfo(Context c) {
        try {
            Intent i = new Intent("android.settings.APPLICATION_DETAILS_SETTINGS");
            i.setData(android.net.Uri.parse("package:" + c.getPackageName()));
            i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            c.startActivity(i);
        } catch (Throwable ignored) {
        }
    }
}
