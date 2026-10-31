package com.andrerinas.openheadunit.byd;

import android.app.Activity;
import android.os.Bundle;

/**
 * Invisible, instant activity: Android 9 starts a local-only hotspot only for an app in the
 * foreground, so LocalHotspot asks from here and the activity closes straight away.
 */
public final class HotspotActivity extends Activity {
    @Override
    protected void onCreate(Bundle saved) {
        super.onCreate(saved);
        LocalHotspot.requestNow(this);
        finish();
        overridePendingTransition(0, 0);
    }
}
