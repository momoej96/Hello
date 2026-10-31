package android.media;
/** Fake track: plays 48 kHz stereo in real time while PLAYING; counts underruns. */
public class AudioTrack {
  public static final int PLAYSTATE_PAUSED=2, PLAYSTATE_PLAYING=3;
  final int rate=48000, capFrames; long buffered; int state=PLAYSTATE_PLAYING; long last=System.nanoTime(); long head;
  public int underrunMs; boolean dry; public int underruns;
  public AudioTrack(int capFrames){this.capFrames=capFrames;}
  synchronized void tick(){ long now=System.nanoTime(); long f=(now-last)*rate/1000000000L; last=now;
    if(state==PLAYSTATE_PLAYING){ long played=Math.min(f,buffered); buffered-=played; head+=played; long miss=f-played;
      if(miss>0){ underrunMs+=miss*1000/rate; if(!dry){underruns++;dry=true;} } else dry=false; } }
  public synchronized int getChannelCount(){return 2;} public int getAudioFormat(){return 2;} public int getSampleRate(){return rate;}
  public synchronized int getPlayState(){tick();return state;} public synchronized void pause(){tick();state=PLAYSTATE_PAUSED;}
  public synchronized void play(){tick();state=PLAYSTATE_PLAYING;dry=false;} public synchronized int getPlaybackHeadPosition(){tick();return (int)head;}
  public int getBufferSizeInFrames(){return capFrames;}
  public int write(byte[] b,int off,int len){ long frames=len/4; while(true){ synchronized(this){tick(); if(buffered+frames<=capFrames){buffered+=frames;return len;}} try{Thread.sleep(2);}catch(Exception e){} } }
}
