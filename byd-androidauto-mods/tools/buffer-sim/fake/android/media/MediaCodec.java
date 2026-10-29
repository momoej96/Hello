package android.media;
public class MediaCodec { public java.util.List<long[]> shown=new java.util.ArrayList<>(); public int skipped;
 public boolean rejectRealtime; public int configures, resets;
 public void releaseOutputBuffer(int i,long ts){ shown.add(new long[]{System.nanoTime(),ts}); }
 public void releaseOutputBuffer(int i,boolean r){ if(r) shown.add(new long[]{System.nanoTime(),System.nanoTime()}); else skipped++; }
 public void configure(MediaFormat f, android.view.Surface s, MediaCrypto c, int flags){ configures++;
   if(rejectRealtime && Integer.valueOf(0).equals(f.ints.get("priority"))) throw new IllegalArgumentException("refused"); }
 public void reset(){ resets++; } }
