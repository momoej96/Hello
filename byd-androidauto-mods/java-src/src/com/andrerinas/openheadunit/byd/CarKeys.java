package com.andrerinas.openheadunit.byd;

import android.content.Context;
import android.os.Handler;
import android.os.Looper;
import android.os.SystemClock;
import android.view.KeyEvent;

/**
 * Car keys: BYD's known wheel/console keys (codes as Diplus lists them, with BYD's separate
 * long-press codes) plus two learnt "other key" slots; each press type maps to a car action.
 * Called from WheelKeyService.onKeyEvent; returns true when the event is consumed.
 */
public final class CarKeys {
    public static final int SLOTS = 2;

    public static final String[] BTN_NAMES = {
        "Call", "Voice", "Mode", "Mute", "360 camera", "Rotate screen",
        "Next", "Previous", "Power", "Volume up", "Volume down",
    };
    public static final int[] BTN_CODE = {313, 304, 289, 293, 294, 305, 87, 88, 317, 291, 292};
    /** BYD sends its own code while a key is held; -1 when the key has none. */
    public static final int[] BTN_LONG = {-1, 312, -1, -1, -1, 306, 302, 303, -1, -1, -1};
    public static final boolean[] BTN_DOUBLE = {true, true, true, true, true, true, true, true, true, false, false};
    public static final int PRESS_DOUBLE = 0;
    public static final int PRESS_LONG = 1;
    public static final int PRESS_SINGLE = 2;
    public static final String[] PRESS_NAMES = {"Double press", "Long press", "Single press"};

    static final long DOUBLE_MS = 500;
    static final long LONG_MS = 800;
    static final long LEARN_MS = 10000;
    static final long REPLAY_PASS_MS = 3000;

    public interface LearnListener {
        void learnt(int slot, int code);
        void timedOut(int slot);
    }

    private static final Handler MAIN = new Handler(Looper.getMainLooper());

    private static volatile int learningSlot = -1;
    private static volatile LearnListener learnListener;
    private static Runnable learnTimeout;

    private static int swallowUpCode = -1;
    private static int replayCode = -1;
    private static long replayUntil;

    private static int curKey = -1;
    private static boolean longFired;
    private static boolean secondPress;
    private static Runnable longRunnable;

    private static int pendingKey = -1;
    private static Runnable pendingRunnable;

    private CarKeys() {}

    // ---- slot storage ----

    public static int code(Context c, int slot) {
        return CarActions.prefs(c).getInt("carkey_code_" + slot, -1);
    }

    public static int press(Context c, int slot) {
        int p = CarActions.prefs(c).getInt("carkey_press_" + slot, PRESS_DOUBLE);
        return (p < 0 || p > 2) ? PRESS_DOUBLE : p;
    }

    public static int action(Context c, int slot) {
        int a = CarActions.prefs(c).getInt("carkey_action_" + slot, CarActions.NONE);
        return (a < 0 || a >= CarActions.NAMES.length) ? CarActions.NONE : a;
    }

    public static void setCode(Context c, int slot, int code) {
        CarActions.prefs(c).edit().putInt("carkey_code_" + slot, code).apply();
    }

    public static void setPress(Context c, int slot, int press) {
        CarActions.prefs(c).edit().putInt("carkey_press_" + slot, press).apply();
    }

    public static void setAction(Context c, int slot, int action) {
        CarActions.prefs(c).edit().putInt("carkey_action_" + slot, action).apply();
    }

    // ---- named keys ----

    static int buttonIndex(int code) {
        for (int i = 0; i < BTN_CODE.length; i++) if (BTN_CODE[i] == code) return i;
        return -1;
    }

    static int longIndex(int code) {
        for (int i = 0; i < BTN_LONG.length; i++) if (BTN_LONG[i] == code) return i;
        return -1;
    }

    public static int btnAction(Context c, int button, int press) {
        int a = CarActions.prefs(c).getInt("carbtn_" + BTN_CODE[button] + "_" + press, CarActions.NONE);
        return (a < 0 || a >= CarActions.NAMES.length) ? CarActions.NONE : a;
    }

    public static void setBtnAction(Context c, int button, int press, int action) {
        CarActions.prefs(c).edit().putInt("carbtn_" + BTN_CODE[button] + "_" + press, action).apply();
    }

    /** True when any key has an action (keeps the wheel-key service wanted). */
    public static boolean anyConfigured(Context c) {
        try {
            for (int b = 0; b < BTN_CODE.length; b++) {
                for (int press = 0; press <= 2; press++) {
                    if (btnAction(c, b, press) != CarActions.NONE) return true;
                }
            }
            for (int s = 0; s < SLOTS; s++) {
                if (code(c, s) > 0 && action(c, s) != CarActions.NONE) return true;
            }
        } catch (Throwable ignored) {
        }
        return false;
    }

    public static String keyName(int code) {
        if (code <= 0) return "none";
        String n;
        try {
            n = KeyEvent.keyCodeToString(code);
        } catch (Throwable t) {
            n = null;
        }
        if (n == null || n.length() == 0 || n.equals(String.valueOf(code))) return "key " + code;
        if (n.startsWith("KEYCODE_")) n = n.substring(8);
        return n.replace('_', ' ') + " (" + code + ")";
    }

    // ---- learning ----

