#!/usr/bin/env python3
"""Convenience launcher: `python3 main.py ...` is the same as `python3 sdc.py ...`.

The product itself is the single file sdc.py; this shim exists only so people
(and tooling) that reach for a conventional entry point still land in the CLI.
"""

from __future__ import annotations

import sys

from sdc import main

if __name__ == "__main__":
    sys.exit(main())
