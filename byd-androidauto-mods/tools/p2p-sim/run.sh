#!/usr/bin/env bash
# Desktop test of CarP2p (channel choice, recreate triggers) against the car log's sequence, with fakes.
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd); SRC="$HERE/../../java-src/src/com/andrerinas/openheadunit/byd"; OUT=$(mktemp -d)
javac -nowarn -d "$OUT" $(find "$HERE/fake" -name '*.java') "$SRC/CarP2p.java" "$SRC/AapGuard.java" "$HERE"/*.java
java -cp "$OUT" P2pSim
