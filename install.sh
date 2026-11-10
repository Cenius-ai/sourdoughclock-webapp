#!/usr/bin/env bash
#
# SourDoughClock installer - installs the (test-only) dependency, verifies the
# module imports, and EXITS. It never starts anything long-running.
#
# Safe to re-run. No sudo, no system packages: everything goes through pip.
#
set -euo pipefail
cd "$(dirname "$0")"

PYTHON="${PYTHON:-python3}"

if ! command -v "$PYTHON" >/dev/null 2>&1; then
    echo "error: '$PYTHON' was not found. Install Python 3.9+ and re-run." >&2
    exit 1
fi

if ! "$PYTHON" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 9) else 1)'; then
    echo "error: SourDoughClock needs Python 3.9 or newer ($("$PYTHON" --version 2>&1))." >&2
    exit 1
fi

echo "==> 1/3 Upgrading pip, setuptools and wheel"
"$PYTHON" -m pip install --upgrade pip setuptools wheel

echo "==> 2/3 Installing project dependencies from requirements.txt"
"$PYTHON" -m pip install -r requirements.txt

echo "==> 3/3 Import self-check"
"$PYTHON" -c 'import sdc; print(f"sdc {sdc.__version__} imports cleanly from {sdc.__file__}")'
"$PYTHON" sdc.py --version

# The optional `sdc` console command is a convenience: sdc.py itself needs no
# packaging step. A read-only or externally managed Python install must not
# break the installer, so this step warns instead of failing.
if "$PYTHON" -m pip install --no-build-isolation -e . >/dev/null 2>&1; then
    echo "==> Optional: the 'sdc' console command is installed (try: sdc --help)"
else
    echo "==> Optional: skipped the 'sdc' console command; use: python3 sdc.py --help" >&2
fi

cat <<'DONE'
Install complete.

  Try the tool:   python3 sdc.py --help
  Full demo:      bash demo.sh
  Run the tests:  python3 -m pytest
DONE
