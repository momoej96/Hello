package com.andrerinas.openheadunit.byd;

import android.content.Context;
import android.util.Base64;

import java.io.ByteArrayOutputStream;
import java.io.DataInputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.math.BigInteger;
import java.net.InetSocketAddress;
import java.net.Socket;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.security.KeyFactory;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.PrivateKey;
import java.security.interfaces.RSAPublicKey;
import java.security.spec.PKCS8EncodedKeySpec;
import java.security.spec.X509EncodedKeySpec;

import javax.crypto.Cipher;

/**
 * Minimal ADB client talking to the head unit's own adbd over TCP (127.0.0.1), the way DiPlay
 * does it. The first connection shows the "Allow USB debugging?" prompt on the screen; once the
 * key is allowed (tick "Always allow"), commands run as the shell user without asking again.
 */
public final class LocalAdb {
    private static final int A_CNXN = 0x4e584e43;
    private static final int A_AUTH = 0x48545541;
    private static final int A_OPEN = 0x4e45504f;
    private static final int A_OKAY = 0x59414b4f;
    private static final int A_CLSE = 0x45534c43;
    private static final int A_WRTE = 0x45545257;
    private static final int VERSION = 0x01000000;
    private static final int MAX_DATA = 256 * 1024;
    private static final int AUTH_TOKEN = 1;
    private static final int AUTH_SIGNATURE = 2;
    private static final int AUTH_RSAPUBLICKEY = 3;

    static final int[] PORTS = {5555, 5556};
    private static final int CONNECT_MS = 2000;
    private static final int READ_MS = 15000;
    /** Time the person gets to answer the "Allow USB debugging?" prompt. */
    private static final int PROMPT_MS = 60000;

    /** SHA-1 DigestInfo prefix; adbd verifies the 20-byte token as a SHA-1 digest. */
    private static final byte[] SHA1_PREFIX = {
        0x30, 0x21, 0x30, 0x09, 0x06, 0x05, 0x2b, 0x0e, 0x03, 0x02, 0x1a, 0x05, 0x00, 0x04, 0x14,
    };

    private static KeyPair keys;
    private static volatile String lastError = "";

    private LocalAdb() {}

    public static String lastError() {
        return lastError;
    }

    /** Runs a shell command and returns its output, or null when ADB can't be reached. */
    public static synchronized String shell(Context c, String command) {
        Context app = c.getApplicationContext() != null ? c.getApplicationContext() : c;
        int saved = CarActions.prefs(app).getInt("adb_port", PORTS[0]);
        int[] order = new int[PORTS.length + 1];
        order[0] = saved;
        System.arraycopy(PORTS, 0, order, 1, PORTS.length);
        String error = null;
        for (int i = 0; i < order.length; i++) {
            if (i > 0 && order[i] == saved) continue;
            try {
                String out = run(app, order[i], command);
                if (order[i] != saved) CarActions.prefs(app).edit().putInt("adb_port", order[i]).apply();
                lastError = "";
                return out;
            } catch (java.net.ConnectException e) {
                if (error == null) error = "ADB is off (no answer on port " + order[i] + ")";
            } catch (Throwable t) {
                // adbd answered but the command failed: no point trying other ports.
                lastError = t.getMessage() != null ? t.getMessage() : t.getClass().getSimpleName();
                return null;
            }
        }
        lastError = error != null ? error : "ADB not reachable";
        return null;
    }

    private static String run(Context c, int port, String command) throws Exception {
        Socket s = new Socket();
        try {
            s.connect(new InetSocketAddress("127.0.0.1", port), CONNECT_MS);
            s.setSoTimeout(READ_MS);
            s.setTcpNoDelay(true);
            DataInputStream in = new DataInputStream(s.getInputStream());
            OutputStream out = s.getOutputStream();
            send(out, A_CNXN, VERSION, MAX_DATA, "host::\0".getBytes("UTF-8"));
            authenticate(c, s, in, out);
            return exec(in, out, command);
        } finally {
            try {
                s.close();
            } catch (IOException ignored) {
            }
        }
    }

    private static void authenticate(Context c, Socket s, DataInputStream in, OutputStream out) throws Exception {
        boolean signed = false;
        boolean sentKey = false;
        while (true) {
            Msg m = read(in);
            if (m.cmd == A_CNXN) return;
            if (m.cmd != A_AUTH || m.arg0 != AUTH_TOKEN) {
                throw new IOException("unexpected ADB reply " + Integer.toHexString(m.cmd));
            }
            KeyPair kp = keys(c);
            if (!signed) {
                signed = true;
                send(out, A_AUTH, AUTH_SIGNATURE, 0, sign(kp.getPrivate(), m.data));
            } else if (!sentKey) {
                sentKey = true;
                send(out, A_AUTH, AUTH_RSAPUBLICKEY, 0, publicKeyBlob((RSAPublicKey) kp.getPublic()));
                // adbd now shows the prompt on the head unit and answers CNXN once it is allowed.
                s.setSoTimeout(PROMPT_MS);
            } else {
                throw new IOException("ADB key not allowed");
            }
        }
    }

