# BYD DiLink 3 + DiPlay: what we learned

Notes from modding **DiPlay** (CarPlay head-unit app, package `com.shihab.diplay`,
code in `com.shilapi.xcertplay.*`) for a **BYD Qin L 2024**. Everything here was tested on
that car unless marked *untested*. The mods started on 0.2.21 (builds v1–v23) and moved to
**0.2.22** at **v24** (`versionCode 124`, `versionName 0.2.22-mod24`; the engine-water-temperature
gauge was dropped in the move).

## The car

| Item | Value |
|---|---|
| Head unit | BYD DiLink 3.0, Android 10 (API 29) |
| Firmware | `BYD-AUTO/DiLink3.0/DiLink3.0:10/QKQ1.210910.001/eng.build.20241210.184336` |
| Screen | `0:Built-in Screen 1920x1080` (the cluster is not an Android display) |
| Climate screen | `com.byd.airconditioning/.mainactivity.FullScreenMainActivity` (no launcher icon) |
| Accessibility settings page | `com.byd.systemsettings/.accessibility.AccessibilityMainActivity` (hidden in the UI) |

## Reaching the car: three routes

BYD's car API lives in the framework as `android.hardware.bydauto.*` (`BYDAutoAcDevice`,
`BYDAutoStatisticDevice`, `BYDAutoBodyworkDevice`, …). Call it by reflection; the classes exist only on BYD units.

1. **In-app with BYD's client classes.** `BYDAutoXxxDevice.getInstance(context)` checks permissions
   *on the Context you pass* (`checkCallingOrSelfPermission` / `enforce…`). Passing a
   `ContextWrapper` that answers "granted" (`PermissiveContext.java`) gets past that check.
   **Worked for the AC.** Did *not* work for `BYDAutoStatisticDevice` (see water temperature).
2. **Direct binder call from the ADB shell:** `service call autoservice <tx> i32 <device> i32 <featureId>`.
   `tx 5` = getInt, `tx 7` = getDouble. Reply is `Result: Parcel(00000000 <value> …)`.
   DiPlay reads speed/gear/battery this way. Known device numbers:
   `1005` energy, `1007` instrument, `1009`, `1011` gearbox, `1013` speed, `1014` statistic, `1016` tyres.
   Examples: speed `7 i32 1013 i32 -1807745016`, gear `5 i32 1011 i32 555745336`,
   cluster navi mode `5 i32 1007 i32 1086337074`.
3. **`app_process` as the shell user:** `CLASSPATH=<apk> app_process /system/bin <MainClass> args`
   with a Context from `ActivityThread.systemMain().getSystemContext().createPackageContext("com.android.shell", 0)`
   (`CarAcShell.java`). DiPlay itself uses this for ambient lights and other tools.
   Note: the shell user (uid 2000) does **not** hold `BYDAUTO_*` permissions either.

DiPlay talks to ADB on the head unit itself (`hud/BydAdbShell`: `new BydAdbShell(tag).run(ctx, cmd)`;
the user approves the ADB key once).

## Permissions

* `BYDAUTO_*_COMMON` are runtime ("dangerous") permissions. Declare them in the manifest and grant them over
  ADB: `pm grant <pkg> android.permission.BYDAUTO_AC_COMMON` → worked.
* `BYDAUTO_*_GET` / `*_SET` **cannot be granted** to a normal app (stay ✗ after `pm grant`).
* BYD returns **negative codes instead of throwing** when it refuses: `-10011` = refused.
  `[getInt] permission deny!` is the in-process SecurityException text.
* Diplus (`com.van.diplus`) requests 20 `BYDAUTO_*_COMMON` permissions at runtime and pre-grants
  `WRITE_SECURE_SETTINGS`, `READ_LOGS`, `ACCESS_BACKGROUND_LOCATION`, `PROJECT_MEDIA` over ADB.

## AC (works, via route 1 with `PermissiveContext`, fallback route 3)

