import android.content.*; import android.net.wifi.*; import com.andrerinas.openheadunit.byd.HotspotSim;
public class LohsSim { static int pass=0,fail=0;
  static void check(String w, boolean ok){ System.out.println((ok?"  PASS  ":"  FAIL  ")+w); if(ok)pass++; else fail++; }
  static String s(Context c,String k){ return c.getSharedPreferences("settings",0).getString(k,null); }
  static int transport(Context c){ return c.getSharedPreferences("settings",0).getInt("native-ap-transport",1); }
  public static void main(String[] a) throws Exception {
    String part=a.length>0?a[0]:"A";
    if(part.equals("A")){
    Context c=new Context(); WifiManager w=new WifiManager(); c.wifi=w;
    System.out.println("1 - car starts, Android Auto asks for the network (DiAuto Hotspot mode)");
    HotspotSim.ensure(c); Thread.sleep(100);
    check("local network started once", w.starts==1 && HotspotSim.running());
    check("name handed to DiAuto without quotes: "+s(c,"hotspot-ssid"), "AndroidShare_1001".equals(s(c,"hotspot-ssid")));
    check("password handed to DiAuto without quotes", "k3y-1-secret".equals(s(c,"hotspot-password")));
    check("interface left automatic", "".equals(s(c,"hotspot-interface")));
    HotspotSim.ensure(c); HotspotSim.ensure(c); Thread.sleep(100);
    check("DiAuto asking again (refresh every 10 s) doesn't start a second one", w.starts==1);

    System.out.println("2 - the system stops the network (e.g. Wi-Fi toggled)");
    w.last.onStopped(); Thread.sleep(500);
    check("not running right after the stop", !HotspotSim.running());
    Thread.sleep(3000);
    check("started again by itself after 3 s, with the new name "+s(c,"hotspot-ssid"), w.starts==2 && "AndroidShare_1002".equals(s(c,"hotspot-ssid")));

    }
    if(part.equals("B")){
    System.out.println("3 - a car that refuses local networks");
    Context c2=new Context(); WifiManager w2=new WifiManager(); w2.mode="refuse"; c2.wifi=w2;
    HotspotSim.ensure(c2); Thread.sleep(200);
    check("first refusal -> still on hotspot mode, retry scheduled", transport(c2)==1 && w2.starts==1);
    Thread.sleep(3300);
    check("second try happened", w2.starts==2);
    Thread.sleep(3300);
    check("third refusal -> back to WiFi Direct (transport 0)", transport(c2)==0 && w2.starts==3);
    check("remembered, so the next start goes straight to WiFi Direct", c2.getSharedPreferences("byd_car_controls",0).getBoolean("lohs_failed",false));
    HotspotSim.ensure(c2); Thread.sleep(3500);
    check("no more attempts after falling back", w2.starts==3);

    System.out.println("4 - 'Use the car's local network again' after the car is fixed");
    w2.mode="ok"; HotspotSim.reset(c2); HotspotSim.ensure(c2); Thread.sleep(200);
    check("hotspot mode again and network up", transport(c2)==1 && w2.starts==4 && HotspotSim.running());

    }
    if(part.equals("C")){
    System.out.println("5 - person chose WiFi Direct by hand");
    Context c3=new Context(); WifiManager w3=new WifiManager(); c3.wifi=w3;
    c3.getSharedPreferences("settings",0).edit().putInt("native-ap-transport",0).apply();
    HotspotSim.ensure(c3); Thread.sleep(200);
    check("nothing started", w3.starts==0);
    }

    System.out.println("  ("+pass+" passed, "+fail+" failed)"); System.exit(fail==0?0:1);
  }
}
