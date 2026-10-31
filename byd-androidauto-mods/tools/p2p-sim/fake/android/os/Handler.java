package android.os;
import java.util.concurrent.*;
public class Handler { static ScheduledExecutorService ex=Executors.newSingleThreadScheduledExecutor();
 static java.util.Map<Runnable,ScheduledFuture<?>> m=new java.util.concurrent.ConcurrentHashMap<>();
 public Handler(Looper l){}
 public boolean postDelayed(Runnable r,long ms){m.put(r,ex.schedule(()->{m.remove(r);r.run();},ms,TimeUnit.MILLISECONDS));return true;}
 public boolean post(Runnable r){return postDelayed(r,0);}
 public void removeCallbacks(Runnable r){ScheduledFuture<?> f=m.remove(r); if(f!=null) f.cancel(false);} }
