package com.andrerinas.openheadunit.byd;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.Context;
import android.content.DialogInterface;
import android.content.SharedPreferences;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.os.Bundle;
import android.util.TypedValue;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.SeekBar;
import android.widget.TextView;

/**
 * Settings → Picture & sound: everything that decides how smooth Android Auto is on the car, on
 * one page. The video rows write DiAuto's own settings (the same values its Settings screen
 * shows); smooth video and the sound adjustments are the mod's. "Recommended for this car" puts
 * back the values chosen from the car's reports.
 */
public final class TuningActivity extends Activity {
    private static final int BG = 0xFF0C111B;
    private static final int CARD = 0xFF151E2C;
    private static final int ROW = 0xFF1C2738;
    private static final int TEXT = 0xFFF1F5FC;
    private static final int MUTED = 0xFFA8B6CA;
    private static final int ACCENT = 0xFF009688;

    // DiAuto's own keys and values (g1.j1).
    static final String CODEC = "video-codec";
    static final String RESOLUTION = "resolutionId";
    static final String FPS = "fps-limit";
    static final String VIEW_MODE = "view-mode";
    static final String LOW_LATENCY = "debug-video-low-latency";
    static final String DPI = "dpi-pixel-density";
    /** Set by DiAuto after sessions that rendered nothing; it caps the profile until cleared. */
    static final String STARVATION_CAP = "video-profile-starvation-cap";

    private static final String[] CODEC_VALUES = {"Auto", "H.264", "H.265"};
    private static final String[] CODEC_NAMES = {"Auto", "H.264", "H.265 (HEVC)"};
    private static final int[] RESOLUTION_IDS = {0, 1, 2, 3};
    private static final String[] RESOLUTION_NAMES = {"Auto", "800x480", "1280x720", "1920x1080 (more than this screen)"};
    private static final int[] FPS_VALUES = {30, 60};
    private static final int[] VIEW_VALUES = {0, 1, 2};
    private static final String[] VIEW_NAMES = {"SurfaceView (direct output)", "TextureView", "OpenGL"};
    private static final int[] DPI_VALUES = {0, 120, 140, 160, 180, 200, 240};

    private float dp;
    private LinearLayout content;

    static SharedPreferences settings(Context c) {
        return c.getSharedPreferences("settings", 0);
    }

    /** The values chosen from the Qin Plus DM-i reports (link-limited 2.4 GHz, HEVC decoder present). */
    static void applyRecommended(Context c) {
        settings(c).edit()
                .putString(CODEC, "H.265")
                .putInt(RESOLUTION, 2)
                .putInt(FPS, 30)
                .putInt(VIEW_MODE, 0)
                .putBoolean(LOW_LATENCY, true)
                .putBoolean(STARVATION_CAP, false)
                .apply();
        CarActions.prefs(c).edit()
                .putInt(AvBuffer.KEY_AUDIO, AvBuffer.DEFAULT_AUDIO_MS)
                .putInt(AvBuffer.KEY_VIDEO, AvBuffer.DEFAULT_VIDEO_MS)
                .apply();
        AvBuffer.load(c);
    }

