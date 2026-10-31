package android.accessibilityservice;
// Compile-time stand-in: the build's android.jar (API 16) predates onKeyEvent (API 18).
public abstract class AccessibilityService extends android.app.Service {
  protected void onServiceConnected() {}
  protected boolean onKeyEvent(android.view.KeyEvent event) { return false; }
  public abstract void onAccessibilityEvent(android.view.accessibility.AccessibilityEvent event);
  public abstract void onInterrupt();
  public final android.os.IBinder onBind(android.content.Intent intent) { return null; }
}
