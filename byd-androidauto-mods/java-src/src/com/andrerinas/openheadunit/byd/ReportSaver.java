package com.andrerinas.openheadunit.byd;

import android.content.Context;
import android.net.Uri;
import android.os.Build;
import android.os.Environment;
import android.util.Log;

import java.io.BufferedReader;
import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.io.PrintWriter;
import java.io.StringWriter;

/**
 * Saves DiAuto's diagnostic report on BYD units. DiAuto only writes it through MediaStore
 * Downloads on Android 10+, which BYD's firmware refuses, and the unit has no file picker either.
 * This keeps that path first and falls back to places that work without a picker, and adds a
 * BYD section (car controls state, own logcat) to the report.
 */
public final class ReportSaver {
    private static final String TAG = "DiAuto-Report";
    private static final String AUTHORITY_SUFFIX = ".fileprovider";

    private static volatile String where = "Downloads/DiAuto/";

    private ReportSaver() {}

    /** Prefix shown before the file name in DiAuto's "Report saved" dialog. */
    public static String wherePrefix() {
        return where;
    }

    /** Replaces DiAuto's own save step. Returns a Uri the share sheet can use. */
    public static Uri save(Context c, Uri destination, String name) throws Exception {
        lastFailure = "";
        try {
            return saveNow(c, destination, name, false);
        } catch (Throwable t) {
            if (lastFailure.length() == 0) lastFailure = String.valueOf(t);
            Log.w(TAG, "report not saved: " + lastFailure, t);
            throw new java.io.IOException(lastFailure);
        }
    }

    /** DiAuto's "could not save" text, followed by what actually failed. */
    public static String withFailure(String text) {
        String f = lastFailure;
        return f == null || f.length() == 0 ? text : text + "\n\n" + f;
    }

    /** "Choose save location" with no file picker on the unit: save without one instead. */
    public static void noPicker(final Context context) {
        final Context c = context.getApplicationContext();
        CarActions.toast(c, "No file picker on this unit, saving the report without one…");
        new Thread(new Runnable() {
            public void run() {
                String name = "DiAuto-report-" + new java.text.SimpleDateFormat("yyyyMMdd-HHmmss",
                        java.util.Locale.US).format(new java.util.Date()) + ".txt";
                try {
                    saveNow(c, null, name, true);
                    longToast(c, "Report saved: " + where + name);
                } catch (Throwable t) {
                    longToast(c, "Report not saved: " + (lastFailure.length() > 0 ? lastFailure : String.valueOf(t)));
                }
            }
        }, "DiAuto-Report").start();
    }

    private static volatile String lastFailure = "";

    private static void longToast(final Context c, final String text) {
        new android.os.Handler(android.os.Looper.getMainLooper()).post(new Runnable() {
            public void run() {
                try {
                    android.widget.Toast.makeText(c, text, android.widget.Toast.LENGTH_LONG).show();
                } catch (Throwable ignored) {
                }
            }
        });
    }

    private static Uri saveNow(Context c, Uri destination, String name, boolean appFolderFirst) throws Exception {
        String report = build(c);
        StringBuilder failures = new StringBuilder();

        if (destination != null) {
            g1.w.a.b(c.getContentResolver(), destination, report);
            where = "";
            return destination;
        }

        // 1) DiAuto's own way: MediaStore Downloads/DiAuto.
        if (!appFolderFirst && Build.VERSION.SDK_INT >= 29) {
            try {
                Uri uri = g1.w.a.a(c.getContentResolver(), name, report);
                where = "Downloads/DiAuto/";
                return uri;
            } catch (Throwable t) {
                failures.append("Downloads (MediaStore): ").append(t).append('\n');
                Log.w(TAG, "MediaStore save failed", t);
            }
        }

        // 2) Straight into /sdcard/Download/DiAuto (needs storage permission).
        File pub = new File(Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOWNLOADS), "DiAuto");
        if (!appFolderFirst) {
            try {
                File f = write(pub, name, report);
                where = pub.getAbsolutePath() + "/";
                return Uri.fromFile(f);
            } catch (Throwable t) {
                failures.append("Download folder: ").append(t).append('\n');
            }
        }

