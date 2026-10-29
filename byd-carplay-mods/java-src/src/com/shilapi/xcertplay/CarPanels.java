package com.shilapi.xcertplay;

import android.app.AlertDialog;
import android.app.Dialog;
import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.content.pm.ResolveInfo;
import android.graphics.Color;
import android.graphics.drawable.GradientDrawable;
import android.os.Handler;
import android.os.Looper;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

import java.util.ArrayList;
import java.util.List;

import kotlin.jvm.functions.Function0;

/**
 * The two panels behind the Audio page: "Equalizer" (the sound adjustments) and "Car wheel keys"
 * (key actions, service, climate screen, permission). Plain Android views in a full-screen dialog,
 * so the same code works from DiPlay's settings and from the CarPlay side window.
 */
public final class CarPanels {
    private static final Handler MAIN = new Handler(Looper.getMainLooper());
    private static final int BG = 0xFF12161C;
    private static final int CARD = 0xFF1F2630;
    private static final int TEXT = 0xFFFFFFFF;
    private static final int SUB = 0xFFA8B3C2;

    private CarPanels() {}

    // ---- entry points ----

    /** Settings → Audio → Sound adjustments: two buttons in DiPlay's own style. */
    public static void settingsButtons(final DiPlayActivity a, LinearLayout card) {
        try {
            DiPlayActivity.diplayButton(a, card, "Equalizer", new Function0() {
                public Object invoke() {
                    openEqualizer(a);
                    return kotlin.Unit.INSTANCE;
                }
            });
            DiPlayActivity.diplayButton(a, card, "Car wheel keys", new Function0() {
                public Object invoke() {
                    openWheelKeys(a);
                    return kotlin.Unit.INSTANCE;
                }
            });
        } catch (Throwable ignored) {
        }
    }

    /** CarPlay side window, Audio tab. */
    public static void popupAudio(String key, LinearLayout page, final Context c) {
        try {
            if (!"audio".equals(key)) return;
            page.addView(bigButton(c, "Equalizer", new Runnable() {
                public void run() {
                    openEqualizer(c);
                }
            }), rowParams(c));
            page.addView(bigButton(c, "Car wheel keys", new Runnable() {
                public void run() {
                    openWheelKeys(c);
                }
            }), rowParams(c));
        } catch (Throwable ignored) {
        }
    }

    public static void openEqualizer(Context c) {
        try {
            Dialog d = new Dialog(c, android.R.style.Theme_Black_NoTitleBar);
            LinearLayout content = frame(c, d, "Equalizer");
            content.addView(new View(c), new LinearLayout.LayoutParams(1, 1));   // "header" that Reset keeps
            DiplayPopup.audioSliders("audio", content, c);
            d.show();
        } catch (Throwable t) {
            CarActions.toast(c, "Couldn't open the equalizer");
        }
    }

    public static void openWheelKeys(Context c) {
        try {
            Dialog d = new Dialog(c, android.R.style.Theme_Black_NoTitleBar);
            LinearLayout content = frame(c, d, "Car wheel keys");
            buildWheelKeys(c, content);
            d.show();
        } catch (Throwable t) {
            CarActions.toast(c, "Couldn't open car wheel keys");
        }
    }

    // ---- wheel keys panel ----