    private static String exec(DataInputStream in, OutputStream out, String command) throws Exception {
        final int local = 1;
        send(out, A_OPEN, local, 0, ("shell:" + command + "\0").getBytes("UTF-8"));
        ByteArrayOutputStream result = new ByteArrayOutputStream();
        int remote = 0;
        while (true) {
            Msg m;
            try {
                m = read(in);
            } catch (java.io.EOFException e) {
                break;
            }
            if (m.cmd == A_OKAY) {
                remote = m.arg0;
            } else if (m.cmd == A_WRTE) {
                remote = m.arg0;
                result.write(m.data);
                send(out, A_OKAY, local, remote, null);
            } else if (m.cmd == A_CLSE) {
                if (remote == 0 && result.size() == 0) throw new IOException("ADB refused the shell");
                send(out, A_CLSE, local, m.arg0, null);
                break;
            }
        }
        return result.toString("UTF-8");
    }

    // ---- wire format ----

    private static final class Msg {
        int cmd;
        int arg0;
        int arg1;
        byte[] data;
    }

    private static void send(OutputStream out, int cmd, int arg0, int arg1, byte[] data) throws IOException {
        int len = data == null ? 0 : data.length;
        int sum = 0;
        for (int i = 0; i < len; i++) sum += data[i] & 0xff;
        ByteBuffer b = ByteBuffer.allocate(24 + len).order(ByteOrder.LITTLE_ENDIAN);
        b.putInt(cmd).putInt(arg0).putInt(arg1).putInt(len).putInt(sum).putInt(~cmd);
        if (len > 0) b.put(data);
        out.write(b.array());
        out.flush();
    }

    private static Msg read(DataInputStream in) throws IOException {
        byte[] h = new byte[24];
        in.readFully(h);
        ByteBuffer b = ByteBuffer.wrap(h).order(ByteOrder.LITTLE_ENDIAN);
        Msg m = new Msg();
        m.cmd = b.getInt();
        m.arg0 = b.getInt();
        m.arg1 = b.getInt();
        int len = b.getInt();
        if (len < 0 || len > 1024 * 1024) throw new IOException("bad ADB packet");
        m.data = new byte[len];
        in.readFully(m.data);
        return m;
    }

    // ---- keys ----

    private static synchronized KeyPair keys(Context c) throws Exception {
        if (keys != null) return keys;
        File dir = new File(c.getFilesDir(), "adb");
        File priv = new File(dir, "adbkey");
        File pub = new File(dir, "adbkey.pub");
        KeyFactory kf = KeyFactory.getInstance("RSA");
        if (priv.exists() && pub.exists()) {
            try {
                keys = new KeyPair(kf.generatePublic(new X509EncodedKeySpec(readAll(pub))),
                        kf.generatePrivate(new PKCS8EncodedKeySpec(readAll(priv))));
                return keys;
            } catch (Throwable ignored) {
            }
        }
        KeyPairGenerator g = KeyPairGenerator.getInstance("RSA");
        g.initialize(2048);
        KeyPair kp = g.generateKeyPair();
        dir.mkdirs();
        writeAll(priv, kp.getPrivate().getEncoded());
        writeAll(pub, kp.getPublic().getEncoded());
        keys = kp;
        return kp;
    }

    private static byte[] sign(PrivateKey key, byte[] token) throws Exception {
        Cipher cipher = Cipher.getInstance("RSA/ECB/PKCS1Padding");
        cipher.init(Cipher.ENCRYPT_MODE, key);
        cipher.update(SHA1_PREFIX);
        return cipher.doFinal(token);
    }

    /** The public key in adbd's format: base64 of Android's RSAPublicKey struct, then a name. */
    private static byte[] publicKeyBlob(RSAPublicKey key) throws Exception {
        final int words = 64; // 2048-bit key
        BigInteger n = key.getModulus();
        BigInteger r32 = BigInteger.ONE.shiftLeft(32);
        BigInteger n0inv = n.mod(r32).modInverse(r32).negate().mod(r32);
        BigInteger rr = BigInteger.ONE.shiftLeft(words * 32 * 2).mod(n);
        ByteBuffer b = ByteBuffer.allocate(4 + 4 + words * 4 + words * 4 + 4).order(ByteOrder.LITTLE_ENDIAN);
        b.putInt(words);
        b.putInt(n0inv.intValue());
        putWords(b, n, words);
        putWords(b, rr, words);
        b.putInt(key.getPublicExponent().intValue());
        String text = Base64.encodeToString(b.array(), Base64.NO_WRAP) + " DiAuto@headunit\0";
        return text.getBytes("UTF-8");
    }

    private static void putWords(ByteBuffer b, BigInteger v, int words) {
        BigInteger mask = BigInteger.ONE.shiftLeft(32).subtract(BigInteger.ONE);
        for (int i = 0; i < words; i++) {
            b.putInt(v.shiftRight(i * 32).and(mask).intValue());
        }
    }

    private static byte[] readAll(File f) throws IOException {
        InputStream in = new FileInputStream(f);
        try {
            ByteArrayOutputStream o = new ByteArrayOutputStream();
            byte[] buf = new byte[4096];
            int r;
            while ((r = in.read(buf)) > 0) o.write(buf, 0, r);
            return o.toByteArray();
        } finally {
            in.close();
        }
    }

    private static void writeAll(File f, byte[] data) throws IOException {
        OutputStream o = new FileOutputStream(f);
        try {
            o.write(data);
        } finally {
            o.close();
        }
    }
}
