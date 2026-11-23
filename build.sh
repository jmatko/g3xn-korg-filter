#!/usr/bin/env bash
# build.sh — build the Traveler ZD2 effect (G3Xn + MS Plus variants).
#
# Prerequisites (see README "Toolchain"):
#   1. The stomphacks toolchain cloned to ./stomphacks (git clone
#      https://github.com/thammer/stomphacks stomphacks && cd stomphacks &&
#      python3 -m venv .venv && .venv/bin/pip install -r requirements.txt)
#   2. The TI C6000 compiler. On Linux, an i386 build works. Set ZOOM_TI_CGT
#      to its directory (it must contain bin/cl6x and include/).
#
# Usage:
#   ./build.sh            # build both G3Xn and MS Plus variants into files/
#   ZOOM_TI_CGT=/path/to/ti-cgt-c6000 ./build.sh
#
# The build writes the effect into stomphacks/effects/traveler/ (the kernel +
# manifests are copied there first), then copies the results into files/.

set -euo pipefail

REPO="$(cd "$(dirname "$0")" && pwd)"
SH="$REPO/stomphacks"
FX="$SH/effects/traveler"

if [ ! -d "$SH" ]; then
  echo "error: ./stomphacks not found. Clone it first (see README)." >&2
  exit 1
fi
if [ -z "${ZOOM_TI_CGT:-}" ]; then
  echo "error: ZOOM_TI_CGT is not set. Point it at the TI C6000 compiler dir." >&2
  exit 1
fi
if [ ! -x "$ZOOM_TI_CGT/bin/cl6x" ]; then
  echo "error: $ZOOM_TI_CGT/bin/cl6x not found (is ZOOM_TI_CGT correct?)" >&2
  exit 1
fi

# Copy the effect source into the toolchain's effects dir.
mkdir -p "$FX"
cp "$REPO/effect/traveler.c"            "$FX/traveler.c"
cp "$REPO/effect/manifest.g3xn.json"    "$FX/manifest.g3xn.json"
cp "$REPO/effect/manifest.msplus.json"  "$FX/manifest.json"

PY="$SH/.venv/bin/python3"
[ -x "$PY" ] || PY=python3

echo "=== building MS Plus variant (manifest.json) ==="
( cd "$SH" && ZOOM_TI_CGT="$ZOOM_TI_CGT" "$PY" tools/zd2_make_effect.py effects/traveler/manifest.json )
cp "$FX/build/XXTRVL.ZD2" "$REPO/files/XXTRVL_msplus.ZD2"
cp "$FX/build/XXTRVL.ZIC" "$REPO/files/XXTRVL.ZIC"

echo "=== building G3Xn variant (manifest.g3xn.json) ==="
( cd "$SH" && ZOOM_TI_CGT="$ZOOM_TI_CGT" "$PY" tools/zd2_make_effect.py effects/traveler/manifest.g3xn.json )
cp "$FX/build/XXTRVL.ZD2" "$REPO/files/XXTRVL_g3xn_raw.ZD2"
cp "$FX/build/XXTRVL.ZIC" "$REPO/files/XXTRVL.ZIC"

echo "=== setting G3Xn target bit (0x91 = MS Plus | g-series) ==="
python3 "$REPO/tools/set_target.py" "$REPO/files/XXTRVL_g3xn_raw.ZD2" "$REPO/files/XXTRVL_g3xn.ZD2" 0x91
rm -f "$REPO/files/XXTRVL_g3xn_raw.ZD2"

echo ""
echo "Done. Files in $REPO/files/ :"
ls -la "$REPO/files/"
echo ""
echo "NOTE: the G3Xn target bit (0x91) is a best-guess. Verify it against a"
echo "stock G3Xn ZD2 with:  python3 tools/g3xn_inspect.py LOWPASSF.ZD2"