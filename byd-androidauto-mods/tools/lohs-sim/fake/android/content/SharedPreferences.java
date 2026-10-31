package android.content;
public interface SharedPreferences { int getInt(String k,int d); boolean getBoolean(String k,boolean d); String getString(String k,String d); Editor edit();
 interface Editor { Editor putInt(String k,int v); Editor putBoolean(String k,boolean v); Editor putString(String k,String v); void apply(); } }
