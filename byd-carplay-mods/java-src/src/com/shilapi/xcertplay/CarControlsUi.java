package com.shilapi.xcertplay;

import android.content.Context;
import android.os.Handler;
import android.os.Looper;
import android.view.View;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.TextView;

import java.util.ArrayList;
import java.util.Arrays;

import kotlin.jvm.functions.Function0;
import kotlin.jvm.functions.Function1;

/** "Car controls" rows inside Settings → Vehicle → Wheel keys, built with DiPlay's own widgets. */
public final class CarControlsUi {
    private static final Handler MAIN = new Handler(Looper.getMainLooper());

    private CarControlsUi() {}

    public static void build(DiPlayActivity a, LinearLayout card) {
        try {
            buildNow(a, card);
        } catch (Throwable ignored) {
        }
    }

    private static void buildNow(final DiPlayActivity a, LinearLayout card) {
        CarKeys.migrate(a);
        DiPlayActivity.diplayTitle(a, card, "Car controls");
        DiPlayActivity.diplayNote(a, card,
                "Choose what each car key does. A single press replaces the key's normal job; with only a double press set, a single press keeps working.");

        String wake = CarWake.lastNote(a);
        if (wake != null) DiPlayActivity.diplayNote(a, card, "Last car start: " + wake);

        serviceRows(a, card);
        wakeRows(a, card);

        for (int b = 0; b < CarKeys.BTN_CODE.length; b++) buttonRows(a, card, b);

        DiPlayActivity.diplayTitle(a, card, "Other keys");
        DiPlayActivity.diplayNote(a, card,
                "For a key that isn't in the list above: assign it by pressing it on the car.");
        for (int s = 0; s < CarKeys.SLOTS; s++) slotRows(a, card, s);

        screenRows(a, card);
        DiplayUi.climateChoice(a, card);
        permissionRows(a, card);
    }

    // ---- wheel-key service ----

    private static void serviceRows(final DiPlayActivity a, LinearLayout card) {
        boolean running = false;
        try {
            running = WheelKeyService.Companion.connected();
        } catch (Throwable ignored) {
        }
        if (running) return;
        final TextView status = DiPlayActivity.diplayNote(a, card,
                "Wheel key service: off. Turn it on so DiPlay can see the wheel keys.");
        DiPlayActivity.diplayButton(a, card, "Turn on wheel key service", new Function0() {
            public Object invoke() {
                status.setText("Wheel key service: turning on…");
                final Context app = a.getApplicationContext();
                new Thread(new Runnable() {
                    public void run() {
                        Object r = null;
                        try {
                            r = WheelKeyService.Companion.enableOverAdb(app, true);
                        } catch (Throwable ignored) {
                        }
                        final String access = String.valueOf(r);
                        MAIN.postDelayed(new Runnable() {
                            public void run() {
                                boolean on = false;
                                try {
                                    on = WheelKeyService.Companion.connected();
                                } catch (Throwable ignored) {
                                }
                                status.setText(on ? "Wheel key service: on ✓"
                                        : "Wheel key service: not on yet (ADB: " + access + "). Allow the ADB prompt, then try again.");
                            }
                        }, 1500);
                    }
                }, "DiPlay-WheelEnable").start();
                return kotlin.Unit.INSTANCE;
            }
        });
    }

    // ---- named keys ----

    private static final String[] PRESS_TITLES = {"Double press", "Long press", "Single press"};

