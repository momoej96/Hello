package com.andrerinas.openheadunit.byd;

import android.content.Context;
import android.content.SharedPreferences;
import android.media.AudioFormat;
import android.media.AudioTrack;
import android.media.MediaCodec;
import android.os.Handler;
import android.os.HandlerThread;
import android.os.SystemClock;
import android.util.Log;

import java.util.Map;
import java.util.WeakHashMap;

/**
 * Audio and video buffers, like DiPlay's. The car's Wi-Fi link delivers Android Auto in bursts
 * with gaps of up to about 2 s, so playing everything the moment it arrives stutters.
 *
 * Audio (media stream only, i.e. stereo): playback waits until the buffer holds the chosen time,
 * and whenever the buffer runs dry it pauses and fills up again instead of stuttering on every
 * packet. Navigation and system sounds (mono) stay immediate.
 *
 * Video: every decoded frame is shown a fixed delay after it is ready, and frames that arrive in
 * a burst are spread out at the stream's frame interval instead of flashing past at once. If
 * the backlog grows past a limit, the schedule jumps forward so the picture never lags further.
 */
public final class AvBuffer {
    private static final String TAG = "DiAuto-AvBuffer";

    public static final String KEY_AUDIO = "buffer_audio_ms";
    public static final String KEY_VIDEO = "buffer_video_ms";
    public static final int[] AUDIO_MS = {0, 500, 1000, 1500, 2000, 3000};
    public static final int[] VIDEO_MS = {0, 80, 150, 250, 400};
    /** Defaults chosen for the Qin Plus DM-i log: audio gaps up to ~2 s, bursty video. */
    static final int DEFAULT_AUDIO_MS = 2000;
    static final int DEFAULT_VIDEO_MS = 150;

    private static volatile int audioMs = -1;
    private static volatile int videoMs = -1;

    private AvBuffer() {}

    static void load(Context c) {
        SharedPreferences p = CarActions.prefs(c);
        audioMs = p.getInt(KEY_AUDIO, DEFAULT_AUDIO_MS);
        videoMs = p.getInt(KEY_VIDEO, DEFAULT_VIDEO_MS);
    }

    static void set(Context c, String key, int ms) {
        CarActions.prefs(c).edit().putInt(key, ms).apply();
        load(c);
    }

    private static int audioMs() {
        int v = audioMs;
        if (v < 0) {
            try {
                Context app = appContext();
                if (app != null) load(app);
            } catch (Throwable ignored) {
            }
            v = audioMs;
        }
        return v < 0 ? DEFAULT_AUDIO_MS : v;
    }

    private static int videoMs() {
        int v = videoMs;
        if (v < 0) {
            try {
                Context app = appContext();
                if (app != null) load(app);
            } catch (Throwable ignored) {
            }
            v = videoMs;
        }
        return v < 0 ? DEFAULT_VIDEO_MS : v;
    }

    private static Context appContext() throws Exception {
        Class<?> at = Class.forName("android.app.ActivityThread");
        return (Context) at.getMethod("currentApplication").invoke(null);
    }

    // ---- audio ----

    private static final class Track {
        long written;
        boolean filling;
        long lastWrite;
        int lastHead;
        long headBase;
    }

    private static final Map<AudioTrack, Track> TRACKS = new WeakHashMap<AudioTrack, Track>();
    private static Handler timer;

    private static synchronized Handler timer() {
        if (timer == null) {
            HandlerThread t = new HandlerThread("DiAuto-AudioBuffer");
            t.start();
            timer = new Handler(t.getLooper());
        }
        return timer;
    }

    /** AudioTrack buffer size: DiAuto's own size, raised so the chosen buffer time fits with room to spare. */
    public static int audioBufferSize(int size, int sampleRate, int channels) {
        try {
            if (channels != 2 || size <= 0) return size;
            int ms = audioMs();
            if (ms <= 0) return size;
            int bytesPerSec = sampleRate * channels * 2;
            long want = (long) bytesPerSec * (ms + 1500) / 1000;
            return (int) Math.max(size, Math.min(want, 4L * 1024 * 1024));
        } catch (Throwable t) {
            return size;
        }
    }

    /** Replaces AudioTrack.write in DiAuto's playback thread. */
    public static int audioWrite(final AudioTrack t, byte[] data, int len) {
        int ms;
        try {
            ms = t.getChannelCount() == 2 ? audioMs() : 0;
        } catch (Throwable e) {
            ms = 0;
        }
        if (ms <= 0) return t.write(data, 0, len);
        try {
            return bufferedWrite(t, data, len, ms);
        } catch (Throwable e) {
            Log.w(TAG, "audio buffer failed, writing directly", e);
            return t.write(data, 0, len);
        }
    }

