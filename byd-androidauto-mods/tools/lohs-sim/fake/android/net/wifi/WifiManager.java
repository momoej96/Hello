package android.net.wifi;
/** Fake car radio: "ok" starts a 2.4 GHz local network, "refuse" fails with reason 3. */
public class WifiManager { public String mode="ok"; public int starts; public LocalOnlyHotspotCallback last;
 public void startLocalOnlyHotspot(LocalOnlyHotspotCallback cb, android.os.Handler h){ starts++; last=cb;
   if(mode.equals("ok")){ WifiConfiguration c=new WifiConfiguration(); c.SSID="\"AndroidShare_"+(1000+starts)+"\""; c.preSharedKey="\"k3y-"+starts+"-secret\"";
     LocalOnlyHotspotReservation r=new LocalOnlyHotspotReservation(); r.cfg=c; cb.onStarted(r); } else cb.onFailed(3); }
 public static class LocalOnlyHotspotCallback { public void onStarted(LocalOnlyHotspotReservation r){} public void onStopped(){} public void onFailed(int reason){} }
 public static class LocalOnlyHotspotReservation { WifiConfiguration cfg; public WifiConfiguration getWifiConfiguration(){return cfg;} public void close(){} } }
