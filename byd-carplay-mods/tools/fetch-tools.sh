#!/usr/bin/env bash
# Downloads the helper jars used by build.sh and verify.sh into <tools-dir>.
# Needs only curl and java. apktool.jar, uber-apk-signer.jar and an android.jar (API 16 stubs are enough)
# must already be in <tools-dir>; the rest comes from Maven Central.
set -euo pipefail
T=${1:?usage: fetch-tools.sh <tools-dir>}
mkdir -p "$T/smali"
M=https://repo1.maven.org/maven2
get() {
  [ -s "$2" ] && return 0
  for wait in 2 8 20 45 90; do          # Maven Central answers 429 when asked too fast
    sleep "$wait"
    curl -sSfL -o "$2" "$M/$1" && return 0
    rm -f "$2"
  done
  echo "could not download $1" >&2; return 1
}
get com/jakewharton/android/repackaged/dalvik-dx/9.0.0_r3/dalvik-dx-9.0.0_r3.jar "$T/dalvik-dx.jar"
get com/google/android/android/4.1.1.4/android-4.1.1.4.jar "$T/android.jar"
get org/smali/dexlib2/2.5.2/dexlib2-2.5.2.jar "$T/smali/dexlib2-2.5.2.jar"
get org/smali/util/2.5.2/util-2.5.2.jar "$T/smali/util-2.5.2.jar"
get com/google/guava/guava/33.0.0-jre/guava-33.0.0-jre.jar "$T/smali/guava-33.0.0-jre.jar"
get com/google/guava/failureaccess/1.0.2/failureaccess-1.0.2.jar "$T/smali/failureaccess-1.0.2.jar"
get com/google/code/findbugs/jsr305/3.0.2/jsr305-3.0.2.jar "$T/smali/jsr305-3.0.2.jar"
echo "tools ready in $T"