    private static void buttonRows(final DiPlayActivity a, LinearLayout card, final int b) {
        DiPlayActivity.diplayTitle(a, card, CarKeys.BTN_NAMES[b]);
        int[] order = {CarKeys.PRESS_SINGLE, CarKeys.PRESS_DOUBLE, CarKeys.PRESS_LONG};
        for (final int press : order) {
            if (press == CarKeys.PRESS_DOUBLE && !CarKeys.BTN_DOUBLE[b]) continue;
            if (press == CarKeys.PRESS_LONG && CarKeys.BTN_LONG[b] <= 0) continue;
            DiPlayActivity.choice$default(a, card, PRESS_TITLES[press],
                    new ArrayList<String>(Arrays.asList(CarActions.NAMES)),
                    CarKeys.btnAction(a, b, press), false, false, false,
                    new Function1() {
                        public Object invoke(Object p) {
                            CarKeys.setBtnAction(a, b, press, ((Number) p).intValue());
                            return kotlin.Unit.INSTANCE;
                        }
                    }, 0x60, null);
        }
    }

    // ---- after the car wakes ----

    private static void wakeRows(final DiPlayActivity a, LinearLayout card) {
        DiPlayActivity.toggle$default(a, card, "Restart DiPlay after the car wakes",
                "After switching the car off and on, the wheel keys can stop working until DiPlay is force-stopped. "
                        + "With this on, DiPlay does that once by itself when the car wakes (a few seconds; CarPlay "
                        + "connects right after).",
                CarWake.wakeRestartEnabled(a), false,
                new Function1() {
                    public Object invoke(Object p) {
                        CarActions.prefs(a).edit().putBoolean(CarWake.KEY_WAKE_RESTART, Boolean.TRUE.equals(p)).apply();
                        return kotlin.Unit.INSTANCE;
                    }
                }, 0x10, null);
        DiPlayActivity.diplayButton(a, card, "Refresh wheel keys", new Function0() {
            public Object invoke() {
                CarWake.refreshNow(a);
                return kotlin.Unit.INSTANCE;
            }
        });
        DiPlayActivity.diplayNote(a, card, "If the keys stop working: DiPlay closes and opens again by itself.");
    }

    // ---- slots ----

    private static String keyLabel(Context c, int slot) {
        int code = CarKeys.code(c, slot);
        return code > 0 ? "Key: " + CarKeys.keyName(code) + " · tap to change" : "Key: none · tap to assign";
    }

    private static void slotRows(final DiPlayActivity a, LinearLayout card, final int slot) {
        DiPlayActivity.diplayTitle(a, card, "Other key " + (slot + 1));

        final Button[] keyButton = new Button[1];
        keyButton[0] = DiPlayActivity.diplayButton(a, card, keyLabel(a, slot), new Function0() {
            public Object invoke() {
                boolean running = false;
                try {
                    running = WheelKeyService.Companion.connected();
                } catch (Throwable ignored) {
                }
                if (!running) {
                    CarActions.toast(a, "Turn on the wheel key service first");
                    return kotlin.Unit.INSTANCE;
                }
                final Button b = keyButton[0];
                if (b != null) b.setText("Press the wheel key now…");
                CarKeys.startLearning(slot, new CarKeys.LearnListener() {
                    public void learnt(int s, int code) {
                        if (b != null) b.setText(keyLabel(a, s));
                    }

                    public void timedOut(int s) {
                        if (b != null) b.setText(keyLabel(a, s));
                        CarActions.toast(a, "No key pressed. If the key shows nothing, DiPlay can't use it.");
                    }
                });
                return kotlin.Unit.INSTANCE;
            }
        });

        final TextView warning = DiPlayActivity.diplayNote(a, card,
                "Single press replaces this key's normal job.");
        if (warning != null) {
            warning.setVisibility(CarKeys.press(a, slot) == CarKeys.PRESS_SINGLE ? View.VISIBLE : View.GONE);
        }

        DiPlayActivity.choice$default(a, card, "Press",
                new ArrayList<String>(Arrays.asList(CarKeys.PRESS_NAMES)),
                CarKeys.press(a, slot), false, false, false,
                new Function1() {
                    public Object invoke(Object p) {
                        int v = ((Number) p).intValue();
                        CarKeys.setPress(a, slot, v);
                        if (warning != null) {
                            warning.setVisibility(v == CarKeys.PRESS_SINGLE ? View.VISIBLE : View.GONE);
                        }
                        return kotlin.Unit.INSTANCE;
                    }
                }, 0x60, null);

        DiPlayActivity.choice$default(a, card, "Action",
                new ArrayList<String>(Arrays.asList(CarActions.NAMES)),
                CarKeys.action(a, slot), false, false, false,
                new Function1() {
                    public Object invoke(Object p) {
                        CarKeys.setAction(a, slot, ((Number) p).intValue());
                        return kotlin.Unit.INSTANCE;
                    }
                }, 0x60, null);
    }

