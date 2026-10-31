package android.content; import java.util.*;
public class Context { public static final String WIFI_SERVICE="wifi"; public Map<String,MapPrefs> prefs=new HashMap<>(); public Object wifi; public int activityStarts; public boolean blockActivities;
 public Context getApplicationContext(){return this;} public Object getSystemService(String n){return wifi;}
 public synchronized SharedPreferences getSharedPreferences(String n,int mode){ return prefs.computeIfAbsent(n,k->new MapPrefs()); }
 public void startActivity(Intent i){ if(blockActivities) throw new SecurityException("background start blocked"); activityStarts++;
   // HotspotActivity.onCreate does exactly this:
   com.andrerinas.openheadunit.byd.HotspotSim.onCreate(this); } }
