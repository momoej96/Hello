package com.shilapi.xcertplay;

import android.content.ComponentName;
import android.content.Context;
import android.content.pm.PackageManager;
import android.provider.Settings;
import android.util.Log;

import java.text.SimpleDateFormat;
import java.util.ArrayList;
import java.util.Date;
import java.util.List;
import java.util.Locale;

/**
 * Evidence and repair helpers for the car keys service.
 *
 * - A small persistent history (it survives process death) that is also appended to the diagnostic report.
 * - Writing enabled_accessibility_services in-process once WRITE_SECURE_SETTINGS is granted (Diplus does the
 *   same), so the service can be re-bound without depending on ADB at that moment.
 * - Snapshots of what the system thinks about the service, and of how the previous process ended.
 */
public final class CarGuard {
    private static final String TAG = "DiPlay-CarGuard";
    private static final String KEY_HISTORY = "carguard_history";
    private static final String KEY_ALIVE = "carguard_alive";
    private static final int MAX_LINES = 40;
    static final String SECURE_PERMISSION = "android.permission.WRITE_SECURE_SETTINGS";
    private static final String ENABLED = "enabled_accessibility_services";

    static volatile Context appContext;

    private CarGuard() {}

    private static String clock(long ms) {
        return new SimpleDateFormat("HH:mm:ss", Locale.US).format(new Date(ms));
    }

    // ---- history ----

    public static synchronized void log(Context c, String text) {
        try {
            Log.i(TAG, text);
            List<String> lines = history(c);
            String line = clock(System.currentTimeMillis()) + " " + text;
            if (!lines.isEmpty()) {
                String last = lines.get(lines.size() - 1);
                int sp = last.indexOf(' ');
                if (sp > 0 && last.substring(sp + 1).equals(text)) return;   // same message again
            }
            lines.add(line);
            while (lines.size() > MAX_LINES) lines.remove(0);
            StringBuilder b = new StringBuilder();
            for (String l : lines) {
                if (b.length() > 0) b.append('\n');
                b.append(l);
            }
            CarActions.prefs(c).edit().putString(KEY_HISTORY, b.toString()).commit();
        } catch (Throwable ignored) {
        }
    }

    public static List<String> history(Context c) {
        List<String> out = new ArrayList<String>();
        try {
            String s = CarActions.prefs(c).getString(KEY_HISTORY, "");
            if (s != null && s.length() > 0) {
                for (String l : s.split("\n")) if (l.length() > 0) out.add(l);
            }
        } catch (Throwable ignored) {
        }
        return out;
    }

    /** Called from WheelKeyLog.report: adds our history to the diagnostic report. */
    @SuppressWarnings({"unchecked", "rawtypes"})
    public static void extraReport(List out) {
        try {
            Context c = appContext;
            if (c == null) return;
            out.add("Wheel keys: guard history (kept across restarts, newest last)");
            for (String l : history(c)) out.add("Wheel keys: guard " + l);
        } catch (Throwable ignored) {
        }
    }

    // ---- how the previous process ended ----

    /** Heartbeat, called every watchdog tick. */
    static void alive(Context c) {
        try {
            CarActions.prefs(c).edit().putLong(KEY_ALIVE, System.currentTimeMillis()).apply();
        } catch (Throwable ignored) {
        }
    }

    /** Once per process: when the previous process last showed life, and what the system's event log says about its end. */
    static void processStartEvidence(Context c, long processStartedAtMs) {
        long prev = CarActions.prefs(c).getLong(KEY_ALIVE, 0);
        if (prev <= 0) {
            log(c, "Process started " + clock(processStartedAtMs) + " (first run with this check)");
            return;
        }
        long gapMin = (processStartedAtMs - prev) / 60000;
        log(c, "Process started " + clock(processStartedAtMs) + "; the previous one was last alive " + clock(prev)
                + " (" + gapMin + " min earlier)");
        if (gapMin < 1) return;
        String ev = CarActions.adb(c, "logcat -b events -d -v time 2>/dev/null | grep -E 'am_proc_died|am_kill|am_crash|am_anr|am_wtf' | grep -i shihab | tail -n 4");
        if (ev == null) {
            log(c, "Event log: ADB did not answer");
            return;
        }
        boolean any = false;
        for (String l : ev.split("\n")) {
            l = l.trim();
            if (l.length() == 0) continue;
            any = true;
            log(c, "Event log: " + (l.length() > 150 ? l.substring(0, 150) : l));
        }
        if (!any) log(c, "Event log: no kill or death entry for DiPlay (it may have exited by itself)");
    }

    // ---- what the system thinks about the service ----

    static void systemView(Context c, String when) {
        String out = CarActions.adb(c, "dumpsys accessibility | grep -i -E 'shihab|bound services|enabled services|binding services|crashed services' | head -n 12");
        if (out == null) {
            log(c, "Accessibility state (" + when + "): ADB did not answer");
            return;
        }
        int n = 0;
        for (String l : out.split("\n")) {
            l = l.trim();
            if (l.length() == 0) continue;
            log(c, "Accessibility state (" + when + "): " + (l.length() > 150 ? l.substring(0, 150) : l));
            if (++n >= 8) break;
        }
        if (n == 0) log(c, "Accessibility state (" + when + "): dumpsys printed nothing about DiPlay");
    }

    // ---- writing the setting without ADB ----

