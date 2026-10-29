package com.andrerinas.openheadunit.byd;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.ComponentName;
import android.content.DialogInterface;
import android.content.Intent;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.util.TypedValue;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

/** Settings → BYD car controls: wheel keys, AC, climate screen, and the setup they need. */
public final class CarControlsActivity extends Activity {
    private static final int BG = 0xFF0C111B;
    private static final int CARD = 0xFF151E2C;
    private static final int TEXT = 0xFFF1F5FC;
    private static final int MUTED = 0xFFA8B6CA;
    private static final int ACCENT = 0xFF009688;
    private static final int LINE = 0xFF243041;

    private static final String[] PRESS_TITLES = {"Double press", "Long press", "Single press"};

    private final Handler main = new Handler(Looper.getMainLooper());
    private float dp;
    private int accent = ACCENT;
    private LinearLayout content;
    private TextView adbStatus;
    private TextView serviceStatus;
    private TextView permissionStatus;

    @Override
    protected void onCreate(Bundle saved) {
        super.onCreate(saved);
        dp = getResources().getDisplayMetrics().density;
        accent = color("brand_teal", ACCENT);

        ScrollView scroll = new ScrollView(this);
        scroll.setBackgroundColor(BG);
        scroll.setFillViewport(true);
        FrameLayout frame = new FrameLayout(this);
        scroll.addView(frame, new ViewGroup.LayoutParams(-1, -2));
        content = new LinearLayout(this);
        content.setOrientation(LinearLayout.VERTICAL);
        int pad = px(24);
        content.setPadding(pad, pad, pad, pad);
        int width = Math.min(getResources().getDisplayMetrics().widthPixels, px(960));
        frame.addView(content, new FrameLayout.LayoutParams(width, -2, Gravity.CENTER_HORIZONTAL));
        setContentView(scroll);

        build();
    }

    @Override
    protected void onResume() {
        super.onResume();
        refreshStatus();
    }

    @Override
    protected void onPause() {
        CarKeys.cancelLearning();
        super.onPause();
    }

    private void build() {
        header();

        LinearLayout setup = card("Setup");
        note(setup, "Car keys and the AC run through the head unit's own ADB, like DiPlay. "
                + "The first time, the car asks \"Allow USB debugging?\": tick \"Always allow\" and press Allow.");
        adbStatus = status(setup);
        button(setup, "Test ADB", new View.OnClickListener() {
            public void onClick(View v) {
                testAdb();
            }
        });
        divider(setup);
        serviceStatus = status(setup);
        button(setup, "Turn on wheel key service", new View.OnClickListener() {
            public void onClick(View v) {
                enableService();
            }
        });
        button(setup, "Open accessibility settings", new View.OnClickListener() {
            public void onClick(View v) {
                openAccessibility();
            }
        });
        divider(setup);
        permissionStatus = status(setup);
        button(setup, "Allow car control", new View.OnClickListener() {
            public void onClick(View v) {
                allowCarControl();
            }
        });
        note(setup, "AC commands try inside DiAuto first, then as the ADB shell, so AC_GET / AC_SET can stay ✗.");

        LinearLayout keys = card("Car keys");
        note(keys, "Choose what each car key does. A single press replaces the key's normal job; "
                + "with only a double press set, a single press keeps working (about half a second later).");
        for (int b = 0; b < CarKeys.BTN_CODE.length; b++) buttonRows(keys, b);

        LinearLayout other = card("Other keys");
        note(other, "For a key that isn't in the list above: assign it by pressing it on the car.");
        for (int s = 0; s < CarKeys.SLOTS; s++) slotRows(other, s);

        climateCard();

        LinearLayout tryCard = card("Try an action");
        note(tryCard, "Runs the action now, to check the car accepts it.");
        choiceRow(tryCard, "Action", CarActions.NAMES, CarActions.NONE, new Choice() {
            public void chose(int which) {
                if (which != CarActions.NONE) CarActions.run(CarControlsActivity.this, which);
            }
        }, false);

        bufferCard();

        LinearLayout wake = card("Start with the car");
        note(wake, "BYD units sleep instead of switching off, so DiAuto rarely gets a boot signal. "
                + "With the wheel key service on, DiAuto runs its own Auto-start (Settings → Auto-start) "
                + "every time the car wakes it up.");
    }