    // ---- climate screen capture ----

    private static String screenLabel(Context c) {
        String comp = CarActions.prefs(c).getString(CarActions.KEY_SCREEN, "");
        if (comp != null && comp.length() > 0) return "Climate screen: " + comp;
        String auto = CarActions.defaultScreen(c);
        return auto != null ? "Climate screen: automatic (BYD climate)" : "Climate screen: not found, use Capture";
    }

    private static void screenRows(final DiPlayActivity a, LinearLayout card) {
        DiPlayActivity.diplayTitle(a, card, "Climate screen");
        final TextView status = DiPlayActivity.diplayNote(a, card, screenLabel(a));
        DiPlayActivity.diplayButton(a, card, "Capture current screen", new Function0() {
            public Object invoke() {
                if (status != null) status.setText("Reading the last screen…");
                final Context app = a.getApplicationContext();
                new Thread(new Runnable() {
                    public void run() {
                        final String comp = CarActions.captureScreen(app);
                        if (comp != null) {
                            CarActions.prefs(app).edit().putString(CarActions.KEY_SCREEN, comp).apply();
                        }
                        MAIN.post(new Runnable() {
                            public void run() {
                                if (status == null) return;
                                if (comp != null) {
                                    status.setText("Saved: " + comp);
                                } else {
                                    status.setText(screenLabel(app) + " · couldn't read it (is ADB allowed?)");
                                }
                            }
                        });
                    }
                }, "DiPlay-Capture").start();
                return kotlin.Unit.INSTANCE;
            }
        });
        DiPlayActivity.diplayNote(a, card,
                "Only needed if the automatic screen doesn't open: open the car's climate screen, come straight back here and press Capture.");
    }

    // ---- permission ----

    private static String permissionLabel(Context c) {
        return (CarActions.acAllowed(c) ? "Car control: allowed ✓" : "Car control: not allowed yet")
                + "\n" + CarActions.acStatus(c);
    }

    private static void permissionRows(final DiPlayActivity a, LinearLayout card) {
        DiPlayActivity.diplayTitle(a, card, "Permission");
        final TextView status = DiPlayActivity.diplayNote(a, card, permissionLabel(a));
        DiPlayActivity.diplayButton(a, card, "Allow car control", new Function0() {
            public Object invoke() {
                if (status != null) status.setText("Allowing car control over ADB…");
                final Context app = a.getApplicationContext();
                new Thread(new Runnable() {
                    public void run() {
                        final String problems = CarActions.grantAc(app);
                        MAIN.post(new Runnable() {
                            public void run() {
                                if (!CarActions.acAllowed(a)) CarActions.requestAc(a);
                                String text = permissionLabel(a);
                                if (problems.length() > 0) text = text + "\n" + problems;
                                if (status != null) status.setText(text);
                            }
                        });
                    }
                }, "DiPlay-GrantAc").start();
                for (int i = 3; i <= 20; i += 2) {
                    MAIN.postDelayed(new Runnable() {
                        public void run() {
                            if (status != null && CarActions.acAllowed(a)) status.setText(permissionLabel(a));
                        }
                    }, i * 1000L);
                }
                return kotlin.Unit.INSTANCE;
            }
        });
        DiPlayActivity.diplayNote(a, card,
                "AC buttons run through ADB, like DiPlay's other car features, so AC_GET / AC_SET can stay ✗. This permission is only a backup.");
    }
}