    static boolean canWriteSecure(Context c) {
        try {
            return c.checkCallingOrSelfPermission(SECURE_PERMISSION) == PackageManager.PERMISSION_GRANTED;
        } catch (Throwable t) {
            return false;
        }
    }

    /** Gives DiPlay WRITE_SECURE_SETTINGS over ADB once (the permission is declared in the manifest). */
    static void ensureSecurePermission(Context c) {
        if (canWriteSecure(c)) return;
        String out = CarActions.adb(c, "pm grant " + c.getPackageName() + " " + SECURE_PERMISSION + " 2>&1; echo DONE");
        if (out == null) return;
        log(c, canWriteSecure(c) ? "Granted itself WRITE_SECURE_SETTINGS"
                : "Could not grant WRITE_SECURE_SETTINGS: " + out.replace("DONE", "").trim());
    }

    private static String selfComponent(Context c) {
        return new ComponentName(c, CarKeysService.class).flattenToString();
    }

    static final String KEY_SERVICE_ON = "carkeys_service_on";

    /** The user's switch for the car keys service (on unless they turned it off). */
    static boolean serviceWanted(Context c) {
        return CarActions.prefs(c).getBoolean(KEY_SERVICE_ON, true);
    }

    private static List<String> enabledList(Context c, String self) {
        List<String> out = new ArrayList<String>();
        String cur = Settings.Secure.getString(c.getContentResolver(), ENABLED);
        if (cur != null) {
            for (String part : cur.split(":")) {
                String s = part.trim();
                if (s.length() == 0 || "null".equals(s)) continue;
                ComponentName cn = ComponentName.unflattenFromString(s);
                if (cn != null && cn.flattenToString().equals(self)) continue;
                out.add(s);
            }
        }
        return out;
    }

    /** True when the car keys service is listed in the system's enabled accessibility services. */
    static boolean enabledInSettings(Context c) {
        try {
            String self = selfComponent(c);
            String cur = Settings.Secure.getString(c.getContentResolver(), ENABLED);
            if (cur == null) return false;
            for (String part : cur.split(":")) {
                ComponentName cn = ComponentName.unflattenFromString(part.trim());
                if (cn != null && cn.flattenToString().equals(self)) return true;
            }
        } catch (Throwable ignored) {
        }
        return false;
    }

    private static String join(List<String> l) {
        StringBuilder b = new StringBuilder();
        for (String s : l) {
            if (b.length() > 0) b.append(':');
            b.append(s);
        }
        return b.toString();
    }

    /**
     * Adds or removes only the car keys service in enabled_accessibility_services (other services,
     * including DiPlay's original wheel-key one and Diplus, are left as they are).
     * Uses WRITE_SECURE_SETTINGS in this process, otherwise the ADB shell. False if neither worked.
     */
    static boolean setServiceEnabled(Context c, boolean on) {
        String self = selfComponent(c);
        try {
            ensureSecurePermission(c);
            if (canWriteSecure(c)) {
                List<String> l = enabledList(c, self);
                if (on) l.add(self);
                boolean ok = Settings.Secure.putString(c.getContentResolver(), ENABLED, join(l));
                if (on) Settings.Secure.putString(c.getContentResolver(), "accessibility_enabled", "1");
                return ok;
            }
        } catch (Throwable t) {
            log(c, "Setting the car keys service failed in the app: " + t.getClass().getSimpleName());
        }
        String current = CarActions.adb(c, "settings get secure enabled_accessibility_services");
        if (current == null) return false;
        List<String> l = new ArrayList<String>();
        for (String part : current.trim().split(":")) {
            String s = part.trim();
            if (s.length() == 0 || "null".equals(s)) continue;
            ComponentName cn = ComponentName.unflattenFromString(s);
            if (cn != null && cn.flattenToString().equals(self)) continue;
            l.add(s);
        }
        if (on) l.add(self);
        return CarActions.adb(c, "settings put secure enabled_accessibility_services '" + join(l) + "'"
                + (on ? "; settings put secure accessibility_enabled 1" : "") + "; echo DONE") != null;
    }

    /** Turns the wheel-key service off and on in the system settings, in this process. False if not allowed to. */
    static boolean toggleAccessibility(Context c) {
        if (!canWriteSecure(c)) return false;
        try {
            String self = selfComponent(c);
            String cur = Settings.Secure.getString(c.getContentResolver(), ENABLED);
            StringBuilder without = new StringBuilder();
            if (cur != null) {
                for (String part : cur.split(":")) {
                    String s = part.trim();
                    if (s.length() == 0 || "null".equals(s)) continue;
                    ComponentName cn = ComponentName.unflattenFromString(s);
                    if (cn != null && cn.flattenToString().equals(self)) continue;
                    if (without.length() > 0) without.append(':');
                    without.append(s);
                }
            }
            String with = without.length() > 0 ? without + ":" + self : self;
            boolean off = Settings.Secure.putString(c.getContentResolver(), ENABLED, without.toString());
            Thread.sleep(700);
            boolean on = Settings.Secure.putString(c.getContentResolver(), ENABLED, with);
            Settings.Secure.putString(c.getContentResolver(), "accessibility_enabled", "1");
            return off && on;
        } catch (Throwable t) {
            log(c, "In-process toggle failed: " + t.getClass().getSimpleName());
            return false;
        }
    }
}
