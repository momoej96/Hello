#!/usr/bin/env bash
# Rebuilds the modded DiPlay APK from the original DiPlay-0.2.22.apk.
# Needs: Java 17+, apktool 2.10.0, uber-apk-signer 1.3.0, dalvik-dx 9.0.0_r3,
#        and an API-level android.jar for compiling (any 4.1+ works; only standard APIs are used).
# Usage: tools/build.sh <DiPlay-0.2.22.apk> <tools-dir> <out.apk> [versionCode] [versionName]
set -euo pipefail
APK=$1; TOOLS=$2; OUT=$3; VCODE=${4:-200}; VNAME=${5:-0.2.22-mod}
HERE=$(cd "$(dirname "$0")/.." && pwd)
WORK=$(mktemp -d)

# 1) Decompile and apply the smali/manifest changes.
java -jar "$TOOLS/apktool.jar" d -f -o "$WORK/project" "$APK"
patch -p1 -d "$WORK/project" < "$HERE/smali-patches/diplay-0.2.22-mods.diff"
sed -i "s/versionCode: .*/versionCode: $VCODE/; s/versionName: .*/versionName: $VNAME/" "$WORK/project/apktool.yml"

# 2) Compile the Java helpers (stubs are compile-time only) and convert to dex.
mkdir -p "$WORK/stubout" "$WORK/out"
javac -nowarn --release 8 -cp "$TOOLS/android.jar" -d "$WORK/stubout" $(find "$HERE/java-src/stub" -name '*.java')
javac -nowarn --release 8 -cp "$TOOLS/android.jar:$WORK/stubout" -d "$WORK/out" $(find "$HERE/java-src/src" -name '*.java')
java -cp "$TOOLS/dalvik-dx.jar" com.android.dx.command.Main --dex --min-sdk-version=26 \
    --output="$WORK/classes5.dex" "$WORK/out"

# 3) Rebuild, add the helpers as an extra dex, sign (same embedded debug key every time,
#    so each build installs over the previous one).
java -jar "$TOOLS/apktool.jar" b "$WORK/project" -o "$WORK/unsigned.apk"
(cd "$WORK" && zip -q unsigned.apk classes5.dex)
java -jar "$TOOLS/uber-apk-signer.jar" -a "$WORK/unsigned.apk" -o "$WORK/signed"
cp "$WORK"/signed/*.apk "$OUT"
echo "Built $OUT"
