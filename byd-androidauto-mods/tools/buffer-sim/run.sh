#!/usr/bin/env bash
# Desktop simulation of AvBuffer against the car log's arrival pattern (fake AudioTrack/MediaCodec).
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd); OUT=$(mktemp -d)
javac -nowarn -d "$OUT" $(find "$HERE/fake" -name '*.java') "$HERE/../../java-src/src/com/andrerinas/openheadunit/byd/AvBuffer.java" "$HERE/Sim.java"
java -cp "$OUT" Sim
