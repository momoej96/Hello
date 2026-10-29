# BYD DiLink 3 + DiAuto: car-control mods

These are the DiPlay (CarPlay) car controls from `byd-carplay-mods/` ported to **DiAuto 0.3.12** (an Android Auto
head-unit app). Read `byd-carplay-mods/KNOWLEDGE.md` first: the car facts (keys, AC calls, permissions,
sleep and wake) apply here unchanged. The engine water temperature gauge was left out on purpose.

Builds: **mod1** (`versionCode 1001`) car controls; **mod2** (`versionCode 1002`, `0.3.12-mod2`) adds the
diagnostic-report fix; **mod3** (`1003`) handles "Choose save location" without a picker and shows why a save
failed; **mod4** (`1004`) restarts Wi-Fi Direct when the phone is stuck waiting for credentials.; **mod5** (`1005`) adds the audio/video buffer,
the Qin Plus DM-i defaults, the poke guard and the Bluetooth-settings crash fix; **mod6** (`1006`) pins the
WiFi Direct group to 2.4 GHz channel 6; **mod7** (`1007`) is WiFi Direct only: the group follows the car's Wi-Fi
channel and is recreated on every join failure, and the app starts with the car; **mod8** (`1008`) connects over
the car's own local-only Wi-Fi network, started and filled in by the app, with WiFi Direct as the automatic fallback (tested: the phone did not connect, no report); **mod9** (`1009`) removes the car controls and keeps only starting with the car and connecting by itself, plus a status line on the home screen. mod9 connected in the car without a hotspot (car's local network) but lagged; **mod10** (`1010`) adds the "Picture & sound" page (video settings, smooth video buffers, DiPlay-style sound adjustments). mod10 worked in the car ("good, not perfectly smooth"); **mod11** (`1011`) adds an Equalizer row to Quick Settings and keeps the car's bottom bar over Android Auto. mod11 worked, but the bar still hid (the log showed `fullscreen-mode` back at immersive) and the picture was slow; **mod12** (`1012`) is for smoothness at 60 fps / 1280x720. *mod12 not tested in the car yet.*

## The app

| Item | Value |
|---|---|
| APK | `DiAuto-v0.3.12.apk`, sha256 `b0c0db4d76c9cacc…6add9a4`, versionCode 112 |
| Package (applicationId) | `com.andrerinas.headunitrevived` |
| Code | `com.andrerinas.openheadunit.*`, a fork of Headunit Revived, obfuscated with R8 |
| Dex | `classes.dex` and `classes2.dex`; the mod adds `classes3.dex` |
| Already has | key mapping for Android Auto, media-button receivers, boot/screen-on/USB/Wi-Fi auto-start, Shizuku |
| Doesn't have | an accessibility service, on-device ADB, or BYD car API calls |

## What the mod adds (package `com.andrerinas.openheadunit.byd`)

* **`LocalAdb`**: a small ADB client that talks to the head unit's own `adbd` on `127.0.0.1:5555`, falling back to
  5556. DiAuto has no ADB code of its own (DiPlay had `BydAdbShell`). The RSA key lives in `files/adb/`. The first
  connection triggers the "Allow USB debugging?" prompt. The public key format was checked against the
  mincrypt layout (n0inv, rr, exponent).
* **`WheelKeyService`**: an accessibility service with `flagRequestFilterKeyEvents`. It hands every key to `CarKeys`,
  which is unchanged from DiPlay: named BYD keys plus two learnt slots, single/double/long press, and replay with
  `input keyevent` when only a double press is assigned.
* **`CarActions` / `CarAc` / `CarAcShell` / `PermissiveContext`**: the AC and climate-screen actions, as in DiPlay.
  Each command is tried in-process first, then through `app_process` as the shell user. "Open climate app" was
  dropped because it was a DiPlay-only shortcut. Settings are kept in the `byd_car_controls` prefs.
