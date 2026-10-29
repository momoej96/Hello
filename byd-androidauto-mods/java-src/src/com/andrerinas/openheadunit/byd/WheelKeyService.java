package com.andrerinas.openheadunit.byd;

import android.accessibilityservice.AccessibilityService;
import android.content.Context;
import android.content.Intent;
import android.view.accessibility.AccessibilityEvent;

/**
 * Only there to start DiAuto with the car. BYD units sleep instead of switching off, and the
 * system re-binds an enabled accessibility service when the car wakes (starting the process if
 * the car killed it), so this is the one thing that reliably runs after a wake (CarWake).
 * It reads no keys and no screen content. The class name is kept from the earlier builds, so a
 * service the driver already switched on stays on after the update.
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
        StatusLine.note("Start with the car: on");
        CarWake.attach(this);
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
        CarWake.detach(this);
        return super.onUnbind(intent);
    }

    @Override
    public void onDestroy() {
        current = null;
        CarWake.detach(this);
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