    // ---- audio / video buffer ----

    private static String[] msNames(int[] values) {
        String[] n = new String[values.length];
        for (int i = 0; i < values.length; i++) n[i] = values[i] == 0 ? "Off" : values[i] + " ms";
        return n;
    }

    private static int indexOf(int[] values, int v) {
        for (int i = 0; i < values.length; i++) if (values[i] == v) return i;
        return 0;
    }

    private void bufferCard() {
        LinearLayout card = card("Audio & video buffer");
        note(card, "Like DiPlay's buffer: Android Auto arrives over Wi-Fi in bursts, so DiAuto holds a little back "
                + "and plays it smoothly. More buffer = fewer cuts, but a later start. Changes apply from the next connection.");
        final int[] audio = AvBuffer.AUDIO_MS;
        final int[] video = AvBuffer.VIDEO_MS;
        choiceRow(card, "Audio buffer (music)", msNames(audio),
                indexOf(audio, CarActions.prefs(this).getInt(AvBuffer.KEY_AUDIO, AvBuffer.DEFAULT_AUDIO_MS)),
                new Choice() {
                    public void chose(int which) {
                        AvBuffer.set(CarControlsActivity.this, AvBuffer.KEY_AUDIO, audio[which]);
                    }
                }, true);
        choiceRow(card, "Video buffer", msNames(video),
                indexOf(video, CarActions.prefs(this).getInt(AvBuffer.KEY_VIDEO, AvBuffer.DEFAULT_VIDEO_MS)),
                new Choice() {
                    public void chose(int which) {
                        AvBuffer.set(CarControlsActivity.this, AvBuffer.KEY_VIDEO, video[which]);
                    }
                }, true);
        final int[] chans = CarP2p.CHANNELS;
        String[] chanNames = new String[chans.length];
        for (int i = 0; i < chans.length; i++) chanNames[i] = CarP2p.name(chans[i]);
        choiceRow(card, "WiFi Direct channel", chanNames,
                indexOf(chans, CarActions.prefs(this).getInt(CarP2p.KEY, CarP2p.DEFAULT)),
                new Choice() {
                    public void chose(int which) {
                        CarActions.prefs(CarControlsActivity.this).edit().putInt(CarP2p.KEY, chans[which]).apply();
                    }
                }, true);
        note(card, "The channel Android Auto's WiFi Direct network uses. Channel 6 (2.4 GHz) lets the phone join even "
                + "when the car isn't on any Wi-Fi network. Try 36-48 for smoother video if your phone joins them. Applies from the next connection.");
        note(card, "Navigation voice and system sounds are never delayed. The video buffer also delays touches by the same time, so keep it small.");
    }

    // ---- setup ----

    private void refreshStatus() {
        if (serviceStatus != null) {
            serviceStatus.setText(WheelKeyService.connected() ? "Wheel key service: on ✓"
                    : "Wheel key service: off. Turn it on so DiAuto can see the car keys.");
        }
        if (permissionStatus != null) {
            permissionStatus.setText((CarActions.acAllowed(this) ? "Car control: allowed ✓" : "Car control: not allowed yet")
                    + "\n" + CarActions.acStatus(this));
        }
        if (adbStatus != null && adbStatus.getText().length() == 0) {
            adbStatus.setText("ADB: not tested yet");
        }
    }

    private void testAdb() {
        adbStatus.setText("ADB: connecting… (allow the prompt if it appears)");
        background(new Runnable() {
            public void run() {
                final String out = LocalAdb.shell(CarControlsActivity.this, "echo DIAUTO_OK");
                main.post(new Runnable() {
                    public void run() {
                        if (out != null && out.contains("DIAUTO_OK")) {
                            adbStatus.setText("ADB: connected ✓");
                        } else {
                            adbStatus.setText("ADB: " + (out == null ? LocalAdb.lastError() : out.trim())
                                    + "\nTurn on USB debugging / wireless ADB in the car's developer options, then try again.");
                        }
                    }
                });
            }
        });
    }