    private static void buildWheelKeys(final Context c, LinearLayout l) {
        CarKeys.migrate(c);

        title(c, l, "Service");
        l.addView(bigButton(c, "Open accessibility settings", new Runnable() {
            public void run() {
                try {
                    Intent i = new Intent("android.settings.ACCESSIBILITY_SETTINGS");
                    i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
                    c.startActivity(i);
                } catch (Throwable t) {
                    CarActions.toast(c, "Couldn't open accessibility settings");
                }
            }
        }), rowParams(c));
        l.addView(bigButton(c, "Turn on car wheel keys (ADB)", new Runnable() {
            public void run() {
                CarActions.prefs(c).edit().putBoolean(CarGuard.KEY_SERVICE_ON, true).apply();
                CarActions.toast(c, "Turning on…");
                final Context app = c.getApplicationContext();
                new Thread(new Runnable() {
                    public void run() {
                        boolean ok = CarGuard.setServiceEnabled(app, true);
                        try {
                            Thread.sleep(1500);
                        } catch (InterruptedException ignored) {
                        }
                        CarActions.toast(app, CarKeysService.connected() ? "Car wheel keys: on ✓"
                                : ok ? "Allowed. Starting…" : "Couldn't turn on. Allow the ADB prompt, then try again.");
                    }
                }, "DiPlay-CarKeysEnable").start();
            }
        }), rowParams(c));

        for (int b = 0; b < CarKeys.BTN_CODE.length; b++) buttonRows(c, l, b);

        title(c, l, "Other keys");
        for (int s = 0; s < CarKeys.SLOTS; s++) slotRows(c, l, s);

        title(c, l, "Climate");
        climateRows(c, l);

        title(c, l, "Permission");
        final TextView perm = label(c, permissionLabel(c));
        l.addView(perm, rowParams(c));
        l.addView(bigButton(c, "Allow car control", new Runnable() {
            public void run() {
                perm.setText("Allowing car control over ADB…");
                final Context app = c.getApplicationContext();
                new Thread(new Runnable() {
                    public void run() {
                        final String problems = CarActions.grantAc(app);
                        MAIN.post(new Runnable() {
                            public void run() {
                                String text = permissionLabel(c);
                                if (problems.length() > 0) text = text + "\n" + problems;
                                perm.setText(text);
                            }
                        });
                    }
                }, "DiPlay-GrantAc").start();
            }
        }), rowParams(c));
    }

    private static String permissionLabel(Context c) {
        return (CarActions.acAllowed(c) ? "Car control: allowed ✓" : "Car control: not allowed yet")
                + "\n" + CarActions.acStatus(c);
    }

    private static final String[] PRESS_TITLES = {"Double press", "Long press", "Single press"};

    private static void buttonRows(final Context c, LinearLayout l, final int b) {
        title(c, l, CarKeys.BTN_NAMES[b]);
        int[] order = {CarKeys.PRESS_SINGLE, CarKeys.PRESS_DOUBLE, CarKeys.PRESS_LONG};
        for (final int press : order) {
            if (press == CarKeys.PRESS_DOUBLE && !CarKeys.BTN_DOUBLE[b]) continue;
            if (press == CarKeys.PRESS_LONG && CarKeys.BTN_LONG[b] <= 0) continue;
            final Button row = row(c, "");
            row.setText(PRESS_TITLES[press] + " · " + CarActions.NAMES[CarKeys.btnAction(c, b, press)]);
            row.setOnClickListener(new View.OnClickListener() {
                public void onClick(View v) {
                    chooseAction(c, PRESS_TITLES[press], CarKeys.btnAction(c, b, press), new Picked() {
                        public void picked(int i) {
                            CarKeys.setBtnAction(c, b, press, i);
                            row.setText(PRESS_TITLES[press] + " · " + CarActions.NAMES[i]);
                        }
                    });
                }
            });
            l.addView(row, rowParams(c));
        }
    }

    private static String keyLabel(Context c, int slot) {
        int code = CarKeys.code(c, slot);
        return code > 0 ? "Key: " + CarKeys.keyName(code) + " · tap to change" : "Key: none · tap to assign";
    }