Mirrors Diplus (`com.van.diplus.byd.c`, `cmd/f`). `area` is always 0.

| Action | Call |
|---|---|
| AC state | `getAcStartState()` → 1 = on |
| AC on (Auto) | `setAcControlMode(0, 0)` (Diplus has no plain "on"; Auto turns it on) |
| Manual | `setAcControlMode(0, 1)` |
| AC off | `stop(src)`; Diplus passes `BYDAutoFeatureIds$Setting.SET_RIGHT_LANE_LINE_Y_DISTANCE`, else 0 |
| Temperature | `getTemprature(1)` (driver), `getTemperatureUnit()`; `setAcTemperature(0, t, 0, unit)`; unit 0 → clamp 64–91, else 17–33 |
| Fan speed | `getAcWindLevel()`, `setAcWindLevel(0, 0..7)` |
| Recirculation | `getAcCycleMode()`; `setAcCycleMode(0, 1 inside / 0 outside)` |
| Fan only (ventilation) | `setAcVentilationState(0, 1/0)` |
| Airflow | `getAcWindMode()`, `setAcWindMode(0, m)`: 1 face, 2 face+feet, 3 feet, 4 feet+defrost, 5 defrost, 6 face+feet+defrost, 7 face+defrost |

## Steering-wheel and console keys

DiPlay's `WheelKeyService` is an AccessibilityService with `flagRequestFilterKeyEvents`. It sees the keys, it can
consume them, it is re-bound by the system after the car wakes, and it may start activities from the background.

Key codes (taken from Diplus `res/xml/keydown_preferences.xml`):

| Key | Code | Held (BYD sends a separate code) |
|---|---|---|
| Next / Previous | 87 / 88 | 302 / 303 |
| Mode | 289 | |
| Volume up / down | 291 / 292 | |
| Mute | 293 | |
| 360 camera | 294 | |
| Voice | 304 | 312 |
| Rotate screen | 305 | 306 |
| Call | 313 | |
| Power | 317 | |

* Consuming a key and replaying it with `input keyevent <code>` over ADB keeps a key's normal job working when only
  a double press is assigned (about 0.5 s delay on the single press).
* **Rotate screen still rotates even when consumed**: BYD acts on it below Android. Diplus *can* stop it.
* DiPlay switches its own wheel-key service off when none of its features "want" it
  (`WheelKeyService$Companion.wanted$common`); the mod makes configured car keys count.
* Diplus can also put on keys: windows, sunroof, seats (heat/vent/massage), lights, 360 views, sentry,
  drive modes, volume, apps… (~150 actions, list in `cmd/f.smali`). Avoid unlock/power-off/AEB-off on keys.

## Starting with the car

* BYD units **sleep and wake**; `BOOT_COMPLETED` is rarely sent ("Boot diagnostics received=false").
* Diplus listens to `QUICKBOOT_POWERON` + `BOOT_COMPLETED` and watches `SCREEN_ON` from a running service.
* The mod (`CarWake.java`) adds `QUICKBOOT_POWERON` and, from `WheelKeyService.onServiceConnected`, opens DiPlay
  when the screen comes on after ≥60 s off, or when the process has just started. *(Built, not yet confirmed.)*

## Cluster (dashboard) map

* DiLink 3 needs the **DiLink 3** setting, and "DiLink 4 cluster video via ADB" **off** (it blocks the native switch).
* The car only shows the map in the wheel's **Small / Full screen navi** modes.
* The map shrinks after reverse gear or switching cluster views because `DiLink3ClusterModeSession.apply()` sends
  the enlarge command once (`if (applied == mode) return`). *(Fix designed, not built.)*

## Things that did not work (don't retry blindly)