    public static void startLearning(final int slot, LearnListener listener) {
        learnListener = listener;
        learningSlot = slot;
        if (learnTimeout != null) MAIN.removeCallbacks(learnTimeout);
        learnTimeout = new Runnable() {
            public void run() {
                if (learningSlot == slot) {
                    learningSlot = -1;
                    LearnListener l = learnListener;
                    if (l != null) l.timedOut(slot);
                }
            }
        };
        MAIN.postDelayed(learnTimeout, LEARN_MS);
    }

    public static void cancelLearning() {
        learningSlot = -1;
        if (learnTimeout != null) MAIN.removeCallbacks(learnTimeout);
    }

    // ---- key handling ----

    public static boolean onKey(Context ctx, KeyEvent e) {
        try {
            return handle(ctx, e);
        } catch (Throwable t) {
            return false;
        }
    }

    private static boolean handle(final Context ctx, KeyEvent e) {
        final int code = e.getKeyCode();
        int act = e.getAction();
        if (code == KeyEvent.KEYCODE_UNKNOWN) return false;
        if (act != KeyEvent.ACTION_DOWN && act != KeyEvent.ACTION_UP) return false;
        long now = SystemClock.uptimeMillis();

        // Our own replayed press goes to the head unit untouched.
        if (code == replayCode && now < replayUntil) {
            if (act == KeyEvent.ACTION_UP) replayCode = -1;
            return false;
        }

        if (learningSlot >= 0) {
            if (act == KeyEvent.ACTION_DOWN && e.getRepeatCount() == 0) {
                final int slot = learningSlot;
                learningSlot = -1;
                if (learnTimeout != null) MAIN.removeCallbacks(learnTimeout);
                setCode(ctx, slot, code);
                swallowUpCode = code;
                CarActions.toast(ctx, "Key saved: " + keyName(code));
                final LearnListener l = learnListener;
                if (l != null) {
                    MAIN.post(new Runnable() {
                        public void run() {
                            l.learnt(slot, code);
                        }
                    });
                }
            }
            return true;
        }

        if (act == KeyEvent.ACTION_UP && code == swallowUpCode) {
            swallowUpCode = -1;
            return true;
        }

        // BYD's held-key codes (e.g. 302 for Next held) act at once.
        int li = longIndex(code);
        if (li >= 0) {
            int a = btnAction(ctx, li, PRESS_LONG);
            if (a == CarActions.NONE) return false;
            if (act == KeyEvent.ACTION_DOWN && e.getRepeatCount() == 0) CarActions.run(ctx, a);
            return true;
        }

        final int dbl = slotAction(ctx, code, PRESS_DOUBLE);
        final int lng = slotAction(ctx, code, PRESS_LONG);
        final int sgl = slotAction(ctx, code, PRESS_SINGLE);
        if (dbl == 0 && lng == 0 && sgl == 0) return false;

        if (act == KeyEvent.ACTION_DOWN) {
            if (e.getRepeatCount() > 0) return curKey == code;
            if (pendingKey == code && dbl != 0) {
                MAIN.removeCallbacks(pendingRunnable);
                pendingKey = -1;
                curKey = code;
                secondPress = true;
                longFired = false;
                CarActions.run(ctx, dbl);
                return true;
            }
            if (pendingKey != -1) flushPending();
            curKey = code;
            secondPress = false;
            longFired = false;
            if (lng != 0) {
                longRunnable = new Runnable() {
                    public void run() {
                        if (curKey == code) {
                            longFired = true;
                            CarActions.run(ctx, lng);
                        }
                    }
                };
                MAIN.postDelayed(longRunnable, LONG_MS);
            }
            return true;
        }

        // ACTION_UP
        if (curKey != code) return false;
        curKey = -1;
        if (longRunnable != null) {
            MAIN.removeCallbacks(longRunnable);
            longRunnable = null;
        }
        if (longFired || secondPress) return true;
        if (dbl != 0) {
            pendingKey = code;
            pendingRunnable = new Runnable() {
                public void run() {
                    if (pendingKey == code) {
                        pendingKey = -1;
                        shortPress(ctx, code, sgl);
                    }
                }
            };
            MAIN.postDelayed(pendingRunnable, DOUBLE_MS);
        } else {
            shortPress(ctx, code, sgl);
        }
        return true;
    }

    private static void flushPending() {
        Runnable r = pendingRunnable;
        MAIN.removeCallbacks(r);
        if (r != null) r.run();
    }

    private static int slotAction(Context c, int code, int pressType) {
        int b = buttonIndex(code);
        if (b >= 0 && pressType != PRESS_LONG) {
            int a = btnAction(c, b, pressType);
            if (a != CarActions.NONE) return a;
        }
        for (int s = 0; s < SLOTS; s++) {
            if (code(c, s) == code && press(c, s) == pressType) {
                int a = action(c, s);
                if (a != CarActions.NONE) return a;
            }
        }
        return 0;
    }

    /** A short press with no single-press slot keeps the key's normal job by replaying it. */
    private static void shortPress(final Context ctx, final int code, int single) {
        if (single != 0) {
            CarActions.run(ctx, single);
            return;
        }
        replayCode = code;
        replayUntil = SystemClock.uptimeMillis() + REPLAY_PASS_MS;
        final Context app = ctx.getApplicationContext();
        new Thread(new Runnable() {
            public void run() {
                CarActions.adb(app, "input keyevent " + code);
            }
        }, "DiAuto-KeyReplay").start();
    }
}
