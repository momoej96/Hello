# BYD DiLink 3 + DiAuto: car-control mods

These are the DiPlay (CarPlay) car controls from `byd-carplay-mods/` ported to **DiAuto 0.3.12** (an Android Auto
head-unit app). Read `byd-carplay-mods/KNOWLEDGE.md` first: the car facts (keys, AC calls, permissions,
sleep and wake) apply here unchanged. The engine water temperature gauge was left out on purpose.

Builds: **mod1** (`versionCode 1001`) car controls; **mod2** (`versionCode 1002`, `0.3.12-mod2`) adds the
diagnostic-report fix; **mod3** (`1003`) handles "Choose save location" without a picker and shows why a save
failed; **mod4** (`1004`) restarts Wi-Fi Direct when the phone is stuck waiting for credentials.
*Not tested in the car yet.*

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

## Smali changes (`smali-patches/diauto-0.3.12-mods.diff`)

* `SettingsFragment.updateSettingsList`: one `invoke-static {v0, v1}, SettingsHook->addEntry(List, Object)` after the
  keymap row's `List.add`. At that point `v0` is the list and `v1` is `this`.
* `SettingsFragment.<init>`: `basicSettingIds` grows from 15 to 16 entries with `"bydCarControls"`.
* `DiagnosticsFragment$export$2$result$1.invokeSuspend`: the build-and-save block is replaced by one
  `ReportSaver.save(context, destination, fileName)` call inside the original try/catch.
* `DiagnosticsFragment$export$2`: `"Downloads/DiAuto/"` is replaced by `ReportSaver.wherePrefix()`.
* `y0.l2.V0` (Wi-Fi Direct credential refresh): `return-void` after `p1(...)` reports the manager stopped is
  replaced by `goto :goto_0`, the existing `m1()` call.
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