* **Engine water temperature (removed from the mod in v24):** the id exists (`BYDAutoFeatureIds.STATISTIC_WATER_TEMPERATURE = 2858`, device
  1014; Diplus reads it with `BYDAutoStatisticDevice.getWaterTemperature()`), but the car refused all three routes:
  in-app `[getInt] permission deny!`, `service call autoservice 5 i32 1014 i32 2858` → `-10011`,
  app_process → `-10011`, even after granting `BYDAUTO_STATISTIC_COMMON`. Not checked: whether it only reports
  with the engine running. How Diplus gets past this is unknown.
* Using `BOOT_COMPLETED` alone to auto-start.

## Wheel keys after the car wakes (root-cause work, 29 Oct)

Symptom: after the car has been off for a while the wheel keys are dead in DiPlay until it is force-stopped, while
Diplus's keys keep working.

Evidence from the report taken in the dead state (v26):
* `Wheel key service: wanted=true allowedInSettings=true bound=false lastRestore=attempt=6 adb=READY`.
* DiPlay's own restore loop logged "wheel key service allowed over adb" every ~11 s and `bound` never changed: it
  writes the value that is already in `enabled_accessibility_services`, and an unchanged write is a no-op, so the
  system never re-binds. (Only turning the service off and on again changes the setting.)
* The previous process (12:02) ended with "Activity destroyed" and the next process only started at 14:45; DiPlay has
  no service of its own keeping the process alive when CarPlay isn't connected, so it is a cached process that the
  car can kill during sleep. Process exit info needs API 30; the car is API 29.
* The BYD "App start management" (`com.byd.appstartmanagement/.frame.AppStartManagement`) and "Rapid mode" whitelist
  (`com.byd.rapidmode/.RapidModeActivity`) lists were already correct on the car, so they are not the (only) cause.
  Diplus tells its users to set both and to redo them after every update.

How Diplus differs: its accessibility service (`KDService`) and its foreground `MainService` are declared with
`android:process=":remote"`, i.e. the same, protected process; it pre-grants itself `WRITE_SECURE_SETTINGS` and writes
`enabled_accessibility_services` directly; it re-checks every 5 s (`com.van.diplus.service.w.d()`) and falls back to
`am force-stop` + `am start` over ADB.

v28 follows that design (`CarWake`, `CarGuard`, `CarKeepAliveService`):
* `CarKeepAliveService`: foreground service (notification) in the main process, started from `CarWake.watch()`;
  setting "Keep DiPlay running in the background", on by default.
* `WRITE_SECURE_SETTINGS` declared in the manifest and self-granted over ADB; the 5 s watchdog then toggles the
  service off and on in-process (`CarGuard.toggleAccessibility`), ADB as the fallback; v27's restart-after-wake and
  the manual "Refresh wheel keys" button remain.
