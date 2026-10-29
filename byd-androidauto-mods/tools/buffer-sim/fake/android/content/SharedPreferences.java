package android.content; public interface SharedPreferences { int getInt(String k,int d); Editor edit(); interface Editor{Editor putInt(String k,int v); void apply();} }
