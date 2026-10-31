package android.content; import java.util.*;
public class MapPrefs implements SharedPreferences { public final Map<String,Object> m=new HashMap<>();
 public int getInt(String k,int d){Object o=m.get(k);return o==null?d:(Integer)o;} public boolean getBoolean(String k,boolean d){Object o=m.get(k);return o==null?d:(Boolean)o;}
 public String getString(String k,String d){Object o=m.get(k);return o==null?d:(String)o;}
 public Editor edit(){ final Map<String,Object> e=new HashMap<>(); return new Editor(){
  public Editor putInt(String k,int v){e.put(k,v);return this;} public Editor putBoolean(String k,boolean v){e.put(k,v);return this;}
  public Editor putString(String k,String v){e.put(k,v);return this;} public void apply(){synchronized(m){m.putAll(e);}} }; } }
