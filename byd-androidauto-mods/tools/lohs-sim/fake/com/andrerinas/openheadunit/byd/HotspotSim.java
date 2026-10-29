package com.andrerinas.openheadunit.byd; public class HotspotSim { public static void onCreate(android.content.Context c){ LocalHotspot.requestNow(c); }
 public static void ensure(android.content.Context c){ LocalHotspot.ensure(c);} public static boolean running(){return LocalHotspot.running();}
 public static void reset(android.content.Context c){ LocalHotspot.reset(c);} }