* Evidence, kept across process deaths and appended to the report by a hook in `WheelKeyLog.report` ("Wheel keys:
  guard …" lines, also shown as "Recent events" in Car controls): when the previous process was last alive vs when
  this one started; the matching `am_kill`/`am_proc_died` lines from `logcat -b events` (who killed it and why);
  `dumpsys accessibility` lines about DiPlay before and after a repair (is it bound, enabled, binding, crashed).
*(Built, not yet confirmed in the car.)*

## CarPlay keeps disconnecting: causes found in reports

* "Small-window navi · separate positions" = **Auto**: every Small/Full navi switch reconnects CarPlay (by design),
  and the cluster flips Full→Small→Full at every start. Set it to Off (or On).
* Quick menu on **3 fingers**: BYD's three-finger swipe opens its AC panel, CarPlay goes to the background and the
  session ends. Use 4 fingers.

## DiPlay 0.2.22 (developer release) adds

Dashboard map shape half/full (re-applied whenever the map appears), `ClusterProjectionWatchdog` (re-asserts the
cluster projection, likely the fix for the map shrinking after reverse), lane guidance, navigation prompts
taking audio focus, calls at their own audio rate, connection-failure causes with fixes, album-colour
speedometer background, auto-activated cluster music card, HEVC video, custom size, Geely support.

## Verifying a build without a car or emulator

Windows 10 can't run the Android emulator under WSL2 (nested virtualization is Windows 11 only), so builds are
checked statically instead: `tools/verify.sh <apk> <tools-dir>` (run automatically at the end of `tools/build.sh`;
`tools/fetch-tools.sh <tools-dir>` downloads its jars, retrying on Maven's HTTP 429).

`tools/verifier/Verify.java` uses dexlib2 (`org.smali:dexlib2:2.5.2`) to infer the type of every register at every
instruction, then applies the rules ART's verifier enforces: no reading a register that is unset or conflicted;
object vs number in invoke arguments, receivers, field get/put, returns, array ops and arithmetic. dexlib2 on its own
never rejects anything: a first version that only asked it for analysis errors reported "0 findings" on APKs with
planted faults, which is why the strict rules were added.

Validation that it works: the original 0.2.22 (185,865 methods) gives 0 findings; two planted faults (an int used as a
Context, and an int/object merge conflict) are caught; and the old crashing builds v7/v8/v9 give 10 findings in
`CarPlayHostActivity.buildSettingsMenu` ("v5 is PosByte, argument String … wrong kind", the exact cause of the
first crash) while v10 and later give 0.

It does **not** check behaviour (logic, permissions, the car's responses), only register/type safety of the dex.
Java helpers are already type-checked by javac. An emulator (Windows 11 + WSL2, or the Android Studio emulator on
Windows) would add install/launch tests; the car is still needed for anything BYD-specific.

## Modding lessons

* **apktool does not verify smali.** (`tools/verify.sh` now does, see above.) Reusing a register as int and object across a branch merge, or overwriting a
  register the original code reads later, assembles fine and then crashes at runtime with
  `VerifyError: Verifier rejected class …`. The first crash-on-connect was exactly this in
  `CarPlayHostActivity.buildSettingsMenu`. Keep patches to single `invoke-static` calls into helper classes and diff
  against the pristine decompile.
* Write new logic in **Java** (`java-src/`), compile against stubs plus `android.jar`, convert with `dx`, and add it as
  `classes5.dex`. Far safer than hand-written smali.
* Private methods in `DiPlayActivity` are reached through small public static bridges added to its smali
  (`diplayButton`, `diplayNote`, `diplayTitle`). `toggle$default` / `choice$default` / `section$default` are
  package-private statics and can be called directly from the same package.
* Use DiPlay's own widgets (`toggle`, `choice`, `OverlaySliderRow`, `SettingsWidgets.createSwitchRow` with
  `SettingsTheme.OVERLAY`) so new rows match the app's font and style.
* Settings builders also run while the search index is built, so keep them free of side effects.
* Every build is signed with uber-apk-signer's embedded debug key (cert SHA-256 `1e08a903…5953`), so each build
  installs over the previous one. Raise `versionCode` every time. Only the first switch from the developer's
  original needs an uninstall.
* **Check every patch hunk's placement when porting to a new version.** `patch` with fuzz put the Audio-tab
  block of `CarPlayHostActivity` into a *different method* 24,000 lines away (0.2.22 renumbered registers).
  Re-apply such hunks by hand, using registers you've confirmed are rewritten before their next read.
  The manifest hunk was also skipped quietly.
* `ClusterSpeedometerView.onDraw` measured "km/h" with a hard-coded length of 4; any other unit text must use
  `length()`.

## Files here

* `smali-patches/diplay-0.2.22-mods.diff`: every smali/manifest change against the original DiPlay 0.2.22 APK.
* `java-src/src`: the helper classes (car keys, AC, gauge, wake, audio reset, tab order).
  `java-src/stub` holds compile-time stubs only.
* `tools/build.sh`: rebuilds the modded APK from the original and runs `tools/verify.sh` as a gate (`tools/fetch-tools.sh` gets the jars). Tested on 0.2.22: applies with no offset or fuzz,
  and the result has the same size as v24 (19,278,895 bytes).
