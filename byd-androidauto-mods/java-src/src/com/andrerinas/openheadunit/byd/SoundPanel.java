package com.andrerinas.openheadunit.byd;

import android.app.AlertDialog;
import android.content.Context;
import android.content.SharedPreferences;
import android.graphics.drawable.GradientDrawable;
import android.util.TypedValue;
import android.view.Gravity;
import android.view.View;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.SeekBar;
import android.widget.TextView;

/**
 * The sound adjustments (on/off, equalizer, bass, surround, loudness), built into any vertical
 * layout: the "Sound" card of Picture & sound, and the Equalizer panel opened from Quick Settings
 * while Android Auto keeps playing behind it.
 */
public final class SoundPanel {
    static final int TEXT = 0xFFF1F5FC;
    static final int MUTED = 0xFFA8B6CA;
    static final int ACCENT = 0xFF009688;
    static final int ROW = 0xFF1C2738;
    private static final int BG = 0xFF151E2C;

    private SoundPanel() {}

    /** Quick Settings → Equalizer: the controls in a dialog over Android Auto. */
    public static void showDialog(Context c) {
        final ScrollView scroll = new ScrollView(c);
        scroll.setBackgroundColor(BG);
        final LinearLayout box = new LinearLayout(c);
        box.setOrientation(LinearLayout.VERTICAL);
        int pad = px(c, 20);
        box.setPadding(pad, pad / 2, pad, pad);
        scroll.addView(box);
        fill(c, box);
        AlertDialog d = new AlertDialog.Builder(c)
                .setTitle("Equalizer")
                .setView(scroll)
                .setPositiveButton(android.R.string.ok, null)
                .create();
        d.show();
    }

    /** Adds the controls to {@code box}. "Reset sound to flat" rebuilds them in place. */
    static void fill(final Context c, final LinearLayout box) {
        final SharedPreferences mine = CarActions.prefs(c);
        final int first = box.getChildCount();
        note(c, box, "Only Android Auto's music is changed; the radio and the car's own sounds are not.");
        final TextView state = note(c, box, AudioFx.state());
        toggle(c, box, "Sound adjustments", mine.getBoolean(AudioFx.KEY_ON, false), new Toggle() {
            public void set(boolean on) {
                mine.edit().putBoolean(AudioFx.KEY_ON, on).apply();
                AudioFx.update(c);
                state.setText(AudioFx.state());
            }
        });
        subtitle(c, box, "Equalizer");
        int[] centers = AudioFx.centersHz();
        int min = AudioFx.minMb();
        int max = AudioFx.maxMb();
        for (int b = 0; b < centers.length; b++) {
            final String key = AudioFx.KEY_BAND + b;
            slider(c, box, hz(centers[b]), min, max, mine.getInt(key, 0), " dB", 100, new Slide() {
                public void moved(int v) {
                    mine.edit().putInt(key, v).apply();
                    AudioFx.update(c);
                }
            });
        }
        subtitle(c, box, "Effects");
        slider(c, box, "Bass", 0, AudioFx.MAX_STRENGTH, mine.getInt(AudioFx.KEY_BASS, 0), "%", 10, new Slide() {
            public void moved(int v) {
                mine.edit().putInt(AudioFx.KEY_BASS, v).apply();
                AudioFx.update(c);
            }
        });
        slider(c, box, "Surround", 0, AudioFx.MAX_STRENGTH, mine.getInt(AudioFx.KEY_VIRT, 0), "%", 10, new Slide() {
            public void moved(int v) {
                mine.edit().putInt(AudioFx.KEY_VIRT, v).apply();
                AudioFx.update(c);
            }
        });
        slider(c, box, "Loudness", 0, AudioFx.MAX_LOUD_MB, mine.getInt(AudioFx.KEY_LOUD, 0), " dB", 100, new Slide() {
            public void moved(int v) {
                mine.edit().putInt(AudioFx.KEY_LOUD, v).apply();
                AudioFx.update(c);
            }
        });
        Button reset = new Button(c);
        reset.setText("Reset sound to flat");
        reset.setAllCaps(false);
        reset.setTextColor(TEXT);
        reset.setTextSize(TypedValue.COMPLEX_UNIT_SP, 15);
        reset.setBackground(rounded(c, 0x00000000, ACCENT, 1.5f));
        reset.setOnClickListener(new View.OnClickListener() {
            public void onClick(View v) {
                SharedPreferences.Editor e = mine.edit();
                for (int b = 0; b < 16; b++) e.remove(AudioFx.KEY_BAND + b);
                e.remove(AudioFx.KEY_BASS).remove(AudioFx.KEY_VIRT).remove(AudioFx.KEY_LOUD).apply();
                AudioFx.update(c);
                box.removeViews(first, box.getChildCount() - first);
                fill(c, box);
            }
        });
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(-1, px(c, 52));
        lp.topMargin = px(c, 12);
        box.addView(reset, lp);
    }

    // ---- widgets ----

    private interface Toggle {
        void set(boolean on);
    }

    private interface Slide {
        void moved(int value);
    }

