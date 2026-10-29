import java.util.*;
/**
 * Straight port of DiAuto's access-point resolution (y0.d1.u()/v(), v0.t3, v0.s3, v0.g3) so the
 * hand-off from LocalHotspot can be checked against the interfaces the car reported.
 */
public class ResolverPort {
  static class If { String name; boolean loop, up; String ip; If(String n,boolean l,boolean u,String ip){name=n;loop=l;up=u;this.ip=ip;} }
  static final List<String> PREFER = Arrays.asList("ap","swlan","softap","wlan");
  static final List<String> EXCLUDE = Arrays.asList("p2p-","tun","dummy","apcli","sta","seth_lte","ccmni","rmnet");
  static boolean excluded(String n){ String l=n.toLowerCase(); for(String e:EXCLUDE) if(l.startsWith(e)) return true; return l.matches("eth[0-9]+")||l.equals("briotgw"); }
  static boolean candidate(If i,String stationIp){ return i.up && !i.loop && i.ip!=null && !excluded(i.name) && (stationIp==null || !i.ip.equals(stationIp)); }
  static int rank(String n){ String l=n.toLowerCase(); for(int k=0;k<PREFER.size();k++) if(l.startsWith(PREFER.get(k))) return k; return PREFER.size(); }
  /** t3.e with an empty interface name: best-ranked candidate. */
  static If pick(List<If> l,String stationIp,String named){
    if(named!=null && !named.trim().isEmpty()){ for(If i:l) if(i.name.equalsIgnoreCase(named.trim())&&i.up&&!i.loop&&i.ip!=null) return i; return null; }
    If best=null; for(If i:l) if(candidate(i,stationIp) && (best==null || rank(best.name)>rank(i.name))) best=i; return best; }
  /** d1.v(): returns the SSID handed to the phone, or why not. */
  static String resolve(List<If> l,String stationIp,String namedIf,String ssid,String pass,boolean apStateDisabled){
    If i=pick(l,stationIp,namedIf); if(i==null) return "WAIT: no interface looks like an access point";
    String s=ssid==null?"":ssid, p=pass==null?"":pass;            // q3 from the system config is unavailable on this car (SecurityException)
    if(s.isEmpty()) return "FAIL: no network name (r3.g) - today's 10:15 failure";
    if(apStateDisabled) return "FAIL: system says no access point running";
    return "SUCCESS via "+i.name+" ("+i.ip+"): SSID="+s+(p.isEmpty()?" (open!)":" with passphrase");
  }
  public static void main(String[] a){
    int pass=0, fail=0;
    // Interfaces as in the 10:16 report while an access point ran: ap0 up with a private IPv4, wlan0 down, lo.
    List<If> car=Arrays.asList(new If("lo",true,true,"127.0.0.1"), new If("ap0",false,true,"192.168.43.1"), new If("wlan0",false,false,null), new If("ccmni0",false,false,null));
    List<If> carWithOldP2p=new ArrayList<>(car); carWithOldP2p.add(new If("p2p0",false,true,"192.168.49.1"));
    List<If> beforeApUp=Arrays.asList(new If("lo",true,true,"127.0.0.1"), new If("wlan0",false,false,null));
    String[][] cases={
      {"car AP up, LocalHotspot handed name+password", resolve(car,null,"","AndroidShare_1001","k3y-1-secret",false), "SUCCESS via ap0"},
      {"same, but p2p0 still has an address", resolve(carWithOldP2p,null,"","AndroidShare_1001","k3y-1-secret",false), "SUCCESS via ap0"},
      {"no name saved (what happened at 10:15)", resolve(car,null,"","","",false), "FAIL: no network name"},
      {"asked before ap0 has its address", resolve(beforeApUp,null,"","AndroidShare_1001","k",false), "WAIT"},
    };
    for(String[] c:cases){ boolean ok=c[1].startsWith(c[2]); System.out.println((ok?"  PASS  ":"  FAIL  ")+c[0]+" -> "+c[1]); if(ok)pass++; else fail++; }
    System.out.println("  ("+pass+" passed, "+fail+" failed)"); System.exit(fail==0?0:1);
  }
}
