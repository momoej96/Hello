package com.andrerinas.openheadunit.byd;

import android.accessibilityservice.AccessibilityService;
import android.content.Context;
import android.content.Intent;
import android.view.KeyEvent;
import android.view.accessibility.AccessibilityEvent;

/**
 * Sees the steering-wheel and console keys before any app does (flagRequestFilterKeyEvents),
 * so a key can run a car action wherever the driver is. The system re-binds it after the car
 * wakes, which also lets DiAuto start again with the car (CarWake).
 */
public final class WheelKeyService extends AccessibilityService {
    private static volatile WheelKeyService current;

    public static boolean connected() {
        return current != null;
    }

    static String component(Context c) {
        return c.getPackageName() + "/" + WheelKeyService.class.getName();
    }

    @Override
    protected void onServiceConnected() {
        current = this;
        CarWake.attach(this);
    }

    @Override
    protected boolean onKeyEvent(KeyEvent event) {
        return CarKeys.onKey(this, event);
    }

    @Override
    public void onAccessibilityEvent(AccessibilityEvent event) {
    }

    @Override
    public void onInterrupt() {
    }

    @Override
    public boolean onUnbind(Intent intent) {
        current = null;
        return super.onUnbind(intent);
    }

    @Override
    public void onDestroy() {
        current = null;
        super.onDestroy();
    }

    /** Turns the service on from the ADB shell. Returns "" when done, else what went wrong. */
    static String enableOverAdb(Context c) {
        String me = component(c);
        String list = CarActions.adb(c, "settings get secure enabled_accessibility_services");
        if (list == null) return LocalAdb.lastError();
        list = list.trim();
        if (list.length() == 0 || "null".equals(list)) {
            list = me;
        } else if (!(":" + list + ":").contains(":" + me + ":")) {
            list = list + ":" + me;
        }
        String out = CarActions.adb(c, "settings put secure enabled_accessibility_services '" + list
                + "' && settings put secure accessibility_enabled 1 && echo DONE");
        if (out == null) return LocalAdb.lastError();
        return out.contains("DONE") ? "" : out.trim();
    }
}
