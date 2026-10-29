#!/usr/bin/env bash
# Register-type check of every method in an APK: the class of bug that crashed the first mod with
# "VerifyError: Verifier rejected class". Exit code 1 if anything is found.
# Usage: tools/verify.sh <apk> <tools-dir>
set -euo pipefail
APK=$1; T=$2
HERE=$(cd "$(dirname "$0")" && pwd)
W=$(mktemp -d)
CP="$T/smali/dexlib2-2.5.2.jar:$T/smali/guava-33.0.0-jre.jar:$T/smali/util-2.5.2.jar:$T/smali/jsr305-3.0.2.jar:$T/smali/failureaccess-1.0.2.jar"
javac -nowarn --release 11 -cp "$CP" -d "$W" "$HERE/verifier/Verify.java" 2>&1 | grep -v "^Picked\|^Note" || true
java -cp "$T/dalvik-dx.jar" com.android.dx.command.Main --dex --core-library --output="$W/android-stub.dex" "$T/android.jar" 2>&1 | grep -v Picked || true
java -cp "$W:$CP" Verify "$APK" "$W/android-stub.dex" "$W/findings.txt" 2>&1 | grep -v Picked
if [ -s "$W/findings.txt" ]; then
  echo "VERIFY FAILED:"; cut -c1-300 "$W/findings.txt" | head -40; exit 1
fi
echo "VERIFY OK"
