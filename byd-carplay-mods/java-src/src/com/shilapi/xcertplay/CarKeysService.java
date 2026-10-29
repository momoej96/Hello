package com.shilapi.xcertplay;

import android.accessibilityservice.AccessibilityService;
import android.content.Context;
import android.util.Log;
import android.view.KeyEvent;
import android.view.accessibility.AccessibilityEvent;

/**
 * DiPlay's own accessibility service for the car keys. It is separate from the original
 * "DiPlay wheel keys" service (Siri / media keys), so turning that one off, or having it stuck,
 * does not touch the car keys, and the other way round.
 */
public final class CarKeysService extends AccessibilityService {
    private static final String TAG = "DiPlay-CarKeysSvc";
    private static volatile CarKeysService instance;

    public static boolean connected() {
        return instance != null;
    }

    @Override
    protected void onServiceConnected() {
        super.onServiceConnected();
        instance = this;
        CarGuard.log(getApplicationContext(), "Car keys service connected");
        CarWake.attach(this);
    }

    // API 18+; the compile-time android.jar is older, so no @Override here.
    protected boolean onKeyEvent(KeyEvent event) {
        try {
            return CarKeys.onKey(this, event);
        } catch (Throwable t) {
            return false;
        }
    }

    @Override
    public void onAccessibilityEvent(AccessibilityEvent event) {
    }

    @Override
    public void onInterrupt() {
    }

    @Override
    public boolean onUnbind(android.content.Intent intent) {
        if (instance == this) instance = null;
        Log.i(TAG, "unbound");
        try {
            CarGuard.log(getApplicationContext(), "Car keys service unbound");
        } catch (Throwable ignored) {
        }
        return super.onUnbind(intent);
    }

    @Override
    public void onDestroy() {
        if (instance == this) instance = null;
        super.onDestroy();
    }
}
