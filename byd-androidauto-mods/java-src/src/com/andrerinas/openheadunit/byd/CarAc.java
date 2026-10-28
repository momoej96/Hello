package com.andrerinas.openheadunit.byd;

import android.content.Context;

import java.lang.reflect.InvocationTargetException;

/**
 * BYD AC commands through BYDAutoAcDevice (reflection; the class exists only on BYD head units).
 * Runs inside the app or inside CarAcShell under the shell user; keeps no state of its own.
 */
final class CarAc {
    static final int WIND_DEFROST = 5;

    private CarAc() {}

    /** Result: [0] message, [1] wind mode to restore after defrost, [2] last Auto/Manual mode. */
    static String[] run(Context c, String cmd, int prevWind, int lastAuto) throws Exception {
        Context ctx = c instanceof PermissiveContext ? c : new PermissiveContext(c);
        Object dev = Class.forName("android.hardware.bydauto.ac.BYDAutoAcDevice")
                .getMethod("getInstance", Context.class).invoke(null, ctx);
        if (dev == null) throw new ClassNotFoundException("no AC device");
        String msg;
        if ("power".equals(cmd)) {
            if (getInt(dev, "getAcStartState") == 1) {
                call(dev, "stop", stopSource());
                msg = "AC off";
            } else {
                call(dev, "setAcControlMode", 0, 0);
                lastAuto = 0;
                msg = "AC on (Auto)";
            }
        } else if ("auto".equals(cmd)) {
            int mode;
            try {
                mode = getInt(dev, "getAcControlMode");
            } catch (NoSuchMethodException e) {
                mode = lastAuto;
            }
            boolean on = getInt(dev, "getAcStartState") == 1;
            int next = (on && mode == 0) ? 1 : 0;
            call(dev, "setAcControlMode", 0, next);
            lastAuto = next;
            msg = next == 0 ? "AC Auto" : "AC Manual";
        } else if ("recirc".equals(cmd)) {
            int next = getInt(dev, "getAcCycleMode") == 1 ? 0 : 1;
            call(dev, "setAcCycleMode", 0, next);
            msg = next == 1 ? "Recirculation: inside" : "Recirculation: outside air";
        } else if ("defrost".equals(cmd)) {
            int current = getInt(dev, "getAcWindMode");
            if (current == WIND_DEFROST) {
                int prev = (prevWind == WIND_DEFROST || prevWind < 0) ? 1 : prevWind;
                call(dev, "setAcWindMode", 0, prev);
                msg = "Defrost off";
            } else {
                prevWind = current;
                call(dev, "setAcWindMode", 0, WIND_DEFROST);
                msg = "Defrost on";
            }
        } else if ("on".equals(cmd)) {
            call(dev, "setAcControlMode", 0, 0);
            lastAuto = 0;
            msg = "AC on (Auto)";
        } else if ("off".equals(cmd)) {
            call(dev, "stop", stopSource());
            msg = "AC off";
        } else if ("tempup".equals(cmd) || "tempdown".equals(cmd)) {
            // Same as Diplus: driver temperature ±1, clamped to the unit's range.
            int unit = getInt(dev, "getTemperatureUnit");
            int temp = getInt(dev, "getTemprature", 1) + ("tempup".equals(cmd) ? 1 : -1);
            if (unit == 0) temp = Math.max(64, Math.min(91, temp));
            else temp = Math.max(17, Math.min(33, temp));
            call(dev, "setAcTemperature", 0, temp, 0, unit);
            msg = "Temperature " + temp + "°";
        } else if ("fanup".equals(cmd) || "fandown".equals(cmd)) {
            int level = getInt(dev, "getAcWindLevel") + ("fanup".equals(cmd) ? 1 : -1);
            level = Math.max(0, Math.min(7, level));
            call(dev, "setAcWindLevel", 0, level);
            msg = "Fan speed " + level;
        } else if ("in".equals(cmd) || "out".equals(cmd)) {
            int mode = "in".equals(cmd) ? 1 : 0;
            call(dev, "setAcCycleMode", 0, mode);
            msg = mode == 1 ? "Recirculation: inside" : "Recirculation: outside air";
        } else if ("vent".equals(cmd) || "venton".equals(cmd) || "ventoff".equals(cmd)) {
            int on;
            if ("venton".equals(cmd)) {
                on = 1;
            } else if ("ventoff".equals(cmd)) {
                on = 0;
            } else {
                int state;
                try {
                    state = getInt(dev, "getAcVentilationState");
                } catch (NoSuchMethodException e) {
                    state = 0;
                }
                on = state == 1 ? 0 : 1;
            }
            call(dev, "setAcVentilationState", 0, on);
            msg = on == 1 ? "Fan only: on" : "Fan only: off";
        } else if (cmd.startsWith("wind") && cmd.length() == 5) {
            int mode = cmd.charAt(4) - '0';
            if (mode < 1 || mode > 7) throw new IllegalArgumentException("unknown airflow " + cmd);
            call(dev, "setAcWindMode", 0, mode);
            msg = "Airflow: " + WIND_NAMES[mode];
        } else {
            throw new IllegalArgumentException("unknown AC command " + cmd);
        }
        return new String[] {msg, String.valueOf(prevWind), String.valueOf(lastAuto)};
    }

    static final String[] WIND_NAMES = {
        "", "face", "face + feet", "feet", "feet + defrost", "windscreen", "face + feet + defrost", "face + defrost",
    };

    private static int getInt(Object dev, String name) throws Exception {
        Object r = dev.getClass().getMethod(name).invoke(dev);
        return r instanceof Number ? ((Number) r).intValue() : -1;
    }

    private static int getInt(Object dev, String name, int arg) throws Exception {
        Object r = dev.getClass().getMethod(name, int.class).invoke(dev, Integer.valueOf(arg));
        return r instanceof Number ? ((Number) r).intValue() : -1;
    }

    private static void call(Object dev, String name, int... args) throws Exception {
        Class<?>[] types = new Class<?>[args.length];
        Object[] values = new Object[args.length];
        for (int i = 0; i < args.length; i++) {
            types[i] = int.class;
            values[i] = Integer.valueOf(args[i]);
        }
        dev.getClass().getMethod(name, types).invoke(dev, values);
    }

    /** Same source id Diplus passes to stop(); 0 when the field is missing. */
    private static int stopSource() {
        try {
            Class<?> cls = Class.forName("android.hardware.bydauto.BYDAutoFeatureIds$Setting");
            return cls.getField("SET_RIGHT_LANE_LINE_Y_DISTANCE").getInt(null);
        } catch (Throwable t) {
            return 0;
        }
    }

    static Throwable unwrap(Throwable t) {
        if (t instanceof InvocationTargetException && t.getCause() != null) return t.getCause();
        return t;
    }

    static String reason(Throwable t) {
        t = unwrap(t);
        String m = t.getMessage();
        if (m == null || m.length() == 0) m = t.getClass().getSimpleName();
        m = m.replace('\n', ' ').replace('|', '/');
        return m.length() > 80 ? m.substring(0, 80) : m;
    }
}
