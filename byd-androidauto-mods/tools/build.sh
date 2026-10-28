#!/usr/bin/env bash
# Rebuilds the modded DiAuto APK from the original DiAuto-v0.3.12.apk.
# Needs: Java 17+, apktool 2.10.0, uber-apk-signer 1.3.0, dalvik-dx 9.0.0_r3,
#        and an android.jar for compiling (4.1+; the newer APIs used come from java-src/stub).
# Usage: tools/build.sh <DiAuto-v0.3.12.apk> <tools-dir> <out.apk> [versionCode] [versionName]
set -euo pipefail
APK=$1; TOOLS=$2; OUT=$3; VCODE=${4:-1001}; VNAME=${5:-0.3.12-mod1}
HERE=$(cd "$(dirname "$0")/.." && pwd)
WORK=$(mktemp -d)

# 1) Decompile and apply the smali/manifest/resource changes.
java -jar "$TOOLS/apktool.jar" d -f -o "$WORK/project" "$APK"
patch -p1 -d "$WORK/project" < "$HERE/smali-patches/diauto-0.3.12-mods.diff"
sed -i "s/versionCode: .*/versionCode: $VCODE/; s/versionName: .*/versionName: $VNAME/" "$WORK/project/apktool.yml"

# 2) Compile the Java helpers (stubs are compile-time only) and convert to dex.
mkdir -p "$WORK/stubout" "$WORK/out"
javac -nowarn --release 8 -cp "$TOOLS/android.jar" -d "$WORK/stubout" $(find "$HERE/java-src/stub" -name '*.java')
javac -nowarn --release 8 -cp "$WORK/stubout:$TOOLS/android.jar" -d "$WORK/out" $(find "$HERE/java-src/src" -name '*.java')
java -cp "$TOOLS/dalvik-dx.jar" com.android.dx.command.Main --dex --min-sdk-version=26 \
    --output="$WORK/classes3.dex" "$WORK/out"

# 3) Rebuild, add the helpers as an extra dex (DiAuto has classes.dex + classes2.dex), sign with
#    uber-apk-signer's embedded debug key (same key as the DiPlay mod, so updates install over).
java -jar "$TOOLS/apktool.jar" b "$WORK/project" -o "$WORK/unsigned.apk"
(cd "$WORK" && zip -q -0 unsigned.apk classes3.dex)
java -jar "$TOOLS/uber-apk-signer.jar" -a "$WORK/unsigned.apk" -o "$WORK/signed"
cp "$WORK"/signed/*.apk "$OUT"
echo "Built $OUT"
