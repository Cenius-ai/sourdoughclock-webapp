"""Shared pytest fixtures for the SourDoughClock suite.

Every test drives the real CLI through a subprocess with SDC_DATA pointed at a
temporary file, so the assertions cover exactly what a user gets: argv in,
stdout/stderr/exit code out, JSON store on disk.
"""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent


@dataclass
class SdcRunner:
    """Invoke sdc.py against an isolated data file."""

    data_file: Path
    root: Path = field(default=PROJECT_ROOT)

    def run(self, *args: str, data_file: Path | None = None, env_extra: dict | None = None):
        env = dict(os.environ)
        env["NO_COLOR"] = "1"
        env.pop("TERM", None)
        env["PYTHONIOENCODING"] = "utf-8"
        env["SDC_DATA"] = str(data_file if data_file is not None else self.data_file)
        if env_extra:
            env.update(env_extra)
        return subprocess.run(
            [sys.executable, str(self.root / "sdc.py"), *args],
            capture_output=True,
            check=False,
            text=True,
            env=env,
            cwd=str(self.root),
            timeout=60,
        )


@pytest.fixture()
def cli(tmp_path: Path) -> SdcRunner:
    return SdcRunner(data_file=tmp_path / "store.json")
