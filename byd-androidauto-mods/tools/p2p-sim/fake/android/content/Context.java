package android.content;
public class Context { public static final String WIFI_SERVICE="wifi"; public static BroadcastReceiver receiver; public static Object wifi;
 public Context getApplicationContext(){return this;} public Object getSystemService(String n){return wifi;}
 public Intent registerReceiver(BroadcastReceiver r, IntentFilter f){receiver=r;return null;}
 public void startActivity(Intent i){} public android.content.pm.PackageManager getPackageManager(){return null;} }