    private void enableService() {
        serviceStatus.setText("Wheel key service: turning on… (allow the ADB prompt if it appears)");
        background(new Runnable() {
            public void run() {
                final String problem = WheelKeyService.enableOverAdb(CarControlsActivity.this);
                main.postDelayed(new Runnable() {
                    public void run() {
                        if (WheelKeyService.connected()) {
                            refreshStatus();
                        } else {
                            serviceStatus.setText("Wheel key service: not on yet"
                                    + (problem.length() > 0 ? " (" + problem + ")" : "")
                                    + ". Use \"Open accessibility settings\" and switch on DiAuto wheel keys.");
                        }
                    }
                }, 1500);
            }
        });
    }

    private void openAccessibility() {
        try {
            Intent i = new Intent();
            i.setComponent(new ComponentName("com.byd.systemsettings",
                    "com.byd.systemsettings.accessibility.AccessibilityMainActivity"));
            startActivity(i);
            return;
        } catch (Throwable ignored) {
        }
        try {
            startActivity(new Intent("android.settings.ACCESSIBILITY_SETTINGS"));
            return;
        } catch (Throwable ignored) {
        }
        background(new Runnable() {
            public void run() {
                CarActions.adb(CarControlsActivity.this,
                        "am start -n com.byd.systemsettings/.accessibility.AccessibilityMainActivity");
            }
        });
    }

    private void allowCarControl() {
        permissionStatus.setText("Allowing car control over ADB…");
        background(new Runnable() {
            public void run() {
                final String problems = CarActions.grantAc(CarControlsActivity.this);
                main.post(new Runnable() {
                    public void run() {
                        if (!CarActions.acAllowed(CarControlsActivity.this)) CarActions.requestAc(CarControlsActivity.this);
                        refreshStatus();
                        if (problems.length() > 0) permissionStatus.append("\n" + problems);
                    }
                });
            }
        });
    }

    /** Activity.onRequestPermissionsResult (API 23; not in the build's android.jar). */
    public void onRequestPermissionsResult(int code, String[] permissions, int[] results) {
        refreshStatus();
    }

    // ---- keys ----

    private void buttonRows(LinearLayout card, final int b) {
        subtitle(card, CarKeys.BTN_NAMES[b]);
        int[] order = {CarKeys.PRESS_SINGLE, CarKeys.PRESS_DOUBLE, CarKeys.PRESS_LONG};
        for (final int press : order) {
            if (press == CarKeys.PRESS_DOUBLE && !CarKeys.BTN_DOUBLE[b]) continue;
            if (press == CarKeys.PRESS_LONG && CarKeys.BTN_LONG[b] <= 0) continue;
            choiceRow(card, PRESS_TITLES[press], CarActions.NAMES, CarKeys.btnAction(this, b, press), new Choice() {
                public void chose(int which) {
                    CarKeys.setBtnAction(CarControlsActivity.this, b, press, which);
                }
            }, true);
        }
    }

    private String keyLabel(int slot) {
        int code = CarKeys.code(this, slot);
        return code > 0 ? "Key: " + CarKeys.keyName(code) + " · tap to change" : "Key: none · tap to assign";
    }

    private void slotRows(LinearLayout card, final int slot) {
        subtitle(card, "Other key " + (slot + 1));
        final Button[] keyButton = new Button[1];
        keyButton[0] = button(card, keyLabel(slot), new View.OnClickListener() {
            public void onClick(View v) {
                if (!WheelKeyService.connected()) {
                    CarActions.toast(CarControlsActivity.this, "Turn on the wheel key service first");
                    return;
                }
                keyButton[0].setText("Press the car key now…");
                CarKeys.startLearning(slot, new CarKeys.LearnListener() {
                    public void learnt(int s, int code) {
                        keyButton[0].setText(keyLabel(s));
                    }

                    public void timedOut(int s) {
                        keyButton[0].setText(keyLabel(s));
                        CarActions.toast(CarControlsActivity.this, "No key pressed. If the key shows nothing, DiAuto can't use it.");
                    }
                });
            }
        });
        final TextView warning = note(card, "Single press replaces this key's normal job.");
        warning.setVisibility(CarKeys.press(this, slot) == CarKeys.PRESS_SINGLE ? View.VISIBLE : View.GONE);
        choiceRow(card, "Press", CarKeys.PRESS_NAMES, CarKeys.press(this, slot), new Choice() {
            public void chose(int which) {
                CarKeys.setPress(CarControlsActivity.this, slot, which);
                warning.setVisibility(which == CarKeys.PRESS_SINGLE ? View.VISIBLE : View.GONE);
            }
        }, true);
        choiceRow(card, "Action", CarActions.NAMES, CarKeys.action(this, slot), new Choice() {
            public void chose(int which) {
                CarKeys.setAction(CarControlsActivity.this, slot, which);
            }
        }, true);
    }

