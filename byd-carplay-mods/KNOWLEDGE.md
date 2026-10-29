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

## Wheel keys after the car wakes

After switching the car off and on, DiPlay could show "Wheel key service: allowed, starting…" (report:
`allowedInSettings=true bound=false lastRestore=attempt=2`): enabled in settings, but the system doesn't bind it
again until DiPlay is force-stopped and reopened. Auto-start (`CarWake`) runs from that service, so it stopped too.

Diplus solves the same problem with a **watchdog every 5 s** in its always-running `MainService`
(`com.van.diplus.service.w.d()`): if its service isn't bound, it first adds itself to
`enabled_accessibility_services`, and if it's still not bound 5 s later it runs
`am force-stop com.van.diplus; am start -n com.van.diplus/.activity.StartMainServiceActivity` over ADB.

v26 copies that (`CarWake.watch`), started from every entry point (both activities' `onCreate`, `BootReceiver`,
`PhoneBluetoothReceiver`, `WheelKeyService.onServiceConnected`): stuck ~10 s → re-toggle the service in settings
over ADB; still stuck ~10 s later → `setsid sh -c 'am force-stop …; am start …'` over ADB, at most once per 10 min.
An ADB call with no answer (ADB not ready right after a wake) is retried on the next tick. On car Bluetooth it also
opens DiPlay when CarPlay isn't running. The outcome shows as "Last car start: …" in Car controls.
*(Built, not yet confirmed.)*

**User finding (28 Oct):** switching the car off and on again within ~1 minute leaves the wheel keys dead —
in DiPlay *and* in Diplus — until the car is off long enough for Bluetooth to disconnect; after that everything
works. So it's the head unit coming back from a half-sleep, not the app. In that state the service may look bound
while key events don't arrive, which the v26 watchdog can't see (confirmed 29 Oct: keys still sometimes dead with
v26, force stop fixes them).

v27 therefore restarts DiPlay once after every car wake when its process lived through the sleep (setting
"Restart DiPlay after the car wakes", on by default). Wake = screen on after ≥10 s off, or the watchdog's real clock
jumping >20 s between 5 s ticks (the handler clock stops in sleep). A process that started after the wake is left
alone; ADB not answering is retried for 90 s; at most one wake restart per 2 min. Car controls also has a manual
"Refresh wheel keys" button. *(Built, not yet confirmed.)*
Also reported: DiPlay's start-at-boot permission seemed lost after several updates (where exactly: not yet known);
idea: re-apply the boot exemptions (`cmd deviceidle whitelist +pkg`, appops `RUN_IN_BACKGROUND`) over ADB after
each update.

## Diplus key commands (for reference)

The command box takes Chinese command names only (`空调自动`, `关空调`, `内循环`, …), `,` runs commands in sequence
and `/` separates successive presses. `打开应用<label or package>` opens only apps with a launcher entry;
`打开应用pkg/activity` would run `am start -n` but can't be used from a key because of the `/` rule, so BYD's
climate screen (no launcher entry) can't be opened from a Diplus key. Other types: `延迟`, `播报`, `TOAST:`,
`HTTPGET:`, `HTTPPOST:`.

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

## Modding lessons

* **apktool does not verify smali.** Reusing a register as int and object across a branch merge, or overwriting a
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
* `tools/build.sh`: rebuilds the modded APK from the original. Tested on 0.2.22: applies with no offset or fuzz,
  and the result has the same size as v24 (19,278,895 bytes).