    @Override
    protected void onCreate(Bundle saved) {
        super.onCreate(saved);
        dp = getResources().getDisplayMetrics().density;
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

    private void rebuild() {
        content.removeAllViews();
        build();
    }

    private void build() {
        header();
        final SharedPreferences s = settings(this);
        final SharedPreferences mine = CarActions.prefs(this);

        LinearLayout video = card("Video");
        note(video, "Changes apply from the next Android Auto connection.");
        choice(video, "Video codec", CODEC_NAMES, indexOf(CODEC_VALUES, s.getString(CODEC, "Auto")), new Choice() {
            public void chose(int w) {
                s.edit().putString(CODEC, CODEC_VALUES[w]).apply();
            }
        });
        choice(video, "Resolution", RESOLUTION_NAMES, indexOf(RESOLUTION_IDS, s.getInt(RESOLUTION, 0)), new Choice() {
            public void chose(int w) {
                s.edit().putInt(RESOLUTION, RESOLUTION_IDS[w]).putBoolean(STARVATION_CAP, false).apply();
            }
        });
        choice(video, "FPS limit", names(FPS_VALUES, " fps", null), indexOf(FPS_VALUES, s.getInt(FPS, 60)), new Choice() {
            public void chose(int w) {
                s.edit().putInt(FPS, FPS_VALUES[w]).putBoolean(STARVATION_CAP, false).apply();
            }
        });
        choice(video, "View mode", VIEW_NAMES, indexOf(VIEW_VALUES, s.getInt(VIEW_MODE, 1)), new Choice() {
            public void chose(int w) {
                s.edit().putInt(VIEW_MODE, VIEW_VALUES[w]).apply();
            }
        });
        toggle(video, "Low latency decoding", s.getBoolean(LOW_LATENCY, false), new Toggle() {
            public void set(boolean on) {
                s.edit().putBoolean(LOW_LATENCY, on).apply();
            }
        });
        choice(video, "Screen density (DPI)", names(DPI_VALUES, "", "Auto"), indexOf(DPI_VALUES, s.getInt(DPI, 0)), new Choice() {
            public void chose(int w) {
                s.edit().putInt(DPI, DPI_VALUES[w]).apply();
            }
        });
        note(video, "Higher DPI makes Android Auto's buttons and text bigger, lower makes them smaller.");

        LinearLayout smooth = card("Smooth video");
        note(smooth, "Wi-Fi delivers Android Auto in bursts. A buffer holds a little back and plays it evenly. "
                + "The video buffer also delays touches by the same time, so keep it small.");
        choice(smooth, "Video buffer", names(AvBuffer.VIDEO_MS, " ms", "Off"),
                indexOf(AvBuffer.VIDEO_MS, mine.getInt(AvBuffer.KEY_VIDEO, AvBuffer.DEFAULT_VIDEO_MS)), new Choice() {
                    public void chose(int w) {
                        AvBuffer.set(TuningActivity.this, AvBuffer.KEY_VIDEO, AvBuffer.VIDEO_MS[w]);
                    }
                });
        choice(smooth, "Audio buffer (music)", names(AvBuffer.AUDIO_MS, " ms", "Off"),
                indexOf(AvBuffer.AUDIO_MS, mine.getInt(AvBuffer.KEY_AUDIO, AvBuffer.DEFAULT_AUDIO_MS)), new Choice() {
                    public void chose(int w) {
                        AvBuffer.set(TuningActivity.this, AvBuffer.KEY_AUDIO, AvBuffer.AUDIO_MS[w]);
                    }
                });

        soundCard(mine);

        LinearLayout reset = card("Recommended for this car");
        note(reset, "H.265, 1280x720, 30 fps, SurfaceView, low latency decoding on, video buffer "
                + AvBuffer.DEFAULT_VIDEO_MS + " ms, audio buffer " + AvBuffer.DEFAULT_AUDIO_MS
                + " ms. Sound adjustments and DPI are left as they are.");
        button(reset, "Use the recommended values", new View.OnClickListener() {
            public void onClick(View v) {
                applyRecommended(TuningActivity.this);
                CarActions.toast(TuningActivity.this, "Recommended values set");
                rebuild();
            }
        });
    }

    private void soundCard(final SharedPreferences mine) {
        LinearLayout sound = card("Sound");
        note(sound, "Only Android Auto's music is changed; the radio and the car's own sounds are not.");
        final TextView state = note(sound, AudioFx.state());
        toggle(sound, "Sound adjustments", mine.getBoolean(AudioFx.KEY_ON, false), new Toggle() {
            public void set(boolean on) {
                mine.edit().putBoolean(AudioFx.KEY_ON, on).apply();
                AudioFx.update(TuningActivity.this);
                state.setText(AudioFx.state());
            }
        });
        subtitle(sound, "Equalizer");
        int[] centers = AudioFx.centersHz();
        final int min = AudioFx.minMb();
        final int max = AudioFx.maxMb();
        for (int b = 0; b < centers.length; b++) {
            final String key = AudioFx.KEY_BAND + b;
            slider(sound, hz(centers[b]), min, max, mine.getInt(key, 0), " dB", 100, new Slide() {
                public void moved(int v) {
                    mine.edit().putInt(key, v).apply();
                    AudioFx.update(TuningActivity.this);
                }
            });
        }
        subtitle(sound, "Effects");
        slider(sound, "Bass", 0, AudioFx.MAX_STRENGTH, mine.getInt(AudioFx.KEY_BASS, 0), "%", 10, new Slide() {
            public void moved(int v) {
                mine.edit().putInt(AudioFx.KEY_BASS, v).apply();
                AudioFx.update(TuningActivity.this);
            }
        });
        slider(sound, "Surround", 0, AudioFx.MAX_STRENGTH, mine.getInt(AudioFx.KEY_VIRT, 0), "%", 10, new Slide() {
            public void moved(int v) {
                mine.edit().putInt(AudioFx.KEY_VIRT, v).apply();
                AudioFx.update(TuningActivity.this);
            }
        });
        slider(sound, "Loudness", 0, AudioFx.MAX_LOUD_MB, mine.getInt(AudioFx.KEY_LOUD, 0), " dB", 100, new Slide() {
            public void moved(int v) {
                mine.edit().putInt(AudioFx.KEY_LOUD, v).apply();
                AudioFx.update(TuningActivity.this);
            }
        });
        button(sound, "Reset sound to flat", new View.OnClickListener() {
            public void onClick(View v) {
                SharedPreferences.Editor e = mine.edit();
                for (int b = 0; b < 16; b++) e.remove(AudioFx.KEY_BAND + b);
                e.remove(AudioFx.KEY_BASS).remove(AudioFx.KEY_VIRT).remove(AudioFx.KEY_LOUD).apply();
                AudioFx.update(TuningActivity.this);
                rebuild();
            }
        });
    }

    // ---- values ----

    private static String hz(int f) {
        return f >= 1000 ? (f % 1000 == 0 ? f / 1000 + " kHz" : String.format(java.util.Locale.US, "%.1f kHz", f / 1000f)) : f + " Hz";
    }

    private static String[] names(int[] values, String unit, String zero) {
        String[] n = new String[values.length];
        for (int i = 0; i < values.length; i++) n[i] = values[i] == 0 && zero != null ? zero : values[i] + unit;
        return n;
    }

    private static int indexOf(int[] values, int v) {
        for (int i = 0; i < values.length; i++) if (values[i] == v) return i;
        return 0;
    }

    private static int indexOf(String[] values, String v) {
        for (int i = 0; i < values.length; i++) if (values[i].equals(v)) return i;
        return 0;
    }

    // ---- widgets (same look as the earlier car controls page) ----

    private interface Choice {
        void chose(int which);
    }

    private interface Toggle {
        void set(boolean on);
    }

    private interface Slide {
        void moved(int value);
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
        t.setText("Picture & sound");
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
        t.setTextColor(ACCENT);
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

    private void button(LinearLayout card, String text, View.OnClickListener click) {
        Button b = new Button(this);
        b.setText(text);
        b.setAllCaps(false);
        b.setTextColor(TEXT);
        b.setTextSize(TypedValue.COMPLEX_UNIT_SP, 15);
        b.setBackground(rounded(0x00000000, ACCENT, 1.5f));
        b.setOnClickListener(click);
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(-1, px(52));
        lp.topMargin = px(12);
        card.addView(b, lp);
    }

    private LinearLayout row(LinearLayout card, String label) {
        LinearLayout row = new LinearLayout(this);
        row.setOrientation(LinearLayout.HORIZONTAL);
        row.setGravity(Gravity.CENTER_VERTICAL);
        row.setPadding(px(16), 0, px(16), 0);
        row.setBackground(rounded(ROW, 0, 0));
        TextView l = new TextView(this);
        l.setText(label);
        l.setTextColor(TEXT);
        l.setTextSize(TypedValue.COMPLEX_UNIT_SP, 15);
        row.addView(l, new LinearLayout.LayoutParams(0, -2, 1));
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(-1, px(52));
        lp.topMargin = px(8);
        card.addView(row, lp);
        return row;
    }

    /** Label on the left, chosen value on the right; a tap opens the list. */
    private void choice(LinearLayout card, final String label, final String[] names, int current, final Choice choice) {
        final int[] selected = {current < 0 || current >= names.length ? 0 : current};
        LinearLayout row = row(card, label);
        final TextView v = new TextView(this);
        v.setText(names[selected[0]] + "  ›");
        v.setTextColor(ACCENT);
        v.setTextSize(TypedValue.COMPLEX_UNIT_SP, 15);
        v.setGravity(Gravity.END);
        row.addView(v, new LinearLayout.LayoutParams(-2, -2));
        row.setOnClickListener(new View.OnClickListener() {
            public void onClick(View view) {
                new AlertDialog.Builder(TuningActivity.this)
                        .setTitle(label)
                        .setSingleChoiceItems(names, selected[0], new DialogInterface.OnClickListener() {
                            public void onClick(DialogInterface d, int which) {
                                d.dismiss();
                                selected[0] = which;
                                v.setText(names[which] + "  ›");
                                choice.chose(which);
                            }
                        })
                        .setNegativeButton(android.R.string.cancel, null)
                        .show();
            }
        });
    }

    private void toggle(LinearLayout card, String label, boolean on, final Toggle toggle) {
        final boolean[] state = {on};
        LinearLayout row = row(card, label);
        final TextView v = new TextView(this);
        v.setTextSize(TypedValue.COMPLEX_UNIT_SP, 15);
        v.setGravity(Gravity.END);
        showToggle(v, on);
        row.addView(v, new LinearLayout.LayoutParams(-2, -2));
        row.setOnClickListener(new View.OnClickListener() {
            public void onClick(View view) {
                state[0] = !state[0];
                showToggle(v, state[0]);
                toggle.set(state[0]);
            }
        });
    }

    private static void showToggle(TextView v, boolean on) {
        v.setText(on ? "On" : "Off");
        v.setTextColor(on ? ACCENT : MUTED);
    }

    /** A labelled slider; the value is shown divided by {@code div} with the unit. */
    private void slider(LinearLayout card, String label, final int min, int max, int value, final String unit,
            final int div, final Slide slide) {
        LinearLayout box = new LinearLayout(this);
        box.setOrientation(LinearLayout.VERTICAL);
        box.setPadding(px(16), px(8), px(16), px(8));
        box.setBackground(rounded(ROW, 0, 0));
        LinearLayout top = new LinearLayout(this);
        top.setOrientation(LinearLayout.HORIZONTAL);
        TextView l = new TextView(this);
        l.setText(label);
        l.setTextColor(TEXT);
        l.setTextSize(TypedValue.COMPLEX_UNIT_SP, 15);
        top.addView(l, new LinearLayout.LayoutParams(0, -2, 1));
        final TextView v = new TextView(this);
        v.setTextColor(ACCENT);
        v.setTextSize(TypedValue.COMPLEX_UNIT_SP, 15);
        top.addView(v, new LinearLayout.LayoutParams(-2, -2));
        box.addView(top);
        SeekBar bar = new SeekBar(this);
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
        box.addView(bar, new LinearLayout.LayoutParams(-1, px(40)));
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(-1, -2);
        lp.topMargin = px(8);
        card.addView(box, lp);
    }

    private static String format(int v, String unit, int div) {
        if (" dB".equals(unit)) return String.format(java.util.Locale.US, "%+.1f dB", v / (float) div);
        return (v / div) + unit;
    }

    private GradientDrawable rounded(int fill, int stroke, float strokeDp) {
        GradientDrawable g = new GradientDrawable();
        g.setCornerRadius(px(14));
        g.setColor(fill);
        if (strokeDp > 0) g.setStroke(Math.max(1, (int) (strokeDp * dp)), stroke);
        return g;
    }

    private int px(float v) {
        return (int) (v * dp + 0.5f);
    }
}
