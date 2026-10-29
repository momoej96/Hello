package android.media;
public class MediaCodec { public java.util.List<long[]> shown=new java.util.ArrayList<>(); public int skipped;
 public void releaseOutputBuffer(int i,long ts){ shown.add(new long[]{System.nanoTime(),ts}); }
 public void releaseOutputBuffer(int i,boolean r){ if(r) shown.add(new long[]{System.nanoTime(),System.nanoTime()}); else skipped++; } }
