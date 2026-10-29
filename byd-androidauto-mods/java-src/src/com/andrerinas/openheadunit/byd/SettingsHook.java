package com.andrerinas.openheadunit.byd;

import android.app.Activity;
import android.content.Context;
import android.content.Intent;

import com.andrerinas.openheadunit.main.settings.SettingItem;

import java.util.List;

/** Adds the "Picture & sound" row right under "Connection mode" in DiAuto's general settings. */
public final class SettingsHook {
    static final String ID = "pictureAndSound";

    private SettingsHook() {}

    /** Called from SettingsFragment.updateSettingsList right after the connection mode row is added. */
    @SuppressWarnings({"unchecked", "rawtypes"})
    public static void addEntry(List list, final Object fragment) {
        try {
            final Context c = (Context) fragment.getClass().getMethod("getContext").invoke(fragment);
            if (c == null) return;
            int name = c.getResources().getIdentifier("byd_picture_sound", "string", c.getPackageName());
            if (name == 0) name = android.R.string.untitled;
            list.add(new SettingItem.SettingEntry(ID, name, "Video codec, resolution, smooth video, equalizer",
                    "Picture & sound", "video codec hevc h265 resolution fps buffer smooth latency equalizer bass sound",
                    new m5.l() {
                        public Object invoke(Object stableId) {
                            open(c, fragment);
                            return null;
                        }
                    }));
        } catch (Throwable ignored) {
        }
    }

    /**
     * DiAuto's settings screen keeps its own copy of resolution, DPI, codec and so on from when it
     * opened, and its Save writes that copy back. It is closed here, so a later Save cannot undo
     * what was set on this page; the next time Settings opens it reads the new values.
     */
    private static void open(Context c, Object fragment) {
        c.startActivity(new Intent(c, TuningActivity.class));
        try {
            Activity host = (Activity) fragment.getClass().getMethod("getActivity").invoke(fragment);
            if (host != null && !"com.andrerinas.openheadunit.main.MainActivity".equals(host.getClass().getName())) {
                host.finish();
            }
        } catch (Throwable ignored) {
        }
    }
}
