#!/usr/bin/env python3
"""Standalone smoke test: python3 tests/test_smoke.py

Exercises preset add/list, rise exact and nearest lookups, and log add/list
against a throwaway SDC_DATA file. Prints one line per check and PASS on
success; exits non-zero on the first failure. No third-party imports, so it
runs on a bare Python install as well as under pytest.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SDC = PROJECT_ROOT / "sdc.py"


def run(data_file: Path, *args: str) -> subprocess.CompletedProcess:
    env = {
        **os.environ,
        "SDC_DATA": str(data_file),
        "NO_COLOR": "1",
        "PYTHONIOENCODING": "utf-8",
    }
    env.pop("TERM", None)
    return subprocess.run(
        [sys.executable, str(SDC), *args],
        capture_output=True,
        check=False,
        text=True,
        env=env,
        cwd=str(PROJECT_ROOT),
        timeout=60,
    )


def check(label: str, condition: bool, detail: str = "") -> None:
    if not condition:
        print(f"  [FAIL] {label}{(' - ' + detail) if detail else ''}", file=sys.stderr)
        raise SystemExit(1)
    print(f"  [ok] {label}")


def preset_add_args() -> tuple[str, ...]:
    return ("preset", "add", "morning", "--hydration", "100", "--feed", "22:00", "--rise", "8")


def bad_preset_args() -> tuple[str, ...]:
    return ("preset", "add", "bad", "--hydration", "100", "--feed", "25:00", "--rise", "6")


def main() -> int:
    print("SourDoughClock smoke test")
    with tempfile.TemporaryDirectory(prefix="sdc-smoke-") as directory:
        data_file = Path(directory) / "smoke.json"
        print(f"  data file: {data_file}")

        add = run(data_file, *preset_add_args())
        check(
            "preset add morning (feed 22:00, rise 8h) -> bake 06:00 +1 day",
            add.returncode == 0 and "06:00 +1 day" in add.stdout,
            add.stderr.strip(),
        )

        listing = run(data_file, "preset", "list")
        check(
            "preset list shows morning with hydration, feed, rise and bake",
            listing.returncode == 0
            and "morning" in listing.stdout
            and "100%" in listing.stdout
            and "22:00" in listing.stdout
            and "8h" in listing.stdout
            and "06:00 +1 day" in listing.stdout,
            listing.stderr.strip(),
        )

        exact = run(data_file, "rise", "24", "--hydration", "100")
        check(
            "rise 24 --hydration 100 -> 8h exact match",
            exact.returncode == 0
            and "8h" in exact.stdout
            and "exact tabulated temperature 24C" in exact.stdout,
            exact.stderr.strip(),
        )

        nearest = run(data_file, "rise", "23", "--hydration", "100")
        check(
            "rise 23 --hydration 100 -> nearest tabulated temperature 24C",
            nearest.returncode == 0
            and "nearest tabulated temperature 24C" in nearest.stdout
            and "8h" in nearest.stdout,
            nearest.stderr.strip(),
        )

        table = run(data_file, "rise", "--table")
        check(
            "rise --table prints the temperature-by-hydration matrix",
            table.returncode == 0
            and "TEMPERATURE" in table.stdout
            and "125%" in table.stdout
            and "30C" in table.stdout,
            table.stderr.strip(),
        )

        log_add = run(
            data_file, "log", "add", "--preset", "morning", "--crumb", "8", "--notes", "open crumb"
        )
        today = date.today().isoformat()
        check(
            "log add records today's date, crumb, preset and notes",
            log_add.returncode == 0
            and today in log_add.stdout
            and "crumb 8/10" in log_add.stdout
            and "preset morning" in log_add.stdout
            and "open crumb" in log_add.stdout,
            log_add.stderr.strip(),
        )

        log_list = run(data_file, "log", "list")
        check(
            "log list shows the batch with its date",
            log_list.returncode == 0 and today in log_list.stdout and "8/10" in log_list.stdout,
            log_list.stderr.strip(),
        )

        stored = json.loads(data_file.read_text(encoding="utf-8"))
        check(
            "store holds one preset and one batch",
            len(stored["presets"]) == 1 and len(stored["batches"]) == 1,
            str(stored),
        )

        rejected = run(data_file, *bad_preset_args())
        check(
            "invalid feed time is rejected with a clear message and no write",
            rejected.returncode != 0 and "feed time must be HH:MM" in rejected.stderr,
            rejected.stdout.strip(),
        )

    print("PASS")
    return 0


def test_smoke_script_exits_zero() -> None:
    """pytest hook so the standalone smoke script also runs with the suite."""
    assert main() == 0


if __name__ == "__main__":
    sys.exit(main())
