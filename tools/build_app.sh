#!/bin/bash
# STAND-IN, written by the pipeline lane so tools/build_dmg.sh can run end to
# end before the UI lane lands its real version. It keeps the contract:
#
#   tools/build_app.sh OUT_DIR -> OUT_DIR/Dictator
#
# the app executable, from every native/app/*.swift, arm64. The real one may
# grow flags or frameworks for SwiftUI; the output path is what must not move.
set -euo pipefail

OUT="${1:?usage: build_app.sh OUT_DIR}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

mkdir -p "$OUT"
echo "  swiftc native/app/*.swift -> Dictator"
swiftc -O -target arm64-apple-macos14.0 "$ROOT"/native/app/*.swift -o "$OUT/Dictator"