    private static String hz(int f) {
        return f >= 1000 ? (f % 1000 == 0 ? f / 1000 + " kHz" : String.format(java.util.Locale.US, "%.1f kHz", f / 1000f)) : f + " Hz";
    }

    private static void subtitle(Context c, LinearLayout box, String text) {
        TextView t = new TextView(c);
        t.setText(text);
        t.setTextColor(TEXT);
        t.setTextSize(TypedValue.COMPLEX_UNIT_SP, 17);
        t.setTypeface(android.graphics.Typeface.DEFAULT_BOLD);
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(-1, -2);
        lp.topMargin = px(c, 18);
        box.addView(t, lp);
    }

    private static TextView note(Context c, LinearLayout box, String text) {
        TextView t = new TextView(c);
        t.setText(text);
        t.setTextColor(MUTED);
        t.setTextSize(TypedValue.COMPLEX_UNIT_SP, 14);
        t.setLineSpacing(0, 1.15f);
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(-1, -2);
        lp.topMargin = px(c, 8);
        box.addView(t, lp);
        return t;
    }

    private static void toggle(Context c, LinearLayout box, String label, boolean on, final Toggle toggle) {
        final boolean[] state = {on};
        LinearLayout row = new LinearLayout(c);
        row.setOrientation(LinearLayout.HORIZONTAL);
        row.setGravity(Gravity.CENTER_VERTICAL);
        row.setPadding(px(c, 16), 0, px(c, 16), 0);
        row.setBackground(rounded(c, ROW, 0, 0));
        TextView l = new TextView(c);
        l.setText(label);
        l.setTextColor(TEXT);
        l.setTextSize(TypedValue.COMPLEX_UNIT_SP, 15);
        row.addView(l, new LinearLayout.LayoutParams(0, -2, 1));
        final TextView v = new TextView(c);
        v.setTextSize(TypedValue.COMPLEX_UNIT_SP, 15);
        showToggle(v, on);
        row.addView(v, new LinearLayout.LayoutParams(-2, -2));
        row.setOnClickListener(new View.OnClickListener() {
            public void onClick(View view) {
                state[0] = !state[0];
                showToggle(v, state[0]);
                toggle.set(state[0]);
            }
        });
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(-1, px(c, 52));
        lp.topMargin = px(c, 8);
        box.addView(row, lp);
    }

    private static void showToggle(TextView v, boolean on) {
        v.setText(on ? "On" : "Off");
        v.setTextColor(on ? ACCENT : MUTED);
    }

    /** A labelled slider; the value is shown divided by {@code div} with the unit. */
    private static void slider(Context c, LinearLayout box, String label, final int min, int max, int value,
            final String unit, final int div, final Slide slide) {
        LinearLayout item = new LinearLayout(c);
        item.setOrientation(LinearLayout.VERTICAL);
        item.setPadding(px(c, 16), px(c, 8), px(c, 16), px(c, 8));
        item.setBackground(rounded(c, ROW, 0, 0));
        LinearLayout top = new LinearLayout(c);
        top.setOrientation(LinearLayout.HORIZONTAL);
        TextView l = new TextView(c);
        l.setText(label);
        l.setTextColor(TEXT);
        l.setTextSize(TypedValue.COMPLEX_UNIT_SP, 15);
        top.addView(l, new LinearLayout.LayoutParams(0, -2, 1));
        final TextView v = new TextView(c);
        v.setTextColor(ACCENT);
        v.setTextSize(TypedValue.COMPLEX_UNIT_SP, 15);
        top.addView(v, new LinearLayout.LayoutParams(-2, -2));
        item.addView(top);
        SeekBar bar = new SeekBar(c);
        bar.setMax(max - min);
        int start = value < min ? min : value > max ? max : value;
        bar.setProgress(start - min);
        v.setText(format(start, unit, div));
        bar.setOnSeekBarChangeListener(new SeekBar.OnSeekBarChangeListener() {
            public void onProgressChanged(SeekBar s, int p, boolean user) {
                v.setText(format(p + min, unit, div));
                if (user) slide.moved(p + min);
            }

            public void onStartTrackingTouch(SeekBar s) {
            }

            public void onStopTrackingTouch(SeekBar s) {
            }
        });
        item.addView(bar, new LinearLayout.LayoutParams(-1, px(c, 40)));
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(-1, -2);
        lp.topMargin = px(c, 8);
        box.addView(item, lp);
    }

    private static String format(int v, String unit, int div) {
        if (" dB".equals(unit)) return String.format(java.util.Locale.US, "%+.1f dB", v / (float) div);
        return (v / div) + unit;
    }

    private static GradientDrawable rounded(Context c, int fill, int stroke, float strokeDp) {
        GradientDrawable g = new GradientDrawable();
        g.setCornerRadius(px(c, 14));
        g.setColor(fill);
        if (strokeDp > 0) g.setStroke(Math.max(1, px(c, strokeDp)), stroke);
        return g;
    }

    private static int px(Context c, float v) {
        return (int) (v * c.getResources().getDisplayMetrics().density + 0.5f);
    }
}