    private static int bufferedWrite(final AudioTrack t, byte[] data, int len, int ms) {
        final Track s;
        synchronized (TRACKS) {
            Track found = TRACKS.get(t);
            if (found == null) {
                found = new Track();
                TRACKS.put(t, found);
            }
            s = found;
        }
        int frameBytes = t.getChannelCount() * (t.getAudioFormat() == AudioFormat.ENCODING_PCM_8BIT ? 1 : 2);
        int rate = t.getSampleRate();
        long target = (long) rate * ms / 1000;
        long capacity = bufferFrames(t, frameBytes);
        long chunk = len / frameBytes;

        synchronized (s) {
            long buffered = s.written - head(t, s);
            if (!s.filling && t.getPlayState() == AudioTrack.PLAYSTATE_PLAYING && buffered <= rate / 50) {
                // Ran dry (or first data): stop and fill up again instead of stuttering.
                t.pause();
                s.filling = true;
                Log.i(TAG, "audio buffer empty, filling " + ms + " ms");
            }
            // Never block a paused track on a full buffer.
            if (s.filling && buffered + chunk > capacity - rate / 20) {
                startPlaying(t, s, "buffer full");
            }
        }

        int n = t.write(data, 0, len);

        synchronized (s) {
            if (n > 0) s.written += n / frameBytes;
            s.lastWrite = SystemClock.uptimeMillis();
            if (s.filling && s.written - head(t, s) >= target) startPlaying(t, s, "buffer filled");
            if (s.filling) {
                // The stream may simply have ended (a short clip): play what is there.
                final long stamp = s.lastWrite;
                timer().postDelayed(new Runnable() {
                    public void run() {
                        synchronized (s) {
                            if (s.filling && s.lastWrite == stamp) startPlaying(t, s, "stream idle");
                        }
                    }
                }, 300);
            }
        }
        return n;
    }

    /** AudioTrack.getBufferSizeInFrames (API 23), read by reflection for the old build android.jar. */
    private static long bufferFrames(AudioTrack t, int frameBytes) {
        try {
            return ((Number) AudioTrack.class.getMethod("getBufferSizeInFrames").invoke(t)).longValue();
        } catch (Throwable e) {
            return 65536 / frameBytes;
        }
    }

    private static void startPlaying(AudioTrack t, Track s, String why) {
        try {
            t.play();
        } catch (Throwable ignored) {
        }
        s.filling = false;
        Log.i(TAG, "audio playing (" + why + ")");
    }

    /** Playback head as a growing 64-bit count (the int position wraps). */
    private static long head(AudioTrack t, Track s) {
        int h = t.getPlaybackHeadPosition();
        if ((h & 0xffffffffL) < (s.lastHead & 0xffffffffL)) s.headBase += 1L << 32;
        s.lastHead = h;
        return s.headBase + (h & 0xffffffffL);
    }

    // ---- video ----

    private static java.lang.reflect.Method releaseAt;

    /** MediaCodec.releaseOutputBuffer(int, long) (API 21; not in the build's android.jar). */
    private static void releaseAt(MediaCodec codec, int index, long ns) throws Exception {
        if (releaseAt == null) releaseAt = MediaCodec.class.getMethod("releaseOutputBuffer", int.class, long.class);
        try {
            releaseAt.invoke(codec, Integer.valueOf(index), Long.valueOf(ns));
        } catch (java.lang.reflect.InvocationTargetException e) {
            Throwable c = e.getCause();
            if (c instanceof IllegalStateException) throw (IllegalStateException) c;
            throw e;
        }
    }

    private static MediaCodec videoCodec;
    private static long nextNs;
    private static long lastReadyNs;
    private static long intervalNs = 1000000000L / 30;

    /**
     * Replaces the frame release in DiAuto's video decoder.
     * Returns -1 when the buffer is off (DiAuto's own path runs), 1 when the frame was scheduled.
     */
    public static synchronized int videoRelease(MediaCodec codec, int index) {
        int ms = videoMs();
        if (ms <= 0) return -1;
        try {
            long now = System.nanoTime();
            long delay = ms * 1000000L;
            if (codec != videoCodec) {
                videoCodec = codec;
                nextNs = 0;
                lastReadyNs = 0;
                intervalNs = 1000000000L / 30;
            }
            // Learn the average frame interval (bursts included; long stalls left out).
            if (lastReadyNs > 0) {
                long gap = now - lastReadyNs;
                if (gap < 200000000L) intervalNs = (intervalNs * 15 + gap) / 16;
            }
            lastReadyNs = now;
            // Slightly under the frame interval, so a backlog left by a burst drains back to the delay.
            long spacing = Math.max(10000000L, Math.min(intervalNs, 50000000L)) * 85 / 100;
            long at = Math.max(now + delay, nextNs + spacing);
            if (at - now > delay + 300000000L) {
                // Too far behind after a long gap: skip this frame rather than lag further.
                codec.releaseOutputBuffer(index, false);
                return 1;
            }
            nextNs = at;
            releaseAt(codec, index, at);
            return 1;
        } catch (IllegalStateException e) {
            return -1;
        } catch (Throwable t) {
            Log.w(TAG, "video buffer failed", t);
            return -1;
        }
    }
}
