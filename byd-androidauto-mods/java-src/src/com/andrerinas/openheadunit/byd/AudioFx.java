package com.andrerinas.openheadunit.byd;

import android.content.Context;
import android.content.SharedPreferences;
import android.media.audiofx.BassBoost;
import android.media.audiofx.Equalizer;
import android.media.audiofx.LoudnessEnhancer;
import android.media.audiofx.Virtualizer;
import android.util.Log;

/**
 * Sound adjustments like DiPlay's (equalizer, bass, surround, loudness), applied only to Android
 * Auto's media (music) track: the effects attach to DiAuto's own stereo
 * AudioTrack session (found in AvBuffer.audioWrite), so the radio and the car's own sounds are
 * never touched. Values live in the mod's prefs and apply at once while a track plays.
 */
public final class AudioFx {
    private static final String TAG = "DiAuto-AudioFx";

    static final String KEY_ON = "fx_on";
    static final String KEY_BAND = "fx_band_";
    static final String KEY_BASS = "fx_bass";
    static final String KEY_VIRT = "fx_virt";
    static final String KEY_LOUD = "fx_loud";
    /** Bass and surround strength 0..1000 (Android's own scale); loudness gain 0..1500 mB. */
    static final int MAX_STRENGTH = 1000;
    static final int MAX_LOUD_MB = 1500;

    private static int session = -1;
    private static Equalizer eq;
    private static BassBoost bass;
    private static Virtualizer virt;
    private static LoudnessEnhancer loud;
    private static String lastError = "";

    /** Band info read from the last equalizer: centre frequencies (Hz) and the level range (mB). */
    private static int[] centersHz = {60, 230, 910, 3600, 14000};
    private static short minMb = -1500;
    private static short maxMb = 1500;

    private AudioFx() {}

    /** From AvBuffer.audioWrite for every stereo track: (re)attaches when the session changes. */
    static void attach(Context c, int audioSession) {
        if (audioSession <= 0) return;
        synchronized (AudioFx.class) {
            if (audioSession == session) return;
            releaseLocked();
            session = audioSession;
            try {
                eq = new Equalizer(0, audioSession);
                short bands = eq.getNumberOfBands();
                short[] range = eq.getBandLevelRange();
                minMb = range[0];
                maxMb = range[1];
                int[] centers = new int[bands];
                for (short b = 0; b < bands; b++) centers[b] = eq.getCenterFreq(b) / 1000;
                centersHz = centers;
            } catch (Throwable t) {
                eq = null;
                lastError = "equalizer: " + t;
            }
            try {
                bass = new BassBoost(0, audioSession);
            } catch (Throwable t) {
                bass = null;
                lastError = "bass: " + t;
            }
            try {
                virt = new Virtualizer(0, audioSession);
            } catch (Throwable t) {
                virt = null;
                lastError = "surround: " + t;
            }
            try {
                loud = new LoudnessEnhancer(audioSession);
            } catch (Throwable t) {
                loud = null;
                lastError = "loudness: " + t;
            }
            Log.i(TAG, "attached to session " + audioSession + (lastError.length() > 0 ? " (" + lastError + ")" : ""));
        }
        update(c);
    }

    /** Applies the saved values to the attached effects. Safe to call from the settings page. */
    static void update(Context c) {
        SharedPreferences p = CarActions.prefs(c);
        boolean on = p.getBoolean(KEY_ON, false);
        synchronized (AudioFx.class) {
            try {
                if (eq != null) {
                    if (on) {
                        short bands = eq.getNumberOfBands();
                        for (short b = 0; b < bands; b++) {
                            int v = clamp(p.getInt(KEY_BAND + b, 0), minMb, maxMb);
                            eq.setBandLevel(b, (short) v);
                        }
                    }
                    eq.setEnabled(on);
                }
                if (bass != null) {
                    int v = clamp(p.getInt(KEY_BASS, 0), 0, MAX_STRENGTH);
                    if (on && v > 0) bass.setStrength((short) v);
                    bass.setEnabled(on && v > 0);
                }
                if (virt != null) {
                    int v = clamp(p.getInt(KEY_VIRT, 0), 0, MAX_STRENGTH);
                    if (on && v > 0) virt.setStrength((short) v);
                    virt.setEnabled(on && v > 0);
                }
                if (loud != null) {
                    int v = clamp(p.getInt(KEY_LOUD, 0), 0, MAX_LOUD_MB);
                    if (on && v > 0) loud.setTargetGain(v);
                    loud.setEnabled(on && v > 0);
                }
            } catch (Throwable t) {
                lastError = "apply: " + t;
                Log.w(TAG, "could not apply sound adjustments", t);
            }
        }
    }

    static synchronized int[] centersHz() {
        return centersHz.clone();
    }

    static synchronized int minMb() {
        return minMb;
    }

    static synchronized int maxMb() {
        return maxMb;
    }

    static synchronized String state() {
        if (session < 0) return "Starts with the next Android Auto music";
        if (eq == null && bass == null && virt == null && loud == null) return "This car refused sound effects: " + lastError;
        return "Working on Android Auto audio" + (lastError.length() > 0 ? " (partly: " + lastError + ")" : "");
    }

    private static void releaseLocked() {
        try {
            if (eq != null) eq.release();
        } catch (Throwable ignored) {
        }
        try {
            if (bass != null) bass.release();
        } catch (Throwable ignored) {
        }
        try {
            if (virt != null) virt.release();
        } catch (Throwable ignored) {
        }
        try {
            if (loud != null) loud.release();
        } catch (Throwable ignored) {
        }
        eq = null;
        bass = null;
        virt = null;
        loud = null;
        lastError = "";
    }

    private static int clamp(int v, int lo, int hi) {
        return v < lo ? lo : v > hi ? hi : v;
    }
}