    private static void slotRows(final Context c, LinearLayout l, final int slot) {
        title(c, l, "Other key " + (slot + 1));
        final Button key = row(c, keyLabel(c, slot));
        key.setOnClickListener(new View.OnClickListener() {
            public void onClick(View v) {
                if (!CarKeysService.connected()) {
                    CarActions.toast(c, "Turn on car wheel keys first");
                    return;
                }
                key.setText("Press the wheel key now…");
                CarKeys.startLearning(slot, new CarKeys.LearnListener() {
                    public void learnt(int s, int code) {
                        key.setText(keyLabel(c, s));
                    }

                    public void timedOut(int s) {
                        key.setText(keyLabel(c, s));
                        CarActions.toast(c, "No key pressed. If the key shows nothing, DiPlay can't use it.");
                    }
                });
            }
        });
        l.addView(key, rowParams(c));

        final Button press = row(c, "Press · " + CarKeys.PRESS_NAMES[CarKeys.press(c, slot)]);
        press.setOnClickListener(new View.OnClickListener() {
            public void onClick(View v) {
                chooseFrom(c, "Press", CarKeys.PRESS_NAMES, CarKeys.press(c, slot), new Picked() {
                    public void picked(int i) {
                        CarKeys.setPress(c, slot, i);
                        press.setText("Press · " + CarKeys.PRESS_NAMES[i]);
                    }
                });
            }
        });
        l.addView(press, rowParams(c));

        final Button act = row(c, "Action · " + CarActions.NAMES[CarKeys.action(c, slot)]);
        act.setOnClickListener(new View.OnClickListener() {
            public void onClick(View v) {
                chooseAction(c, "Action", CarKeys.action(c, slot), new Picked() {
                    public void picked(int i) {
                        CarKeys.setAction(c, slot, i);
                        act.setText("Action · " + CarActions.NAMES[i]);
                    }
                });
            }
        });
        l.addView(act, rowParams(c));
    }

    // ---- climate ----

    private static String screenLabel(Context c) {
        String comp = CarActions.prefs(c).getString(CarActions.KEY_SCREEN, "");
        if (comp != null && comp.length() > 0) return "Climate screen: " + comp;
        return CarActions.defaultScreen(c) != null ? "Climate screen: automatic (BYD climate)"
                : "Climate screen: not found, use Capture";
    }

    private static void climateRows(final Context c, LinearLayout l) {
        final TextView status = label(c, screenLabel(c));
        l.addView(status, rowParams(c));
        l.addView(bigButton(c, "Capture climate screen", new Runnable() {
            public void run() {
                status.setText("Reading the last screen…");
                final Context app = c.getApplicationContext();
                new Thread(new Runnable() {
                    public void run() {
                        final String comp = CarActions.captureScreen(app);
                        if (comp != null) CarActions.prefs(app).edit().putString(CarActions.KEY_SCREEN, comp).apply();
                        MAIN.post(new Runnable() {
                            public void run() {
                                status.setText(comp != null ? "Saved: " + comp
                                        : screenLabel(app) + " · couldn't read it (is ADB allowed?)");
                            }
                        });
                    }
                }, "DiPlay-Capture").start();
            }
        }), rowParams(c));

        final List<String> names = new ArrayList<String>();
        final List<String> comps = new ArrayList<String>();
        names.add("Not set");
        comps.add("");
        try {
            PackageManager pm = c.getPackageManager();
            Intent q = new Intent("android.intent.action.MAIN");
            q.addCategory("android.intent.category.LAUNCHER");
            for (ResolveInfo ri : pm.queryIntentActivities(q, 0)) {
                names.add(ri.loadLabel(pm).toString());
                comps.add(ri.activityInfo.packageName + "/" + ri.activityInfo.name);
            }
        } catch (Throwable ignored) {
        }
        String cur = CarActions.prefs(c).getString("climate_component", "");
        int at = comps.indexOf(cur);
        final Button app = row(c, "Climate app · " + names.get(at < 0 ? 0 : at));
        app.setOnClickListener(new View.OnClickListener() {
            public void onClick(View v) {
                String now = CarActions.prefs(c).getString("climate_component", "");
                int sel = comps.indexOf(now);
                chooseFrom(c, "Climate app", names.toArray(new String[0]), sel < 0 ? 0 : sel, new Picked() {
                    public void picked(int i) {
                        CarActions.prefs(c).edit().putString("climate_component", comps.get(i)).apply();
                        app.setText("Climate app · " + names.get(i));
                    }
                });
            }
        });
        l.addView(app, rowParams(c));
    }

    // ---- choosers ----

    private interface Picked {
        void picked(int index);
    }

    private static void chooseAction(Context c, String title, int selected, Picked p) {
        chooseFrom(c, title, CarActions.NAMES, selected, p);
    }

