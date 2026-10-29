package com.andrerinas.openheadunit.byd;

import android.app.Activity;
import android.app.Application;
import android.content.Context;
import android.graphics.Typeface;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.widget.FrameLayout;
import android.widget.TextView;

import java.text.SimpleDateFormat;
import java.util.ArrayDeque;
import java.util.Date;
import java.util.Locale;

/**
 * A few lines at the bottom of DiAuto's home screen showing what the Wi-Fi connection and the
 * start with the car are doing, so a photo of the screen tells what happened without a report.
 * Fed by DiAuto's own logger (hook at the top of g1.a.s, every line at its log level) and by
 * the mod's classes, filtered to the connection steps.
 */
public final class StatusLine {
    private static final int LINES = 8;
    private static final int MAX_CHARS = 150;
    private static final String HOME = "com.andrerinas.openheadunit.main.MainActivity";
    private static final String[] TOPICS = {
        "nativeaa", "handshake", "wificonnect", "wifi direct", "wifidirect", "p2p", "group",
        "hotspot", "bluetooth", "rfcomm", "credential", "ssid", "joined", "session", "auto-start",
        "start with the car", "starting with the car", "refused", "access point", "carp2p",
    };

    private static final Handler MAIN = new Handler(Looper.getMainLooper());
    private static final ArrayDeque<String> lines = new ArrayDeque<String>();
    private static final SimpleDateFormat TIME = new SimpleDateFormat("HH:mm:ss", Locale.US);
    private static TextView view;
    private static boolean attached;
    private static boolean enableTried;
    private static boolean refreshQueued;

    private StatusLine() {}

    /** From g1.a.s(level, message): every line DiAuto logs. Never throws. */
    public static void log(int level, String message) {
        try {
            if (message == null || level < 4) return;
            String low = message.toLowerCase(Locale.US);
            for (String t : TOPICS) {
                if (low.contains(t)) {
                    add(message);
                    return;
                }
            }
        } catch (Throwable ignored) {
        }
    }

    /** A line from the mod itself, always shown. */
    static void note(String message) {
        try {
            add(message);
        } catch (Throwable ignored) {
        }
    }

    private static void add(String message) {
        String m = message.replace('\n', ' ').trim();
        if (m.length() > MAX_CHARS) m = m.substring(0, MAX_CHARS) + "…";
        String line;
        synchronized (TIME) {
            line = TIME.format(new Date()) + "  " + m;
        }
        synchronized (lines) {
            lines.addLast(line);
            while (lines.size() > LINES) lines.removeFirst();
        }
        queueRefresh();
    }

    private static void queueRefresh() {
        synchronized (lines) {
            if (refreshQueued) return;
            refreshQueued = true;
        }
        MAIN.postDelayed(new Runnable() {
            public void run() {
                synchronized (lines) {
                    refreshQueued = false;
                }
                refresh();
            }
        }, 300);
    }

    private static void refresh() {
        TextView v = view;
        if (v == null) return;
        StringBuilder b = new StringBuilder();
        b.append(WheelKeyService.connected() ? "Start with the car: on" : "Start with the car: OFF");
        synchronized (lines) {
            for (String l : lines) b.append('\n').append(l);
        }
        v.setText(b);
    }

    /** From CarDefaults.apply (App.onCreate): shows the lines while DiAuto's home screen is open. */
    static void attach(Context c) {
        if (attached || !(c.getApplicationContext() instanceof Application)) return;
        attached = true;
        ((Application) c.getApplicationContext()).registerActivityLifecycleCallbacks(
                new Application.ActivityLifecycleCallbacks() {
                    public void onActivityResumed(Activity a) {
                        if (HOME.equals(a.getClass().getName())) show(a);
                    }

                    public void onActivityPaused(Activity a) {
                        if (HOME.equals(a.getClass().getName())) hide();
                    }

                    public void onActivityCreated(Activity a, Bundle b) {
                    }

                    public void onActivityStarted(Activity a) {
                    }

                    public void onActivityStopped(Activity a) {
                    }

                    public void onActivitySaveInstanceState(Activity a, Bundle b) {
                    }

                    public void onActivityDestroyed(Activity a) {
                    }
                });
    }

    private static void show(Activity a) {
        try {
            hide();
            View root = a.findViewById(android.R.id.content);
            if (!(root instanceof FrameLayout)) return;
            float dp = a.getResources().getDisplayMetrics().density;
            TextView t = new TextView(a);
            t.setTextColor(0xFFE8EEF6);
            t.setBackgroundColor(0xB0000000);
            t.setTypeface(Typeface.MONOSPACE);
            t.setTextSize(11);
            t.setPadding((int) (8 * dp), (int) (4 * dp), (int) (8 * dp), (int) (4 * dp));
            t.setClickable(false);
            t.setFocusable(false);
            FrameLayout.LayoutParams lp = new FrameLayout.LayoutParams(
                    ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT,
                    Gravity.BOTTOM);
            ((FrameLayout) root).addView(t, lp);
            view = t;
            refresh();
            enableServiceOnce(a.getApplicationContext());
        } catch (Throwable ignored) {
        }
    }

    private static void hide() {
        TextView t = view;
        view = null;
        if (t == null) return;
        try {
            ((ViewGroup) t.getParent()).removeView(t);
        } catch (Throwable ignored) {
        }
    }

    /**
     * The first time the home screen opens with the start-with-the-car service off, switches it
     * on through the car's own ADB (the car asks "Allow USB debugging?" once).
     */
    private static void enableServiceOnce(final Context c) {
        if (enableTried || WheelKeyService.connected()) return;
        enableTried = true;
        note("Start with the car is off: switching it on over ADB (allow the prompt if the car shows one)");
        new Thread(new Runnable() {
            public void run() {
                String err;
                try {
                    err = WheelKeyService.enableOverAdb(c);
                } catch (Throwable t) {
                    err = String.valueOf(t);
                }
                note(err == null || err.length() == 0 ? "Start with the car: switched on over ADB"
                        : "Could not switch it on over ADB (" + err + "). Car settings → Accessibility → DiAuto start with the car");
            }
        }, "DiAuto-StatusLine").start();
    }
}
