import android.media.*;
public class Sim {
  // Arrival pattern from the car log: steady 20 ms audio chunks, with stalls of 1.4 s and 2.0 s
  // whose data then arrives in one burst (TCP keeps it, Wi-Fi delays it).
  static void run(String name, int bufferMs, boolean useBuffer) throws Exception {
    java.lang.reflect.Field f=com.andrerinas.openheadunit.byd.AvBuffer.class.getDeclaredField("audioMs"); f.setAccessible(true); f.setInt(null,bufferMs);
    int cap = useBuffer ? com.andrerinas.openheadunit.byd.AvBuffer.audioBufferSize(65792,48000,2)/4 : 65792/4;
    AudioTrack t=new AudioTrack(cap);
    byte[] chunk=new byte[960*4]; // 20 ms
    long start=System.nanoTime(); int[] stalls={3000,1400, 7000,2000, 11000,1400, 14000,2000};
    int sent=0; long totalMs=17000;
    for(long ms=0; ms<totalMs; ms+=20){
      long due=start+ms*1000000L; int si=-1;
      for(int i=0;i<stalls.length;i+=2) if(ms>=stalls[i]&&ms<stalls[i]+stalls[i+1]) si=i;
      if(si>=0) due=start+(stalls[si]+stalls[si+1])*1000000L; // held until the stall ends
      long w=due-System.nanoTime(); if(w>0) Thread.sleep(w/1000000L,(int)(w%1000000L));
      if(useBuffer) com.andrerinas.openheadunit.byd.AvBuffer.audioWrite(t,chunk,chunk.length); else t.write(chunk,0,chunk.length);
    }
    Thread.sleep(bufferMs+500);
    System.out.printf("%-28s underruns=%d  silent=%d ms%n", name, t.underruns, t.underrunMs);
  }
  static void video(String name, int ms, boolean stall, boolean jitter) throws Exception {
    java.lang.reflect.Field vf=com.andrerinas.openheadunit.byd.AvBuffer.class.getDeclaredField("videoMs"); vf.setAccessible(true); vf.setInt(null,ms);
    java.lang.reflect.Field cf=com.andrerinas.openheadunit.byd.AvBuffer.class.getDeclaredField("videoCodec"); cf.setAccessible(true); cf.set(null,null);
    MediaCodec c=new MediaCodec(); long st=System.nanoTime(); java.util.Random r=new java.util.Random(1);
    for(int i=0;i<180;i++){ long due=i*33L; if(stall && due>=2000 && due<3400) due=3400;
      if(jitter){ int k=i%10; due = (i/10)*330L + (k<7? 0 : 0) + (k<7? k*5 : 35+ (k-7)*100); } // 7 frames bunched, then slow
      long w=st+due*1000000L-System.nanoTime(); if(w>0) Thread.sleep(w/1000000L,(int)(w%1000000L));
      if(com.andrerinas.openheadunit.byd.AvBuffer.videoRelease(c,i)<0) c.releaseOutputBuffer(i,true); }
    long prev=0, maxGap=0, back=0; double sum=0,sq=0; int n=0;
    for(long[] s: c.shown){ if(prev>0){ long g=(s[1]-prev)/1000000L; if(g<0) back++; maxGap=Math.max(maxGap,g); sum+=g; sq+=g*g; n++; } prev=s[1]; }
    double mean=sum/n, sd=Math.sqrt(sq/n-mean*mean);
    long[] last=c.shown.get(c.shown.size()-1);
    System.out.printf("%-32s shown=%d skipped=%d  spacing %.0f±%.0f ms  longest=%d ms  backwards=%d  delay at end=%d ms%n", name, c.shown.size(), c.skipped, mean, sd, maxGap, back, (last[1]-last[0])/1000000L);
  }
  public static void main(String[] a) throws Exception {
    run("DiAuto now (340 ms track)", 0, false);
    run("Buffer 1000 ms", 1000, true);
    run("Buffer 1500 ms", 1500, true);
    run("Buffer 2000 ms (default)", 2000, true);
    video("Video 150 ms, 1.4 s stall", 150, true, false);
    video("No video buffer, jittery Wi-Fi", 0, false, true);
    video("Video 150 ms, jittery Wi-Fi", 150, false, true);
  }
}