    private static void chooseFrom(Context c, String title, final String[] items, int selected, final Picked p) {
        try {
            AlertDialog.Builder b = new AlertDialog.Builder(c, android.R.style.Theme_DeviceDefault_Dialog);
            b.setTitle(title);
            b.setSingleChoiceItems(items, selected, null);
            final AlertDialog[] holder = new AlertDialog[1];
            b.setSingleChoiceItems(items, selected, new android.content.DialogInterface.OnClickListener() {
                public void onClick(android.content.DialogInterface d, int which) {
                    p.picked(which);
                    d.dismiss();
                }
            });
            holder[0] = b.create();
            holder[0].show();
        } catch (Throwable t) {
            CarActions.toast(c, "Couldn't open the list");
        }
    }

    // ---- views ----

    private static LinearLayout frame(Context c, final Dialog d, String titleText) {
        LinearLayout root = new LinearLayout(c);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setBackgroundColor(BG);

        LinearLayout header = new LinearLayout(c);
        header.setOrientation(LinearLayout.HORIZONTAL);
        header.setGravity(Gravity.CENTER_VERTICAL);
        header.setPadding(dp(c, 16), dp(c, 12), dp(c, 16), dp(c, 12));
        Button back = pill(c, "← Back");
        back.setOnClickListener(new View.OnClickListener() {
            public void onClick(View v) {
                d.dismiss();
            }
        });
        header.addView(back, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.WRAP_CONTENT, dp(c, 48)));
        TextView t = new TextView(c);
        t.setText(titleText);
        t.setTextColor(TEXT);
        t.setTextSize(22);
        t.setPadding(dp(c, 16), 0, 0, 0);
        header.addView(t, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT));
        root.addView(header, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));

        ScrollView sv = new ScrollView(c);
        LinearLayout content = new LinearLayout(c);
        content.setOrientation(LinearLayout.VERTICAL);
        content.setPadding(dp(c, 24), dp(c, 8), dp(c, 24), dp(c, 32));
        sv.addView(content, new ViewGroup.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));
        root.addView(sv, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 0, 1f));
        d.setContentView(root);
        return content;
    }

    private static int dp(Context c, int v) {
        return (int) (v * c.getResources().getDisplayMetrics().density + 0.5f);
    }

    private static LinearLayout.LayoutParams rowParams(Context c) {
        LinearLayout.LayoutParams p = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        p.topMargin = dp(c, 8);
        return p;
    }

    private static void title(Context c, LinearLayout l, String text) {
        TextView t = new TextView(c);
        t.setText(text);
        t.setTextColor(TEXT);
        t.setTextSize(18);
        t.setPadding(dp(c, 4), dp(c, 24), 0, dp(c, 2));
        l.addView(t, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));
    }

    private static TextView label(Context c, String text) {
        TextView t = new TextView(c);
        t.setText(text);
        t.setTextColor(SUB);
        t.setTextSize(14);
        t.setPadding(dp(c, 4), dp(c, 4), 0, dp(c, 4));
        return t;
    }

    private static GradientDrawable fill(Context c, int color) {
        GradientDrawable g = new GradientDrawable();
        g.setColor(color);
        g.setCornerRadius(dp(c, 14));
        return g;
    }

    private static Button pill(Context c, String text) {
        Button b = new Button(c);
        b.setText(text);
        b.setAllCaps(false);
        b.setTextColor(TEXT);
        b.setTextSize(16);
        b.setBackground(fill(c, CARD));
        return b;
    }

    private static Button row(Context c, String text) {
        Button b = pill(c, text);
        b.setGravity(Gravity.CENTER_VERTICAL | Gravity.START);
        b.setMinHeight(dp(c, 56));
        b.setPadding(dp(c, 18), 0, dp(c, 18), 0);
        return b;
    }

    private static Button bigButton(Context c, String text, final Runnable action) {
        Button b = row(c, text);
        b.setGravity(Gravity.CENTER);
        b.setOnClickListener(new View.OnClickListener() {
            public void onClick(View v) {
                action.run();
            }
        });
        return b;
    }
}
