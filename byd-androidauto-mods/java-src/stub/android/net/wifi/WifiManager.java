package android.net.wifi;
// Compile-time stand-in: the build's android.jar (API 16) predates the local-only hotspot (API 26).
// Only the members the helpers use; the real framework class is used at runtime.
public class WifiManager {
  public static final String NETWORK_STATE_CHANGED_ACTION = "android.net.wifi.STATE_CHANGE";
  public WifiInfo getConnectionInfo() { return null; }
  public boolean isWifiEnabled() { return false; }
  public void startLocalOnlyHotspot(LocalOnlyHotspotCallback callback, android.os.Handler handler) {}
  public static class LocalOnlyHotspotCallback {
    public static final int ERROR_NO_CHANNEL = 1, ERROR_GENERIC = 2, ERROR_INCOMPATIBLE_MODE = 3, ERROR_TETHERING_DISALLOWED = 4;
    public void onStarted(LocalOnlyHotspotReservation reservation) {}
    public void onStopped() {}
    public void onFailed(int reason) {}
  }
  public static class LocalOnlyHotspotReservation implements java.io.Closeable {
    public WifiConfiguration getWifiConfiguration() { return null; }
    public void close() {}
  }
}
