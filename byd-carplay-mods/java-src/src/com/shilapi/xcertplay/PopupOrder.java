package com.shilapi.xcertplay;

import kotlin.Pair;

/** Puts the CarPlay settings window's "audio" tab straight after "display". */
public final class PopupOrder {
    private PopupOrder() {}

    public static void audioAfterDisplay(Object[] tabs) {
        try {
            int audio = indexOf(tabs, "audio");
            int display = indexOf(tabs, "display");
            if (audio < 0 || display < 0 || audio == display + 1) return;
            Object moving = tabs[audio];
            if (audio > display) {
                for (int i = audio; i > display + 1; i--) tabs[i] = tabs[i - 1];
                tabs[display + 1] = moving;
            } else {
                for (int i = audio; i < display; i++) tabs[i] = tabs[i + 1];
                tabs[display] = moving;
            }
        } catch (Throwable ignored) {
        }
    }

    private static int indexOf(Object[] tabs, String key) {
        for (int i = 0; i < tabs.length; i++) {
            Object t = tabs[i];
            if (t instanceof Pair && key.equals(((Pair) t).getFirst())) return i;
        }
        return -1;
    }
}
