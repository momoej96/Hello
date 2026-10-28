package com.andrerinas.openheadunit.byd;

import android.content.Context;
import android.content.ContextWrapper;

/**
 * Context handed to BYD's AC client class. That class checks the AC permissions on the
 * Context it is given before it talks to the car service; direct
 * "service call autoservice" reads show the service itself serves an app caller.
 */
final class PermissiveContext extends ContextWrapper {
    PermissiveContext(Context base) {
        super(base);
    }

    @Override
    public Context getApplicationContext() {
        return this;
    }

    @Override
    public int checkPermission(String permission, int pid, int uid) {
        return 0;
    }

    @Override
    public int checkCallingPermission(String permission) {
        return 0;
    }

    @Override
    public int checkCallingOrSelfPermission(String permission) {
        return 0;
    }

    public int checkSelfPermission(String permission) {
        return 0;
    }

    @Override
    public void enforcePermission(String permission, int pid, int uid, String message) {
    }

    @Override
    public void enforceCallingPermission(String permission, String message) {
    }

    @Override
    public void enforceCallingOrSelfPermission(String permission, String message) {
    }
}
