package com.andrerinas.openheadunit.byd;

import android.content.Context;
import android.os.Looper;

/**
 * Entry point run over ADB with app_process, so the AC call comes from the shell user,
 * which BYD's service accepts (an app needs AC_GET/AC_SET, which can't be granted).
 * Usage: CarAcShell <command> <prevWind> <lastAuto>
 * Prints one line: "CARAC|OK|message|prevWind|lastAuto" or "CARAC|ERR|reason".
 */
public final class CarAcShell {
    private CarAcShell() {}

    public static void main(String[] args) {
        String line;
        try {
            try {
                Looper.prepareMainLooper();
            } catch (Throwable ignored) {
            }
            String cmd = args.length > 0 ? args[0] : "";
            int prev = args.length > 1 ? parse(args[1], -1) : -1;
            int last = args.length > 2 ? parse(args[2], 1) : 1;
            String[] r = CarAc.run(shellContext(), cmd, prev, last);
            line = "CARAC|OK|" + r[0] + "|" + r[1] + "|" + r[2];
        } catch (Throwable t) {
            line = "CARAC|ERR|" + CarAc.reason(t);
        }
        System.out.println(line);
        System.out.flush();
        System.exit(0);
    }

    private static int parse(String s, int fallback) {
        try {
            return Integer.parseInt(s.trim());
        } catch (Throwable t) {
            return fallback;
        }
    }

    /** The system context re-targeted to com.android.shell. */
    private static Context shellContext() throws Exception {
        Class<?> at = Class.forName("android.app.ActivityThread");
        Object thread = at.getMethod("systemMain").invoke(null);
        Context sys = (Context) at.getMethod("getSystemContext").invoke(thread);
        try {
            return sys.createPackageContext("com.android.shell", 0);
        } catch (Throwable t) {
            return sys;
        }
    }
}
