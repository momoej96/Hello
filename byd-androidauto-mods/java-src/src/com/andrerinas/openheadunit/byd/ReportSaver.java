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
        String report = build(c);
        StringBuilder failures = new StringBuilder();

        if (destination != null) {
            g1.w.a.b(c.getContentResolver(), destination, report);
            where = "";
            return destination;
        }

        // 1) DiAuto's own way: MediaStore Downloads/DiAuto.
        if (Build.VERSION.SDK_INT >= 29) {
            try {
                Uri uri = g1.w.a.a(c.getContentResolver(), name, report);
                where = "Downloads/DiAuto/";
                return uri;
            } catch (Throwable t) {
                failures.append("MediaStore: ").append(t).append('\n');
                Log.w(TAG, "MediaStore save failed", t);
            }
        }

        // 2) Straight into /sdcard/Download/DiAuto (needs storage permission).
        File pub = new File(Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOWNLOADS), "DiAuto");
        try {
            File f = write(pub, name, report);
            where = pub.getAbsolutePath() + "/";
            return Uri.fromFile(f);
        } catch (Throwable t) {
            failures.append("Download folder: ").append(t).append('\n');
        }

        // 3) DiAuto's own external folder: always writable, readable by file managers and adb pull.
        File ext = c.getExternalFilesDir(null);
        File dir = ext != null ? new File(ext, "reports") : new File(c.getFilesDir(), "reports");
        File f = write(dir, name, report + "\n\n===== Save attempts =====\n" + failures);
        where = dir.getAbsolutePath() + "/";
        copyOverAdb(c, f, pub, name);
        return shareUri(c, f);
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