        // 3) DiAuto's own external folder: readable by file managers and adb pull.
        //    4) Its private folder as a last resort (adb / run-as only).
        File ext = null;
        try {
            ext = c.getExternalFilesDir(null);
        } catch (Throwable t) {
            failures.append("App folder: ").append(t).append('\n');
        }
        File[] dirs = {ext != null ? new File(ext, "reports") : null, new File(c.getFilesDir(), "reports")};
        for (File dir : dirs) {
            if (dir == null) continue;
            try {
                File f = write(dir, name, report + "\n\n===== Save attempts =====\n" + failures);
                where = dir.getAbsolutePath() + "/";
                copyOverAdb(c, f, pub, name);
                return shareUri(c, f);
            } catch (Throwable t) {
                failures.append(dir.getAbsolutePath()).append(": ").append(t).append('\n');
            }
        }
        lastFailure = failures.toString().trim();
        throw new java.io.IOException(lastFailure);
    }

    private static File write(File dir, String name, String text) throws Exception {
        if (!dir.isDirectory() && !dir.mkdirs()) throw new java.io.IOException("can't create " + dir);
        File f = new File(dir, name);
        OutputStream o = new FileOutputStream(f);
        try {
            o.write(text.getBytes("UTF-8"));
        } finally {
            o.close();
        }
        return f;
    }

    /** With ADB already allowed, the shell user can also put a copy in Download/DiAuto. */
    private static void copyOverAdb(Context c, File f, File pub, String name) {
        try {
            if (!LocalAdb.wasAllowed(c)) return;
            String target = "/sdcard/Download/DiAuto/" + name;
            String out = LocalAdb.shell(c, "mkdir -p /sdcard/Download/DiAuto && cp '" + f.getAbsolutePath()
                    + "' '" + target + "' && echo COPIED");
            if (out != null && out.contains("COPIED")) where = "/sdcard/Download/DiAuto/";
        } catch (Throwable ignored) {
        }
    }

    private static Uri shareUri(Context c, File f) {
        try {
            Class<?> fp = Class.forName("androidx.core.content.FileProvider");
            return (Uri) fp.getMethod("getUriForFile", Context.class, String.class, File.class)
                    .invoke(null, c, c.getPackageName() + AUTHORITY_SUFFIX, f);
        } catch (Throwable t) {
            return Uri.fromFile(f);
        }
    }

    // ---- report ----

    private static String build(Context c) {
        StringBuilder b = new StringBuilder();
        try {
            b.append(g1.z.a.a(c));
        } catch (Throwable t) {
            b.append("DiAuto's report builder failed:\n").append(stack(t));
        }
        b.append("\n\n===== BYD car controls =====\n");
        try {
            b.append("Firmware: ").append(Build.FINGERPRINT).append('\n');
            b.append("Android: ").append(Build.VERSION.RELEASE).append(" (API ").append(Build.VERSION.SDK_INT).append(")\n");
            b.append("Wheel key service: ").append(WheelKeyService.connected() ? "on" : "off").append('\n');
            b.append("ADB: ").append(LocalAdb.wasAllowed(c) ? "allowed before" : "never connected")
                    .append(", port ").append(CarActions.prefs(c).getInt("adb_port", LocalAdb.PORTS[0]))
                    .append(", last error: ").append(LocalAdb.lastError()).append('\n');
            b.append("Car control: ").append(CarActions.acStatus(c)).append('\n');
            b.append("Settings:\n");
            for (java.util.Map.Entry<String, ?> e : CarActions.prefs(c).getAll().entrySet()) {
                b.append("  ").append(e.getKey()).append(" = ").append(e.getValue()).append('\n');
            }
        } catch (Throwable t) {
            b.append(stack(t));
        }
        b.append("\n===== logcat (this app) =====\n").append(logcat());
        return b.toString();
    }

    private static String logcat() {
        try {
            Process p = Runtime.getRuntime().exec(new String[] {"logcat", "-d", "-v", "time", "-t", "1500"});
            BufferedReader r = new BufferedReader(new InputStreamReader(p.getInputStream(), "UTF-8"));
            StringBuilder b = new StringBuilder();
            String line;
            while ((line = r.readLine()) != null) b.append(line).append('\n');
            r.close();
            p.destroy();
            return b.toString();
        } catch (Throwable t) {
            return "logcat failed: " + t + "\n";
        }
    }

    private static String stack(Throwable t) {
        StringWriter w = new StringWriter();
        t.printStackTrace(new PrintWriter(w));
        return w.toString();
    }
}