    // ---- climate screen ----

    private String screenLabel() {
        String comp = CarActions.prefs(this).getString(CarActions.KEY_SCREEN, "");
        if (comp != null && comp.length() > 0) return "Climate screen: " + comp;
        return CarActions.defaultScreen(this) != null ? "Climate screen: automatic (BYD climate)"
                : "Climate screen: not found, use Capture";
    }

    private void climateCard() {
        LinearLayout card = card("Climate screen");
        final TextView status = status(card);
        status.setText(screenLabel());
        button(card, "Capture current screen", new View.OnClickListener() {
            public void onClick(View v) {
                status.setText("Reading the last screen…");
                background(new Runnable() {
                    public void run() {
                        final String comp = CarActions.captureScreen(CarControlsActivity.this);
                        if (comp != null) {
                            CarActions.prefs(CarControlsActivity.this).edit().putString(CarActions.KEY_SCREEN, comp).apply();
                        }
                        main.post(new Runnable() {
                            public void run() {
                                status.setText(comp != null ? "Saved: " + comp
                                        : screenLabel() + " · couldn't read it (is ADB allowed?)");
                            }
                        });
                    }
                });
            }
        });
        button(card, "Use the automatic screen", new View.OnClickListener() {
            public void onClick(View v) {
                CarActions.prefs(CarControlsActivity.this).edit().remove(CarActions.KEY_SCREEN).apply();
                status.setText(screenLabel());
            }
        });
        note(card, "Only needed if the automatic screen doesn't open: open the car's climate screen, "
                + "come straight back here and press Capture.");
    }

    // ---- widgets ----

    private interface Choice {
        void chose(int which);
    }

    private void header() {
        LinearLayout bar = new LinearLayout(this);
        bar.setOrientation(LinearLayout.HORIZONTAL);
        bar.setGravity(Gravity.CENTER_VERTICAL);
        TextView back = new TextView(this);
        back.setText("‹");
        back.setTextColor(TEXT);
        back.setTextSize(TypedValue.COMPLEX_UNIT_SP, 34);
        back.setPadding(0, 0, px(16), px(4));
        back.setOnClickListener(new View.OnClickListener() {
            public void onClick(View v) {
                finish();
            }
        });
        bar.addView(back);
        TextView t = new TextView(this);
        t.setText("BYD car controls");
        t.setTextColor(TEXT);
        t.setTextSize(TypedValue.COMPLEX_UNIT_SP, 26);
        t.setTypeface(Typeface.DEFAULT_BOLD);
        bar.addView(t);
        content.addView(bar, new LinearLayout.LayoutParams(-1, -2));
    }

    private LinearLayout card(String title) {
        LinearLayout c = new LinearLayout(this);
        c.setOrientation(LinearLayout.VERTICAL);
        c.setPadding(px(20), px(16), px(20), px(20));
        c.setBackground(rounded(CARD, 0, 0));
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(-1, -2);
        lp.topMargin = px(20);
        content.addView(c, lp);
        TextView t = new TextView(this);
        t.setText(title);
        t.setTextColor(accent);
        t.setTextSize(TypedValue.COMPLEX_UNIT_SP, 18);
        t.setTypeface(Typeface.DEFAULT_BOLD);
        c.addView(t);
        return c;
    }

    private void subtitle(LinearLayout card, String text) {
        TextView t = new TextView(this);
        t.setText(text);
        t.setTextColor(TEXT);
        t.setTextSize(TypedValue.COMPLEX_UNIT_SP, 17);
        t.setTypeface(Typeface.DEFAULT_BOLD);
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(-1, -2);
        lp.topMargin = px(18);
        card.addView(t, lp);
    }

