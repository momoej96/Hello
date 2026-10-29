package android.os;
import java.util.concurrent.*;
public class Handler { static ScheduledExecutorService ex=Executors.newSingleThreadScheduledExecutor(r->{Thread t=new Thread(r);t.setDaemon(true);return t;});
 public Handler(Looper l){} public boolean postDelayed(Runnable r,long ms){ex.schedule(r,ms,TimeUnit.MILLISECONDS);return true;} }
