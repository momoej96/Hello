import android.content.*; import android.net.wifi.*;
import com.andrerinas.openheadunit.byd.*;
public class P2pSim {
  static Context ctx=new Context(); static int pass=0, fail=0;
  static void check(String what, boolean ok){ System.out.println((ok?"  PASS  ":"  FAIL  ")+what); if(ok)pass++; else fail++; }
  static void sta(int netId,int mhz){ WifiInfo.netId=netId; WifiInfo.freq=mhz; Context.receiver.onReceive(ctx,new Intent()); }
  static int create(Fakes.FakeWifiDirectManager m){ return CarP2p.channel(0, m); }   // DiAuto would pass 0 (no 5 GHz request)
  public static void main(String[] a) throws Exception {
    Context.wifi=new WifiManager();
    java.lang.reflect.Method setApp=null;
    // CarP2p.app() uses ActivityThread.currentApplication; give it our context.
    ActivityThreadShim.install(ctx);

    System.out.println("Scenario 1 - the 09:46 log: group made before the car's Wi-Fi connects");
    Fakes.FakeWifiDirectManager m=new Fakes.FakeWifiDirectManager();
    WifiInfo.netId=-1; int ch=create(m);
    check("car Wi-Fi off -> group on channel 6", ch==6);
    sta(5,2437); Thread.sleep(3500);
    check("car Wi-Fi joins on channel 6 -> no recreate needed", m.recreated.isEmpty());
    sta(5,2412); Thread.sleep(1000);
    check("car Wi-Fi moves to channel 1 -> waits for Wi-Fi to settle (no recreate after 1 s)", m.recreated.isEmpty());
    Thread.sleep(2600);
    check("... recreated after ~3 s", m.recreated.size()==1);
    ch=create(m);
    check("recreated group follows car Wi-Fi -> channel 1", ch==1);

    System.out.println("Scenario 2 - phone reports join failure (-11)");
    int before=m.recreated.size();
    CarP2p.handshakeFailed("phone reported join failure (type 6, status=-11)");
    Thread.sleep(300);
    check("join failure -> group recreated within 0.3 s (before the phone's next try 2 s later)", m.recreated.size()==before+1);
    CarP2p.handshakeFailed("the peer never responded");
    Thread.sleep(300);
    check("other handshake errors -> nothing", m.recreated.size()==before+1);

    System.out.println("Scenario 3 - DiAuto's 4-attempt limit");
    for(int i=0;i<6;i++){ CarP2p.handshakeFailed("phone reported join failure"); Thread.sleep(150); }
    java.lang.reflect.Field g=m.getClass().getDeclaredField("G"); g.setAccessible(true);
    check("never reaches DiAuto's give-up count of 4 (G now "+g.getInt(m)+")", g.getInt(m)<4);

    System.out.println("Scenario 4 - Android Auto connected");
    AapGuard.sessionStarted(); before=m.recreated.size();
    CarP2p.handshakeFailed("phone reported join failure"); sta(5,2462); Thread.sleep(3500);
    check("no recreate while connected (car Wi-Fi changed + failure message)", m.recreated.size()==before);
    AapGuard.sessionEnded();

    System.out.println("Scenario 5 - fixed channel and DiAuto's own choice");
    Thread.sleep(3500);  // let any pending event from scenario 4 settle
    CarActionsShim.pref(11); before=m.recreated.size(); ch=create(m);
    check("fixed 11 -> channel 11", ch==11);
    sta(5,2412); Thread.sleep(3500);
    check("fixed channel -> no recreate when car Wi-Fi moves", m.recreated.size()==before);
    CarActionsShim.pref(-1); ch=CarP2p.channel(36, m);
    check("DiAuto's own choice -> passes DiAuto's value through", ch==36);
    CarP2p.handshakeFailed("phone reported join failure"); Thread.sleep(300);
    check("DiAuto's own choice -> join failure leaves DiAuto alone", m.recreated.size()==before);

    System.out.println("\n"+pass+" passed, "+fail+" failed"); System.exit(fail==0?0:1);
  }
}