    private TextView note(LinearLayout card, String text) {
        TextView t = new TextView(this);
        t.setText(text);
        t.setTextColor(MUTED);
        t.setTextSize(TypedValue.COMPLEX_UNIT_SP, 14);
        t.setLineSpacing(0, 1.15f);
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(-1, -2);
        lp.topMargin = px(8);
        card.addView(t, lp);
        return t;
    }

    private TextView status(LinearLayout card) {
        TextView t = new TextView(this);
        t.setTextColor(TEXT);
        t.setTextSize(TypedValue.COMPLEX_UNIT_SP, 15);
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(-1, -2);
        lp.topMargin = px(12);
        card.addView(t, lp);
        return t;
    }

    private void divider(LinearLayout card) {
        View v = new View(this);
        v.setBackgroundColor(LINE);
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(-1, Math.max(1, px(1)));
        lp.topMargin = px(16);
        card.addView(v, lp);
    }

    private Button button(LinearLayout card, String text, View.OnClickListener click) {
        Button b = new Button(this);
        b.setText(text);
        b.setAllCaps(false);
        b.setTextColor(TEXT);
        b.setTextSize(TypedValue.COMPLEX_UNIT_SP, 15);
        b.setBackground(rounded(0x00000000, accent, 1.5f));
        b.setOnClickListener(click);
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(-1, px(52));
        lp.topMargin = px(10);
        card.addView(b, lp);
        return b;
    }

    /** A row with the label on the left and the chosen value on the right; tap opens a list. */
    private void choiceRow(LinearLayout card, final String label, final String[] names, int current,
            final Choice choice, final boolean showValue) {
        final int[] selected = {current < 0 || current >= names.length ? 0 : current};
        LinearLayout row = new LinearLayout(this);
        row.setOrientation(LinearLayout.HORIZONTAL);
        row.setGravity(Gravity.CENTER_VERTICAL);
        row.setPadding(px(16), 0, px(16), 0);
        row.setBackground(rounded(0xFF1C2738, 0, 0));
        TextView l = new TextView(this);
        l.setText(label);
        l.setTextColor(TEXT);
        l.setTextSize(TypedValue.COMPLEX_UNIT_SP, 15);
        row.addView(l, new LinearLayout.LayoutParams(0, -2, 1));
        final TextView v = new TextView(this);
        v.setText((showValue ? names[selected[0]] : "Choose") + "  ›");
        v.setTextColor(selected[0] == 0 ? MUTED : accent);
        v.setTextSize(TypedValue.COMPLEX_UNIT_SP, 15);
        v.setGravity(Gravity.END);
        row.addView(v, new LinearLayout.LayoutParams(-2, -2));
        row.setOnClickListener(new View.OnClickListener() {
            public void onClick(View view) {
                new AlertDialog.Builder(CarControlsActivity.this)
                        .setTitle(label)
                        .setSingleChoiceItems(names, showValue ? selected[0] : -1, new DialogInterface.OnClickListener() {
                            public void onClick(DialogInterface d, int which) {
                                d.dismiss();
                                if (showValue) {
                                    selected[0] = which;
                                    v.setText(names[which] + "  ›");
                                    v.setTextColor(which == 0 ? MUTED : accent);
                                }
                                choice.chose(which);
                            }
                        })
                        .setNegativeButton(android.R.string.cancel, null)
                        .show();
            }
        });
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(-1, px(52));
        lp.topMargin = px(8);
        card.addView(row, lp);
    }

    private GradientDrawable rounded(int fill, int stroke, float strokeDp) {
        GradientDrawable g = new GradientDrawable();
        g.setCornerRadius(px(14));
        g.setColor(fill);
        if (strokeDp > 0) g.setStroke(Math.max(1, (int) (strokeDp * dp)), stroke);
        return g;
    }

    private int color(String name, int fallback) {
        try {
            int id = getResources().getIdentifier(name, "color", getPackageName());
            if (id != 0) return getResources().getColor(id);
        } catch (Throwable ignored) {
        }
        return fallback;
    }

    private int px(float v) {
        return (int) (v * dp + 0.5f);
    }

    private static void background(Runnable r) {
        new Thread(r, "DiAuto-CarControls").start();
    }
}
