package com.shilapi.xcertplay;

import android.content.Context;
import android.graphics.drawable.GradientDrawable;
import android.util.TypedValue;
import android.view.View;
import android.widget.Button;
import android.widget.LinearLayout;

import com.shilapi.xcertplay.audio.AudioEffectsEngine;
import com.shilapi.xcertplay.settings.SettingsTheme;

import kotlin.jvm.functions.Function0;

/** "Reset sound to default" for both settings screens: zero every adjustment, then rebuild the rows. */
public final class AudioReset {
    private AudioReset() {}

    static void reset(Context c) {
        android.content.SharedPreferences.Editor e = c.getSharedPreferences("diplay_audio", 0).edit();
        e.putInt("diplay_audio_bass", 0).putInt("diplay_audio_virt", 0).putInt("diplay_audio_loud", 0);
        for (int i = 0; i < 10; i++) e.putInt("diplay_audio_eq" + i, 0);
        e.commit();
        try {
            AudioEffectsEngine.apply(c);
        } catch (Throwable ignored) {
        }
        CarActions.toast(c, "Sound reset to default");
    }

    private static void clearAfterHeader(LinearLayout card) {
        while (card.getChildCount() > 1) card.removeViewAt(card.getChildCount() - 1);
    }

    /** Main settings → Audio card. */
    public static void addMain(final DiPlayActivity a, final LinearLayout card) {
        try {
            DiPlayActivity.diplayButton(a, card, "Reset sound to default", new Function0() {
                public Object invoke() {
                    reset(a);
                    clearAfterHeader(card);
                    new DiplayAudioContent(a).invoke(card);
                    return kotlin.Unit.INSTANCE;
                }
            });
        } catch (Throwable ignored) {
        }
    }

    /** CarPlay settings window → Audio page. */
    public static void addPopup(final Context c, final LinearLayout page) {
        try {
            Button b = new Button(c);
            b.setText("Reset sound to default");
            b.setAllCaps(false);
            b.setTextSize(TypedValue.COMPLEX_UNIT_SP, 15);
            int text = 0xFFFFFFFF;
            int stroke = 0xFF8FE3A8;
            try {
                text = SettingsTheme.OVERLAY.getTextPrimary();
                stroke = SettingsTheme.OVERLAY.getAccent();
            } catch (Throwable ignored) {
            }
            b.setTextColor(text);
            GradientDrawable bg = new GradientDrawable();
            float d = c.getResources().getDisplayMetrics().density;
            bg.setCornerRadius(14 * d);
            bg.setColor(0x00000000);
            bg.setStroke((int) (1.5f * d), stroke);
            b.setBackground(bg);
            LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(
                    LinearLayout.LayoutParams.MATCH_PARENT, (int) (48 * d));
            lp.topMargin = (int) (14 * d);
            b.setOnClickListener(new View.OnClickListener() {
                public void onClick(View v) {
                    reset(c);
                    clearAfterHeader(page);
                    DiplayPopup.maybeAddAudioPage("audio", page, c);
                }
            });
            page.addView(b, lp);
        } catch (Throwable ignored) {
        }
    }
}
