package com.shilapi.xcertplay;

import android.app.Notification;
import android.app.NotificationManager;
import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.os.Build;
import android.os.IBinder;
import android.util.Log;

/**
 * A small foreground service in DiPlay's main process, where the wheel-key accessibility service lives.
 * Diplus keeps its key service alive the same way (its MainService is a foreground service in the same process).
 * Without it, DiPlay's process is just a cached process while CarPlay isn't connected and gets killed during sleep.
 */
public final class CarKeepAliveService extends Service {
    private static final String TAG = "DiPlay-KeepAlive";
    private static final String CHANNEL = "diplay_keepalive";
    private static final int ID = 7411;
    static final String KEY_ENABLED = "carkeep_enabled";

    public static boolean enabled(Context c) {
        try {
            return CarActions.prefs(c).getBoolean(KEY_ENABLED, true);
        } catch (Throwable t) {
            return true;
        }
    }

    public static void start(Context c) {
        try {
            if (!enabled(c)) return;
            Intent i = new Intent(c, CarKeepAliveService.class);
            if (Build.VERSION.SDK_INT >= 26) {
                Context.class.getMethod("startForegroundService", Intent.class).invoke(c, i);
            } else {
                c.startService(i);
            }
        } catch (Throwable t) {
            Log.w(TAG, "start failed", t);
        }
    }

    public static void stop(Context c) {
        try {
            c.stopService(new Intent(c, CarKeepAliveService.class));
        } catch (Throwable ignored) {
        }
    }

    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }

    @Override
    public void onCreate() {
        super.onCreate();
        goForeground();
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        goForeground();
        return START_STICKY;
    }

    private void goForeground() {
        try {
            startForeground(ID, notification());
        } catch (Throwable t) {
            Log.w(TAG, "startForeground failed", t);
        }
    }

    private Notification notification() throws Exception {
        Notification.Builder b;
        if (Build.VERSION.SDK_INT >= 26) {
            NotificationManager nm = (NotificationManager) getSystemService(Context.NOTIFICATION_SERVICE);
            Class<?> channelClass = Class.forName("android.app.NotificationChannel");
            Object channel = channelClass.getConstructor(String.class, CharSequence.class, int.class)
                    .newInstance(CHANNEL, "DiPlay keep-alive", Integer.valueOf(1));   // IMPORTANCE_MIN
            NotificationManager.class.getMethod("createNotificationChannel", channelClass).invoke(nm, channel);
            b = Notification.Builder.class.getConstructor(Context.class, String.class).newInstance(this, CHANNEL);
        } else {
            b = new Notification.Builder(this);
        }
        b.setContentTitle("DiPlay is running");
        b.setContentText("Keeps the wheel keys and auto-start working");
        b.setSmallIcon(android.R.drawable.ic_dialog_info);
        b.setOngoing(true);
        return b.build();
    }
}
