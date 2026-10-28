package com.andrerinas.openheadunit.byd;

import android.content.Context;
import android.content.Intent;

import com.andrerinas.openheadunit.main.settings.SettingItem;

import java.util.List;

/** Adds the "BYD car controls" row under "Key mapping" in DiAuto's settings list. */
public final class SettingsHook {
    private SettingsHook() {}

    /** Called from SettingsFragment.updateSettingsList right after the keymap row is added. */
    @SuppressWarnings({"unchecked", "rawtypes"})
    public static void addEntry(List list, Object fragment) {
        try {
            final Context c = (Context) fragment.getClass().getMethod("getContext").invoke(fragment);
            if (c == null) return;
            int name = c.getResources().getIdentifier("byd_car_controls", "string", c.getPackageName());
            if (name == 0) name = android.R.string.untitled;
            String value = WheelKeyService.connected() ? "Wheel keys, AC, climate"
                    : "Wheel keys, AC, climate · wheel key service off";
            list.add(new SettingItem.SettingEntry("bydCarControls", name, value, "BYD car controls",
                    "byd wheel steering keys buttons ac air conditioning climate", new m5.l() {
                        public Object invoke(Object stableId) {
                            Intent i = new Intent(c, CarControlsActivity.class);
                            c.startActivity(i);
                            return null;
                        }
                    }));
        } catch (Throwable ignored) {
        }
    }
}
