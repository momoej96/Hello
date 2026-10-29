#!/usr/bin/env bash
# Desktop test of LocalHotspot (car's local-only network) with a fake car radio, plus a port of
# DiAuto's access-point resolver checked against the interfaces the car reported.
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd); SRC="$HERE/../../java-src/src/com/andrerinas/openheadunit/byd"; OUT=$(mktemp -d)
javac -nowarn -d "$OUT" $(find "$HERE/fake" -name '*.java') "$SRC/LocalHotspot.java" "$HERE/LohsSim.java" "$HERE/ResolverPort.java"
for part in A B C; do java -cp "$OUT" LohsSim "$part"; done
java -cp "$OUT" ResolverPort