* **`CarWake`**: when the wheel-key service is bound in a freshly started process (which is what happens after the car
  wakes and the process had been killed), it calls DiAuto's own `BootCompleteReceiver` with `QUICKBOOT_POWERON`.
  That way DiAuto's Auto-start settings decide what happens. If DiAuto's service survived the sleep, its own
  `SCREEN_ON` wake detection handles it instead.
* **`CarControlsActivity`**: a "BYD car controls" page built with plain views in DiAuto's colours. It has setup
  (Test ADB, turn on the service over ADB, open BYD's hidden accessibility page, allow car control), the car keys,
  other keys, the climate screen, and "Try an action".
* **`SettingsHook`**: adds the "BYD car controls" row straight after "Key mapping" in Settings, on both the Basic
  and Advanced tabs.

## Diagnostic report (mod2)

DiAuto's "Save diagnostic report" on Android 10+ only writes through MediaStore Downloads (`g1.w.a`), and its
fallback is the system file picker (`CreateDocument`). The user reported that the report doesn't save on the car.
`ReportSaver.save` replaces the save step in `DiagnosticsFragment$export$2$result$1` and tries these in order:

1. A picked Uri, if a picker was used.
2. MediaStore `Downloads/DiAuto`.
3. `/sdcard/Download/DiAuto` written directly. This needs `WRITE_EXTERNAL_STORAGE`; the manifest now sets
   `requestLegacyExternalStorage`.
4. `Android/data/com.andrerinas.headunitrevived/files/reports/`, which always works. If ADB was allowed before,
   the shell also copies the file to `/sdcard/Download/DiAuto`.

The report gains a "BYD car controls" section (firmware, service state, ADB, permissions, car-control prefs) and
the app's own logcat. When the report has to fall back to steps 3 or 4, the failures from the earlier steps are
appended to it. The "Report saved" dialog shows the real folder (`ReportSaver.wherePrefix`). If DiAuto's own
report builder (`g1.z.a`) throws, the error text is saved in its place.

In the car (mod2 photo), the unit showed DiAuto's own toast "No file picker is available". That toast comes from
`chooseLocation`, which is reached either from the button or from the "Could not save" dialog. mod3 changes two
things:
* `chooseLocation`: when the picker is missing, it calls `ReportSaver.noPicker`, which saves straight to the app
  folder and shows the path in a long toast.
* The "Could not save the report" dialog now appends what each save attempt hit (`ReportSaver.withFailure`).

## Log from the car, 2026-10-29

* The unit in the log is a **BYD Qin Plus DM-i** (`秦Plus DMi`), not the Qin L from the DiPlay notes. It reports
  **Android 9 (API 28)**, a MediaTek MT6765 (`k65v1_64_bsp`) and a 1280x720 screen. The phone is a Galaxy S24.
* **Stuck connection (09:01:41 to 09:03:20, the old process):** every 12 s the phone connected over Bluetooth,
  waited for Wi-Fi credentials (`SSID=<null>`), and the refresh was dropped with
  `credential refresh abandoned - the manager was stopped while it was in flight`. The phone then reconnected,
  cancelled the previous handshake, and the cycle repeated until the app was reinstalled. `WifiDirectManager`
  (`y0.l2`) had been stopped while the Bluetooth handshake server kept accepting connections, and the refresh path
  (`l2.V0`) gave up instead of starting it again.
  **mod4:** when `V0` is abandoned, it falls through to `m1()` (startNativeAaQuietHost), which re-arms the
  manager and creates the group again.
* **Video and audio stalls once connected:** the decoder was fine (MTK AVC decoder, first frame in about 80 ms).
  Frames simply stopped arriving: 17 fps, then 0 to 2 fps, `inbound link quiet ... dead=4839ms`, and repeated
  AudioTrack underruns. DiAuto logged the cause: the unit's `wlan0` is joined to another Wi-Fi network on 2412 MHz
  (`10.207.103.248`) while it hosts the Wi-Fi Direct group, so one radio serves both. On Android 9 the group can't
  be moved to 5 GHz. The fix is configuration: make the car forget or disconnect that Wi-Fi network, or use DiAuto's
  hotspot mode.
* Throughput numbers from the session: in every 5 s window `fed` equals `rendered`, the decoder's input wait is
  tiny, and nothing is dropped, so decoding is never the bottleneck. Frames arrive in bursts (up to 54 fps) and
  then nothing for 5 to 11 s. The AudioTrack underruns fall in the same gaps. Both stalls have one cause: the
  link from the phone. A smaller, separate loss sits in the display: in one window the decoder produced 85 frames
  and the TextureView showed 23. Recommended settings: View mode SurfaceView, FPS limit 30.
* The file that came back is a raw logcat, without DiAuto's report header or the BYD section.

## Second log (mod4), 2026-10-29

* **Crash:** `HomeFragment.openBluetoothSettings` fell back to `android.settings.SETTINGS`, which BYD doesn't
  have, so the app died with `ActivityNotFoundException`. **mod5:** `AapGuard.openBluetoothFallback` tries other
  settings screens and then shows a toast.
* **The phone failed to join, three times:** `WifiConnectStatus status=-11` came back roughly every 40 s before the
  fourth try worked. The STA was on 2462 MHz this time. This is the shared-radio problem again.
* **Opening the app during a connection broke it:** the user tapped the app at 09:27:09, two seconds after the
  phone's TCP session landed. DiAuto sent a manual poke, logged "listeners are closed - re-arming", re-initialised
  Wi-Fi mode, released port 5288, and poked the phone. For the next 37 s the phone opened the Bluetooth AA channel
  **114 times** (about every 0.3 s), and DiAuto aborted each one ("USB/other session already active"). On this
  MT6765, Bluetooth shares the 2.4 GHz radio with Wi-Fi, and the video dropped to 0 to 4 fps.
  **mod5:** `AapGuard` tracks the session (`AapService.t0` and `u1`, the WifiLock), and `ACTION_NATIVE_AA_POKE`
  is skipped while a session is up.

## Third log: no phone hotspot (mod5), 2026-10-29 09:39-09:45

* The car's Wi-Fi switch was off ("WiFi is disabled but needed for Native AA. Attempting to enable..."), and at
  report time `wlan0` was down while `p2p0` was up. The group formed and the credentials went over Bluetooth, but
  the S24 answered `WifiConnectStatus -11` about 35 s later on every one of 5 tries in 4 minutes. It never joined.
* With the phone's hotspot on, the car's station joined it on 2.4 GHz (2412 and 2462 MHz in the earlier logs), the
  group followed onto the same channel, and the phone joined at once.
* At 08:57 the transport had been set to **Hotspot** while the car's hotspot was off
  ("SoftApCredentials: No usable access point after 30s"). That caused the first stuck loop. It was later set back
  to WiFi Direct (`native transport=0`).
* Android 9 doesn't report the group's frequency. DiAuto's own API 29+ code warns that groups on channel 12/13 are
  invisible to phones limited to channels 1-11. This test-keys unit may well be using a region code that allows them.
* "Force WiFi Direct onto 2.4 GHz" (`debug-force-p2p-band-24`) does nothing below API 29. Only
  `AapProjectionActivity` reads it.
* **mod6:** `CarP2p.channel` replaces the result of `v0.l3.d(...)` (DiAuto's operating-channel pick for API < 29).
  It defaults to channel 6 and can be changed under BYD car controls → WiFi Direct channel (Auto, 1, 6, 11, 36-48,
  149). DiAuto then calls `setWifiP2pChannels(0, ch)` before `createGroup`. If the unit refuses, it logs "would not
  take an operating channel" and carries on with the driver's choice.

## Fourth log (mod6) and mod7, 2026-10-29

* 09:46:48: the group came up while the car's Wi-Fi was still unconnected. At 09:47:00 the station joined a
  network on 2437 MHz. Seven join failures (-11) followed over 5 minutes, because DiAuto's join watchdog kept
  deferring while a Bluetooth handshake was in flight. At 09:51:49 the watchdog recreated the group, now on the
  station's channel, and the phone joined in 4 s. The MT6765 radio can't host the group on a different channel
  from the station.
* The phone's last Bluetooth attempt was at 10:00:43. After many failures it stops trying until Bluetooth is
  toggled, so mod6 (10:06) and the hotspot test (10:09) never actually got a phone attempt.
* Hotspot test: `ap0` came up and was seen, but `Hotspot name saved=false` meant there were no credentials to send.
* `native-ap-transport` defaults to **1 (head unit hotspot)**. Index 0 is WiFi Direct (`SettingsFragment` lists
  `Q5` WiFi Direct, then `P5` Hotspot). That default caused the 08:57 stuck loop.
* **mod7:**
  * `CarP2p.channel(int, l2)` uses the station's channel when it is connected, otherwise 6. There are no 5 GHz
    options.
  * `CarP2p.handshakeFailed` is hooked after NativeAA logs "Handshake failed — ...". On "join failure" it calls
    `l2.S0` (DiAuto's recover/recreate) right away, inside the ~2 s gap before the phone retries. It holds `G`
    below DiAuto's give-up count of 4.
  * When the station's channel changes, the group is recreated after 3 s. Nothing is recreated while a session is
    up.
  * `CarDefaults`, on every start: `native-ap-transport=0` and the `p2p-legacy-5ghz*` options off. Once:
    `auto-start-on-boot` and `auto-start-on-screen-on` (device-protected prefs).
  * `tools/p2p-sim/run.sh`: 13/13.

## Fifth log (mod7) and mod8, 2026-10-29 10:41

* mod7 behaved as written. The group followed the station to channel 11. When the station dropped (10:41:05,
  `wlan0` down), it was recreated on channel 6. Each join failure recreated it at once. The phone still answered
  -11 every time on channel 6. Across all five logs, the phone joined the WiFi Direct group only while the car's
  Wi-Fi was connected to the phone's hotspot. The channel was not the deciding factor.
* Recreate attempts 2 and 3 go through `T0(true)` ("forcing 2.4GHz"), which skips the operating-channel hook.
* **mod8:** `LocalHotspot` runs Android's local-only hotspot (API 26+; on Android 9 it is 2.4 GHz with a random
  SSID and passphrase, readable by the app). Android 9 only grants one to a foreground app, so the request goes
  through the invisible `HotspotActivity`. On `onStarted`, the SSID and passphrase are written to DiAuto's
  `hotspot-ssid` and `hotspot-password` fields, and `hotspot-interface` is left automatic. DiAuto's own Hotspot
  transport (`y0.d1`) then resolves `ap0` and hands the network to the phone. It is hooked from
  `AapService.K0` (Hotspot mode start) and from `N1` ("Access point refresh requested", about every 10 s while the
  phone waits), and is idempotent. `onStopped` restarts after 3 s. Three refusals set `lohs_failed` and transport 0
  (WiFi Direct). `CarDefaults` now sets transport 1 unless `lohs_failed` is set.
* DiAuto's own LOCAL_HOTSPOT transport (2) exists in `connection.b`, but `j1.f1()` maps 2 to 1, and the
  implementation rejects anything outside 5160-5895 MHz. Hence a separate implementation.
* `tools/lohs-sim/run.sh`: 14 checks of `LocalHotspot` against a fake radio (start, duplicate requests, system stop
  and restart, refusals and fallback, reset, manual WiFi Direct). It also runs a port of DiAuto's resolver
  (`d1.u/v`, `t3`, `s3`, `g3`) against the car's reported interfaces: `ap0` is picked and credentials go out, and
  the 10:15 failure (no name saved) reproduces.

## Audio / video buffer (mod5)

* **Audio** (`c1.s`, media stream only): the AudioTrack is sized for the buffer time plus 1.5 s. Playback pauses
  whenever the buffer runs dry and resumes once it holds the chosen time again (default 2000 ms). After 300 ms
  without new data, whatever is buffered plays anyway, so short clips are never held back. Mono guidance and
  system sounds are untouched.
* **Video** (`decoder.g.X`): each frame is released with `releaseOutputBuffer(index, time)`, at least the chosen
  delay ahead (default 150 ms) and spaced at 85 % of the learned average frame interval, so bursts are spread out
  and the backlog drains. Frames more than delay + 300 ms behind are skipped.
* **Defaults applied once** (`CarDefaults`, run from `App.onCreate`): `view-mode` 0 (SurfaceView) and `fps-limit` 30.
* `tools/buffer-sim/run.sh` replays the log's pattern on the desktop:

  | Audio, 1.4 s and 2 s stalls | Silence |
  |---|---|
  | DiAuto before (340 ms) | 1977 ms |
  | 1000 ms | 1017 ms |
  | 1500 ms | 517 ms |
  | 2000 ms (default) | 17 ms |

  For video with jittery arrival, frame spacing goes from 32±43 ms to 32±18 ms, with no frames out of order.
  A 1.4 s stall still shows as a 1.4 s freeze: the video buffer is kept small because it also delays touches.

## Smali changes (`smali-patches/diauto-0.3.12-mods.diff`)

* `SettingsFragment.updateSettingsList`: one `invoke-static {v0, v1}, SettingsHook->addEntry(List, Object)` after the
  keymap row's `List.add`. At that point `v0` is the list and `v1` is `this`.
* `SettingsFragment.<init>`: `basicSettingIds` grows from 15 to 16 entries with `"bydCarControls"`.
* `DiagnosticsFragment$export$2$result$1.invokeSuspend`: the build-and-save block is replaced by one
  `ReportSaver.save(context, destination, fileName)` call inside the original try/catch.
* `DiagnosticsFragment$export$2`: `"Downloads/DiAuto/"` is replaced by `ReportSaver.wherePrefix()`.
* `y0.l2.V0` (Wi-Fi Direct credential refresh): `return-void` after `p1(...)` reports the manager stopped is
  replaced by `goto :goto_0`, the existing `m1()` call.
* `c1.s.i` (AudioTrack size): after `mul-int v9, v8, p5`, calls `AvBuffer.audioBufferSize(v9, rate, channels)`.
* `c1.s.w`: `AudioTrack.write` is replaced by `AvBuffer.audioWrite(track, data, len)`.
* `decoder.g.X`: starts with `AvBuffer.videoRelease(codec, index)`; `-1` falls through to DiAuto's own path.
* `App.onCreate`: calls `CarDefaults.apply(this)` right after `super.onCreate()`.
* `AapService.K0` (Hotspot mode start) and `N1` (access point refresh): `LocalHotspot.ensure(this)` after their log line.
* Manifest: `HotspotActivity` (translucent, no history, not in recents, `taskAffinity=""`).
* `AapService.t0` / `u1`: call `AapGuard.sessionStarted()` / `sessionEnded()` first.
* `AapService.onStartCommand`, `ACTION_NATIVE_AA_POKE`: `if AapGuard.skipPoke() goto :goto_e` (the method's return).
* `y0.l2` (group creation, API < 29): after `v0.l3.d(IZZ)I`, `CarP2p.channel(v0, this)` replaces the channel.
* `y0.i0$e`: after the "NativeAA: Handshake failed — " log line, `CarP2p.handshakeFailed(message)`.
* `HomeFragment.openBluetoothSettings`: the catch block calls `AapGuard.openBluetoothFallback(this)` and returns.
* Manifest: `requestLegacyExternalStorage="true"`, `BYDAUTO_AC_COMMON/GET/SET`, the activity, and the accessibility service (`res/xml/byd_wheel_keys.xml`
  plus three strings).

jadx can't decompile `updateSettingsList` because the method is too big, so check changes there in smali.

## Building

`tools/build.sh <DiAuto-v0.3.12.apk> <tools-dir> <out.apk> [versionCode] [versionName]`. It needs the same tools as
the DiPlay build. The build compiles against the API 16 `android.jar`, so `java-src/stub/android/accessibilityservice`
supplies `onKeyEvent` (API 18) at compile time only. The output is signed with uber-apk-signer's debug key
(`1e08a903…5953`), the same key as the DiPlay mod. Switching from the developer's original DiAuto needs an
uninstall once, which also loses DiAuto's settings. Use DiAuto's settings export before uninstalling if you want
to keep them.

## To check in the car

1. Test ADB: the prompt appears, Always allow works, and the port is 5555.
2. Turn on the wheel key service. Check that the keys arrive, both while Android Auto is showing and while it isn't.
3. Check that the AC actions work in-process once `BYDAUTO_AC_COMMON` is granted.
4. Check that DiAuto comes back after the car sleeps and wakes.

## mod9: only start with the car and connect by itself, 2026-10-29

The user asked for no extra features: the app should start with the car and connect over Wi-Fi without touching
the phone (a hotspot that the app switches on by itself is fine; the phone's own hotspot, even through a Samsung
routine, is not). mod8 was tried in the car and the phone did not connect; no report could be taken.

Removed: the "BYD car controls" page and its Settings row (`SettingsFragment` hunks), wheel-key actions (`CarKeys`),
AC and climate screen (`CarAc`, `CarAcShell`, `PermissiveContext`), the audio/video buffer (`AvBuffer`, the `c1.s`
and `decoder.g` hunks, `tools/buffer-sim`), the `BYDAUTO_AC_*` permissions. `CarActions` keeps only prefs, toast and
ADB. The prefs file stays `byd_car_controls` so values from earlier builds carry over.

Kept: the connection fixes (mod4 credential-refresh loop, mod5 poke guard and Bluetooth-settings crash, mod7
WiFi Direct channel and recreate-on-join-failure, mod8 local-only network), the report saver, `LocalAdb`.

Changed:
* `WheelKeyService` keeps its class name (an already enabled service stays enabled after the update) but no longer
  filters keys (`flagRequestFilterKeyEvents` removed from `res/xml/byd_wheel_keys.xml`); its label is now
  "DiAuto start with the car".
* `CarWake`: besides the fresh-process case, the service registers a `SCREEN_ON`/`SCREEN_OFF` receiver and runs
  DiAuto's boot receiver (`QUICKBOOT_POWERON`) when the screen comes on after at least 60 s off and no Android Auto
  session is up. This covers a process that survived the car's sleep.
* `CarDefaults`: every start clears `lohs_failed` and sets transport 1 (head unit hotspot = the car's local-only
  network). Before, three refusals switched to WiFi Direct for good, and WiFi Direct never worked without the
  phone's hotspot, so a single bad start could have left mod8 on the path that cannot work.
* `StatusLine` (new): a small panel at the bottom of DiAuto's home screen (`MainActivity` only, never over
  Android Auto) with "Start with the car: on/OFF" and the last 8 connection lines. It is fed by a hook at the top
  of `g1.a.s(int, String)`, DiAuto's single log writer (INFO and above, filtered by topic words such as NativeAA,
  handshake, p2p, hotspot, bluetooth, credential), and by `StatusLine.note` from the mod's classes. The first time
  the home screen opens with the service off, it switches the service on over ADB and shows the result.

Not done, on purpose: restarting the car's Bluetooth when the phone stops trying (the user declined).

Possible reason mod8 did not connect (unconfirmed): after many failures the phone stops opening the Bluetooth
channel until its Bluetooth is toggled (fourth log), and `lohs_failed` may have moved mod8 to WiFi Direct.

Checks: `tools/verify.sh` 71,510 methods, 0 findings; signature `1e08a903…5953` (installs over mod8 without
uninstalling); `tools/lohs-sim` 18/18 and `tools/p2p-sim` 13/13.

## Car report with lag (mod9, 2026-10-29 17:19) and mod10

* mod9 connected over the car's local-only network (`native transport=1`, `status=0`): the start-without-a-hotspot
  goal works. 6 sessions; the ends were the user leaving the projection, not drops.
* The lag is the link, not the decoder: `fed` equals `rendered` in every 5 s window, `dropped=0`, decoder input wait
  20-120 ms. Frames arrive in bursts (40-45 in one window, then 13-16 fps).
* The first session negotiated `1280x720@30` (24-29 fps); every later one `1280x720@60` (13-22 fps): the FPS limit
  had been set to 60 and the 2.4 GHz local network (Android 9 gives no 5 GHz) cannot carry it.
* Start with the car still off: `Wheel key service: off`, ADB is off on this unit (port 5555 does not answer), and
  DiAuto logged "Overlay permission not granted, disabling auto-start settings". Needs "Display over other apps" and
  the accessibility service switched on by hand.
* 800x480 with H.264 was a little smoother but blurry and large. DiPlay is much smoother on the same screen with
  Smooth video, Direct video output, Low latency decoding and HEVC. Three of the four already exist in DiAuto:
  `video-codec` "H.265" (MT6765 reports `hasHwHevc=true`), `view-mode` 0 (SurfaceView = direct output) and
  `debug-video-low-latency` (a hidden debug toggle that sets the vendor keys, MediaTek `vdec-lowlatency`). Smooth
  video is the mod5 buffer. 1080p is not worth it: the panel is 1280x720 and DiAuto itself warns about it.

mod10:
* `TuningActivity` "Picture & sound", reached from a row right under "Connection mode" in Settings (General).
  `SettingsHook.addEntry` is called after that row's `List.add` in `updateSettingsList` (`v0` list, `v1` this) and
  `pictureAndSound` joins `basicSettingIds` (array 15 → 16). Opening the page finishes `SettingsActivity`, because
  `SettingsFragment` loads a pending copy of resolution, DPI, codec, view mode and FPS in `onViewCreated` and its
  Save would write the old values back.
* Video rows write DiAuto's own prefs (`settings`): `video-codec` (Auto / H.264 / H.265), `resolutionId`
  (0 auto, 1 480p, 2 720p, 3 1080p), `fps-limit`, `view-mode` (0 Surface, 1 Texture, 2 GLES),
  `debug-video-low-latency`, `dpi-pixel-density` (0 auto). Changing resolution or FPS clears
  `video-profile-starvation-cap` (DiAuto's own cap after sessions that rendered nothing).
* Smooth video: `AvBuffer` is back with its `c1.s` and `decoder.g` hunks (video 0/80/150/250/400 ms, audio
  0/500/1000/1500/2000/3000 ms). `tools/buffer-sim` is back too (1976 → 16 ms of silence with the 2000 ms audio
  buffer; video spacing 32±45 → 32±18 ms).
* Sound (`AudioFx`): equalizer (the device's own bands), bass boost, virtualizer (surround) and loudness, like
  DiPlay's `AudioEffectsEngine`, but attached to DiAuto's stereo media AudioTrack session from `AvBuffer.audioWrite`,
  so only Android Auto's music changes. Off by default; values in the mod's prefs (`fx_*`); applied live. The
  attach is outside the buffer's try block so a failure there never turns the buffer off (the sim caught that).
* "Use the recommended values" and, once on the first start of mod10 (`car_defaults_v3`): H.265, 1280x720, 30 fps,
  SurfaceView, low latency on, video 150 ms, audio 2000 ms. DPI and sound are left alone.
* Checks: `tools/verify.sh` 71,623 methods, 0 findings; signature `1e08a903…5953`; sims 4/4 sections, 13/13, buffer
  numbers as above.

## mod11: Equalizer in Quick Settings, car's bottom bar kept

* Quick Settings is `QuickSettingsFragment` (opened from the "Exit Android Auto" dialog over the projection). In
  `updateSettingsList` (`v0` this, `v1` the list) `SettingsHook.addEqualizer(list, this)` runs right after the Audio
  section's last row (`audioQueueCapacity`). The row opens `SoundPanel.showDialog`: the sound controls in a dialog,
  so Android Auto keeps running behind it. `SoundPanel` also builds the Sound card of Picture & sound (one copy of
  the controls).
* The bar: DiAuto's `fullscreen-mode` already has "Hide status bar only" (2: hides the status bar, shows the
  navigation bar). Its default is 1 (immersive, both hidden). mod11 sets 2 once (`car_defaults_v4`) and Picture &
  sound has a "Car bars over Android Auto" row (bottom bar only / no bars / both bars).
* Checks: `tools/verify.sh` 71,641 methods, 0 findings; signature `1e08a903…5953`; sims unchanged.

## Car log 19:02 (mod11) and mod12: smooth at 60 fps, 1280x720

* HUR log 18:58-19:02: the phone sent H.265 (`OMX.MTK.VIDEO.DECODER.HEVC`, SPS 1280x720) and the decoder took the
  low-latency key (`optionalKeys=vendor [vdec-lowlatency]`). `dropped=0`, small input wait: the head unit keeps up.
  Frames per 5 s window went 27, 23, 26, 16, then about 10 for a minute, back to 21-27. AA only sends a frame when
  the picture changes, so a still screen also reads low. `isAac=false` (raw PCM 48 kHz stereo, about 1.5 Mbit/s) and
  `Mode: IMMERSIVE`: DiAuto's Settings Save had written back older copies of both.
* The user wants 60 fps at 1280x720 kept, and smoothness first (a little delay is fine). The 17:19 report already
  showed `@30` delivering 24-29 fps and `@60` 13-22 fps on this 2.4 GHz link, so mod12 frees the link and evens out
  what arrives instead of asking for less.
* Rejected: a bigger `max_unacked` window (v0.m.b). DiAuto acks a video message as soon as v0.j2.g hands it to the
  decoder queue (v0.u -> v0.i2.Z), so 12 frames (about 200-400 ms) never fills; and the decoder's feed queue
  (decoder.g.S, ArrayBlockingQueue of 15) drops on overflow (`Y` + `U`), which a 50-frame window would trigger and
  turn into smearing until the next keyframe.

mod12:
* AAC audio: Picture & sound row "AAC audio" (the mod's `aac_audio`, default on) is written into DiAuto's
  `use-aac-audio` at app start and every time DiAuto's home screen resumes (`TuningActivity.enforce`, from the
  StatusLine lifecycle callback), so a Settings Save with an old copy cannot turn it off for long.
* Decoder at full speed: `decoder.g.o0`'s `MediaCodec.configure` is replaced by `AvBuffer.configureVideo`, which sets
  `priority` 0 (real time) and `operating-rate` 120. If the codec throws, it is reset (reflection, API 21) and
  configured again with priority 1 / rate 30 (MediaFormat.removeKey is API 29); a second failure goes to DiAuto's
  catch as before. `tools/buffer-sim` checks both paths.
* Video buffer default 250 ms (15 frames at 60 fps), set once (`car_defaults_v5`) with AAC on. "Use the recommended
  values" now means H.265, 1280x720, 60 fps, AAC, SurfaceView, low latency, video 250 ms, audio 2000 ms.
* Checks: `tools/verify.sh` 71,645 methods, 0 findings; signature `1e08a903…5953`; sims pass (buffer sim models
  30 fps arrival only).
