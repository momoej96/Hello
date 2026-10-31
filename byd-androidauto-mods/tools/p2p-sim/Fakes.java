public class Fakes {
  /** Stands in for y0.l2 (DiAuto's WifiDirectManager): S0 = recover/recreate group, G = attempts. */
  public static class FakeWifiDirectManager { private int G; java.util.List<String> recreated=new java.util.ArrayList<>();
    private void S0(String reason){ G++; recreated.add(reason); System.out.println("    >> DiAuto S0 (recreate group) called: "+reason+"  [G="+G+"]"); } }
}
