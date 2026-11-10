#!/usr/bin/env python3
"""SourDoughClock - feed-to-bake presets, rise estimates and a crumb-score batch log.

A single-file, standard-library-only CLI for home sourdough bakers:

  sdc preset add NAME --hydration PCT --feed HH:MM --rise HOURS
  sdc preset list
  sdc rise TEMP --hydration PCT [--table]
  sdc log add --crumb 1-10 [--preset NAME] [--notes TEXT]
  sdc log list

State lives in one human-readable JSON document at ~/.sourdoughclock.json;
set SDC_DATA to point at a different file. Fully offline: no network calls.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
import tempfile
from dataclasses import dataclass
from datetime import date
from pathlib import Path

__version__ = "1.0.0"

# --------------------------------------------------------------------------- #
# Design tokens - committed direction: calm-precise, terminal dark, mono,
# compact, aligned columns, one accent for primary status, and no colour-only
# signal (every accented value also carries a text label).
# --------------------------------------------------------------------------- #
THEME = {
    "accent_hex": "#b55e42",
    "accent_oklch": "oklch(0.58 0.12 39)",
    "accent_rgb": (181, 94, 66),
    "surface": "terminal-dark",
    "type": "mono",
    "density": "compact",
    "rule": {"horizontal": "\u2500", "vertical": "\u2502", "cross": "\u253c"},
    "neutral": {"muted": 2, "strong": 1},
}

TABLE_RULE = THEME["rule"]
ACCENT_HEX = THEME["accent_hex"]
ACCENT_RGB = THEME["accent_rgb"]

# --------------------------------------------------------------------------- #
# Domain constants
# --------------------------------------------------------------------------- #
DATA_ENV_VAR = "SDC_DATA"
DEFAULT_DATA_NAME = ".sourdoughclock.json"
SCHEMA_VERSION = 1

HYDRATION_MIN, HYDRATION_MAX = 50, 150
RISE_MIN, RISE_MAX = 1, 48
CRUMB_MIN, CRUMB_MAX = 1, 10
NOTE_WIDTH = 64

EXIT_OK = 0
EXIT_DATA = 1
EXIT_USAGE = 2

# Built-in rise matrix: hours to a bake-ready rise at a 20% inoculation.
RISE_TEMPERATURES = (18, 21, 24, 27, 30)
RISE_HYDRATIONS = (60, 75, 100, 125)
RISE_MATRIX = {
    18: {60: 20.0, 75: 18.0, 100: 16.0, 125: 14.5},
    21: {60: 16.0, 75: 14.0, 100: 12.0, 125: 10.5},
    24: {60: 12.0, 75: 10.0, 100: 8.0, 125: 7.0},
    27: {60: 9.0, 75: 7.5, 100: 6.0, 125: 5.0},
    30: {60: 7.0, 75: 6.0, 100: 4.5, 125: 3.5},
}

TIME_RE = re.compile(r"^(?P<hour>\d{1,2}):(?P<minute>\d{2})$")

DESCRIPTION = (
    "SourDoughClock: feed-to-bake presets per starter hydration, a "
    "temperature-adjusted rise table, and a dated batch log with crumb scores."
)

EXAMPLES = """examples:
  sdc preset add morning --hydration 100 --feed 22:00 --rise 8
  sdc preset add rye-sunday --hydration 75 --feed 07:30 --rise 4.5
  sdc preset list
  sdc rise 24 --hydration 100
  sdc rise 23 --hydration 80
  sdc rise --table
  sdc log add --preset morning --crumb 8 --notes 'open crumb, 4h bulk'
  sdc log list

data:
  Presets and batches live in ~/.sourdoughclock.json.
  Set SDC_DATA=/path/to/file.json to use a different file (demos, tests).

exit codes:
  0 success - 1 data-file problem - 2 invalid input
"""


# --------------------------------------------------------------------------- #
# Errors
# --------------------------------------------------------------------------- #
class SdcError(Exception):
    """An expected, user-facing failure. The message is printed to stderr."""

    exit_code = EXIT_DATA


class UsageError(SdcError):
    """Bad input from the user: missing value, out-of-range value, bad format."""

    exit_code = EXIT_USAGE


class DataFileError(SdcError):
    """The JSON store could not be read or written."""

    exit_code = EXIT_DATA


# --------------------------------------------------------------------------- #
# Terminal styling (auto-off for pipes, honouring NO_COLOR)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Style:
    enabled: bool

    def _wrap(self, text: str, sgr: str) -> str:
        return f"\x1b[{sgr}m{text}\x1b[0m" if self.enabled else text

    def accent(self, text: str) -> str:
        """The one committed accent, used only for the primary status value."""
        red, green, blue = ACCENT_RGB
        return self._wrap(text, f"38;2;{red};{green};{blue}")

    def dim(self, text: str) -> str:
        return self._wrap(text, str(THEME["neutral"]["muted"]))


def color_enabled(stream: object, disabled: bool) -> bool:
    """Colour only when a human is watching and nothing asked for plain text."""
    if disabled or os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("TERM", "") == "dumb":
        return False
    return bool(getattr(stream, "isatty", lambda: False)())


# --------------------------------------------------------------------------- #
# Aligned-column table rendering
# --------------------------------------------------------------------------- #
LEFT = "left"
RIGHT = "right"


def render_table(
    style: Style,
    headers: list[str],
    rows: list[list[str]],
    aligns: list[str],
    accents: frozenset = frozenset(),
) -> str:
    """Render aligned columns separated by box-drawing rules.

    ``accents`` holds (row index, column index) pairs painted with the single
    accent colour; each such cell also carries a text label, so nothing is
    signalled by colour alone.
    """
    widths = [len(header) for header in headers]
    for row in rows:
        for index, cell in enumerate(row):
            widths[index] = max(widths[index], len(cell))

    def format_row(cells: list[str], accent_row: int | None) -> str:
        parts = []
        for index, cell in enumerate(cells):
            if aligns[index] == RIGHT:
                padded = cell.rjust(widths[index])
            else:
                padded = cell.ljust(widths[index])
            if accent_row is not None and (accent_row, index) in accents:
                padded = style.accent(padded)
            parts.append(padded)
        return f" {TABLE_RULE['vertical']} ".join(parts).rstrip()

    separator = f"{TABLE_RULE['horizontal']}{TABLE_RULE['cross']}{TABLE_RULE['horizontal']}".join(
        TABLE_RULE["horizontal"] * width for width in widths
    )
    lines = [format_row(headers, None), separator]
    lines.extend(format_row(row, index) for index, row in enumerate(rows))
    return "\n".join(lines)


def truncate(text: str, width: int) -> str:
    collapsed = " ".join(text.split())
    if len(collapsed) <= width:
        return collapsed
    return collapsed[: width - 1] + "\u2026"


# --------------------------------------------------------------------------- #
# Small value helpers
# --------------------------------------------------------------------------- #
def format_hours(value: float) -> str:
    if abs(value - round(value)) < 1e-9:
        return f"{round(value)}h"
    return f"{value:g}h"


def format_temp(value: float) -> str:
    if abs(value - round(value)) < 1e-9:
        return f"{round(value)}C"
    return f"{value:g}C"


def split_feed_time(text: object) -> tuple[int, int] | None:
    """Parse a stored HH:MM feed time; None when the stored value is unusable."""
    if not isinstance(text, str):
        return None
    match = TIME_RE.match(text.strip())
    if match is None:
        return None
    hour, minute = int(match.group("hour")), int(match.group("minute"))
    if hour > 23 or minute > 59:
        return None
    return hour, minute


def parse_feed_time(raw: str) -> tuple[int, int]:
    parsed = split_feed_time(raw)
    if parsed is None:
        raise UsageError(
            f"feed time must be HH:MM between 00:00 and 23:59 (got {str(raw).strip()!r})"
        )
    return parsed


def parse_hydration(raw: str, label: str = "hydration") -> int:
    text = str(raw).strip()
    try:
        value = int(text)
    except ValueError:
        raise UsageError(
            f"{label} must be a whole number between {HYDRATION_MIN} and {HYDRATION_MAX} "
            f"percent (got {text!r})"
        ) from None
    if not HYDRATION_MIN <= value <= HYDRATION_MAX:
        raise UsageError(
            f"{label} must be between {HYDRATION_MIN} and {HYDRATION_MAX} percent (got {value})"
        )
    return value


def parse_rise_hours(raw: str) -> float:
    text = str(raw).strip()
    try:
        value = float(text)
    except ValueError:
        raise UsageError(
            f"rise hours must be a number between {RISE_MIN} and {RISE_MAX} (got {text!r})"
        ) from None
    if not math.isfinite(value) or not RISE_MIN <= value <= RISE_MAX:
        raise UsageError(f"rise hours must be between {RISE_MIN} and {RISE_MAX} (got {text})")
    return value


def parse_crumb(raw: str) -> int:
    text = str(raw).strip()
    try:
        value = int(text)
    except ValueError:
        raise UsageError(
            f"crumb score must be an integer between {CRUMB_MIN} and {CRUMB_MAX} (got {text!r})"
        ) from None
    if not CRUMB_MIN <= value <= CRUMB_MAX:
        raise UsageError(f"crumb score must be between {CRUMB_MIN} and {CRUMB_MAX} (got {value})")
    return value


def parse_temperature(raw: str) -> float:
    text = str(raw).strip()
    for suffix in ("\u00b0C", "\u00b0c", "C", "c", "\u00b0"):
        if text.endswith(suffix):
            text = text[: -len(suffix)].strip()
            break
    try:
        value = float(text)
    except ValueError:
        raise UsageError(
            f"temperature must be a number in Celsius (got {str(raw).strip()!r})"
        ) from None
    if not math.isfinite(value):
        raise UsageError(
            f"temperature must be a finite number in Celsius (got {str(raw).strip()!r})"
        )
    return value


# --------------------------------------------------------------------------- #
# Bake-time arithmetic (derived at display time, never stored)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class BakeTime:
    hour: int
    minute: int
    days_ahead: int

    @property
    def clock(self) -> str:
        return f"{self.hour:02d}:{self.minute:02d}"


def compute_bake(feed: tuple[int, int], rise_hours: float) -> BakeTime:
    total_minutes = feed[0] * 60 + feed[1] + round(rise_hours * 60)
    days_ahead, remainder = divmod(total_minutes, 24 * 60)
    return BakeTime(hour=remainder // 60, minute=remainder % 60, days_ahead=days_ahead)


def bake_label(bake: BakeTime) -> str:
    if bake.days_ahead == 0:
        return bake.clock
    if bake.days_ahead == 1:
        return f"{bake.clock} +1 day"
    return f"{bake.clock} +{bake.days_ahead} days"


def preset_bake(preset: dict) -> BakeTime | None:
    feed = split_feed_time(preset.get("feed_time"))
    rise = preset.get("rise_hours")
    if feed is None or isinstance(rise, bool) or not isinstance(rise, (int, float)):
        return None
    return compute_bake(feed, float(rise))


# --------------------------------------------------------------------------- #
# JSON store: ~/.sourdoughclock.json, overridable with SDC_DATA
# --------------------------------------------------------------------------- #
def data_file_path() -> Path:
    override = os.environ.get(DATA_ENV_VAR, "").strip()
    if override:
        return Path(override).expanduser()
    return Path.home() / DEFAULT_DATA_NAME


def empty_store() -> dict:
    return {"version": SCHEMA_VERSION, "presets": [], "batches": []}


def _coerce_presets(entries: object, path: Path) -> list[dict]:
    if entries is None:
        return []
    if not isinstance(entries, list):
        raise DataFileError(
            f'data file has an unexpected structure ("presets" must be a list): {path}'
        )
    presets: list[dict] = []
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("name"), str):
            raise DataFileError(
                f"data file has a malformed preset entry (a name is required): {path}"
            )
        presets.append(
            {
                "name": entry["name"],
                "hydration_pct": entry.get("hydration_pct"),
                "feed_time": entry.get("feed_time"),
                "rise_hours": entry.get("rise_hours"),
            }
        )
    return presets


def _coerce_batches(entries: object, path: Path) -> list[dict]:
    if entries is None:
        return []
    if not isinstance(entries, list):
        raise DataFileError(
            f'data file has an unexpected structure ("batches" must be a list): {path}'
        )
    batches: list[dict] = []
    for entry in entries:
        identifier = entry.get("id") if isinstance(entry, dict) else None
        if not isinstance(identifier, int) or isinstance(identifier, bool):
            raise DataFileError(
                f"data file has a malformed batch entry (an integer id is required): {path}"
            )
        batches.append(
            {
                "id": entry["id"],
                "date": entry.get("date"),
                "preset_name": entry.get("preset_name"),
                "crumb_score": entry.get("crumb_score"),
                "notes": entry.get("notes"),
            }
        )
    return batches


def load_store(path: Path) -> dict:
    """Read the JSON store; a missing or empty file is simply an empty store."""
    if not path.exists():
        return empty_store()
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise DataFileError(f"could not read data file {path}: {exc.strerror or exc}") from exc
    if not raw.strip():
        return empty_store()
    try:
        document = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise DataFileError(
            f"data file is not valid JSON: {path} "
            f"(line {exc.lineno}, column {exc.colno}: {exc.msg}); "
            "fix or remove the file - SourDoughClock will not overwrite it"
        ) from exc
    if not isinstance(document, dict):
        raise DataFileError(
            f"data file is not valid JSON for SourDoughClock (expected an object): {path}"
        )
    return {
        "version": SCHEMA_VERSION,
        "presets": _coerce_presets(document.get("presets", []), path),
        "batches": _coerce_batches(document.get("batches", []), path),
    }


def save_store(path: Path, store: dict) -> None:
    """Write atomically: a same-directory temp file, then os.replace.

    An interrupted write can never leave a half-written store; on failure the
    previous file is untouched and no temp file is left behind.
    """
    parent = path.parent
    if parent.exists() and not parent.is_dir():
        raise DataFileError(f"could not write data file {path}: {parent} is not a directory")
    try:
        parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise DataFileError(f"could not write data file {path}: {exc.strerror or exc}") from exc

    payload = json.dumps(store, indent=2, ensure_ascii=False) + "\n"
    temp_name: str | None = None
    try:
        handle_fd, temp_name = tempfile.mkstemp(
            dir=str(parent), prefix=".sourdoughclock-", suffix=".tmp"
        )
        with os.fdopen(handle_fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
        temp_name = None
    except OSError as exc:
        raise DataFileError(f"could not write data file {path}: {exc.strerror or exc}") from exc
    finally:
        if temp_name is not None:
            try:
                os.unlink(temp_name)
            except FileNotFoundError:
                pass  # already gone: nothing left to clean up
            except OSError as cleanup_error:
                print(
                    f"warning: could not remove temporary file {temp_name}: {cleanup_error}",
                    file=sys.stderr,
                )


def find_preset(presets: list[dict], name: str) -> dict | None:
    wanted = str(name).strip().casefold()
    for preset in presets:
        if str(preset.get("name", "")).strip().casefold() == wanted:
            return preset
    return None


def next_batch_id(batches: list[dict]) -> int:
    highest = 0
    for batch in batches:
        identifier = batch.get("id")
        if (
            isinstance(identifier, int)
            and not isinstance(identifier, bool)
            and identifier > highest
        ):
            highest = identifier
    return highest + 1


# --------------------------------------------------------------------------- #
# Rise lookups: nearest tabulated row and column, always explained
# --------------------------------------------------------------------------- #
def nearest_temperature(requested: float) -> tuple[int, str]:
    for candidate in RISE_TEMPERATURES:
        if abs(candidate - requested) < 1e-9:
            return candidate, f"exact tabulated temperature {candidate}C"
    lowest, highest = RISE_TEMPERATURES[0], RISE_TEMPERATURES[-1]
    if requested < lowest:
        return lowest, (
            f"requested {format_temp(requested)} is below the table minimum; "
            f"clamped to nearest table edge {lowest}C"
        )
    if requested > highest:
        return highest, (
            f"requested {format_temp(requested)} is above the table maximum; "
            f"clamped to nearest table edge {highest}C"
        )
    nearest = min(RISE_TEMPERATURES, key=lambda candidate: (abs(candidate - requested), candidate))
    return nearest, f"nearest tabulated temperature {nearest}C (requested {format_temp(requested)})"


def nearest_hydration(requested: int) -> tuple[int, str]:
    if requested in RISE_HYDRATIONS:
        return requested, f"exact hydration column {requested}%"
    nearest = min(RISE_HYDRATIONS, key=lambda candidate: (abs(candidate - requested), candidate))
    return nearest, f"nearest tabulated hydration {nearest}% (requested {requested}%)"


# --------------------------------------------------------------------------- #
# Commands: preset
# --------------------------------------------------------------------------- #
def cmd_preset_add(args: argparse.Namespace, style: Style) -> int:
    name = args.name.strip()
    if not name:
        raise UsageError("preset name must not be empty")
    hydration = parse_hydration(args.hydration)
    feed_hour, feed_minute = parse_feed_time(args.feed)
    rise_hours = parse_rise_hours(args.rise)

    path = data_file_path()
    store = load_store(path)
    existing = find_preset(store["presets"], name)
    if existing is not None:
        raise UsageError(
            f"a preset named {existing['name']!r} already exists; presets are create-and-list "
            "only, so choose a different name (see `sdc preset list`)"
        )

    feed_time = f"{feed_hour:02d}:{feed_minute:02d}"
    store["presets"].append(
        {
            "name": name,
            "hydration_pct": hydration,
            "feed_time": feed_time,
            "rise_hours": rise_hours,
        }
    )
    save_store(path, store)

    bake = compute_bake((feed_hour, feed_minute), rise_hours)
    print(
        f"Preset {name!r} saved: {hydration}% hydration \u00b7 feed {feed_time} \u00b7 "
        f"rise {format_hours(rise_hours)} \u00b7 bake {style.accent(bake_label(bake))}"
    )
    return EXIT_OK


def cmd_preset_list(args: argparse.Namespace, style: Style) -> int:
    path = data_file_path()
    presets = load_store(path)["presets"]

    if args.json:
        entries = []
        for preset in presets:
            bake = preset_bake(preset)
            entries.append(
                {
                    "name": preset["name"],
                    "hydration_pct": preset.get("hydration_pct"),
                    "feed_time": preset.get("feed_time"),
                    "rise_hours": preset.get("rise_hours"),
                    "bake_time": bake.clock if bake else None,
                    "days_ahead": bake.days_ahead if bake else None,
                }
            )
        print(
            json.dumps(
                {"presets": entries, "count": len(entries), "data_file": str(path)}, indent=2
            )
        )
        return EXIT_OK

    if not presets:
        print(f"No presets yet - {path} is empty.")
        print("  Add the first one with:")
        print("    sdc preset add morning --hydration 100 --feed 22:00 --rise 8")
        return EXIT_OK

    rows: list[list[str]] = []
    accents = set()
    for index, preset in enumerate(presets):
        hydration = preset.get("hydration_pct")
        rise = preset.get("rise_hours")
        bake = preset_bake(preset)
        hydration_text = (
            f"{hydration}%"
            if isinstance(hydration, int) and not isinstance(hydration, bool)
            else "?"
        )
        rows.append(
            [
                preset["name"],
                hydration_text,
                str(preset.get("feed_time") or "?"),
                format_hours(float(rise)) if isinstance(rise, (int, float)) else "?",
                bake_label(bake) if bake else "?",
            ]
        )
        accents.add((index, 4))
    print(
        render_table(
            style,
            ["NAME", "HYDRATION", "FEED", "RISE", "BAKE"],
            rows,
            [LEFT, RIGHT, LEFT, LEFT, LEFT],
            frozenset(accents),
        )
    )
    plural = "preset" if len(presets) == 1 else "presets"
    print(style.dim(f"{len(presets)} {plural} \u00b7 data file: {path}"))
    return EXIT_OK


# --------------------------------------------------------------------------- #
# Commands: rise
# --------------------------------------------------------------------------- #
def cmd_rise(args: argparse.Namespace, style: Style) -> int:
    if args.table:
        return _print_rise_table(args, style)
    if args.temperature is None:
        raise UsageError(
            "a temperature in Celsius is required, e.g. `sdc rise 24 --hydration 100` "
            "(or `sdc rise --table` for the full matrix)"
        )
    if args.hydration is None:
        raise UsageError(
            "--hydration is required for a rise lookup, e.g. `sdc rise 24 --hydration 100`"
        )

    temperature = parse_temperature(args.temperature)
    hydration = parse_hydration(args.hydration)
    table_temperature, temperature_note = nearest_temperature(temperature)
    table_hydration, hydration_note = nearest_hydration(hydration)
    hours = RISE_MATRIX[table_temperature][table_hydration]

    if args.json:
        print(
            json.dumps(
                {
                    "requested_temperature_c": temperature,
                    "requested_hydration_pct": hydration,
                    "table_temperature_c": table_temperature,
                    "table_hydration_pct": table_hydration,
                    "rise_hours": hours,
                    "temperature_note": temperature_note,
                    "hydration_note": hydration_note,
                },
                indent=2,
            )
        )
        return EXIT_OK

    print(
        f"Rise estimate: {style.accent(format_hours(hours))}  \u00b7  "
        f"{table_temperature}C \u00d7 {table_hydration}% hydration"
    )
    print(f"  temperature: {temperature_note}")
    print(f"  hydration: {hydration_note}")
    print(style.dim("  full matrix: sdc rise --table"))
    return EXIT_OK


def _print_rise_table(args: argparse.Namespace, style: Style) -> int:
    hydrations = list(RISE_HYDRATIONS)
    if args.json:
        print(
            json.dumps(
                {
                    "temperatures_c": list(RISE_TEMPERATURES),
                    "hydrations_pct": hydrations,
                    "rise_hours": {
                        str(temperature): {
                            str(hydration): RISE_MATRIX[temperature][hydration]
                            for hydration in hydrations
                        }
                        for temperature in RISE_TEMPERATURES
                    },
                },
                indent=2,
            )
        )
        return EXIT_OK

    headers = ["TEMPERATURE"] + [f"{hydration}%" for hydration in hydrations]
    rows = [
        [f"{temperature}C"] + [format_hours(RISE_MATRIX[temperature][h]) for h in hydrations]
        for temperature in RISE_TEMPERATURES
    ]
    print(render_table(style, headers, rows, [LEFT] + [RIGHT] * len(hydrations)))
    print(
        style.dim(
            "Hours to a bake-ready rise. Values between rows or columns snap to the "
            "nearest tabulated row and column."
        )
    )
    return EXIT_OK


# --------------------------------------------------------------------------- #
# Commands: log
# --------------------------------------------------------------------------- #
def cmd_log_add(args: argparse.Namespace, style: Style) -> int:
    crumb = parse_crumb(args.crumb)
    notes = " ".join((args.notes or "").split())

    path = data_file_path()
    store = load_store(path)

    preset_name: str | None = None
    if args.preset is not None:
        matched = find_preset(store["presets"], args.preset)
        if matched is None:
            raise UsageError(
                f"unknown preset {args.preset.strip()!r}; run `sdc preset list` to see the "
                "presets that exist (or omit --preset)"
            )
        preset_name = matched["name"]

    entry = {
        "id": next_batch_id(store["batches"]),
        "date": date.today().isoformat(),
        "preset_name": preset_name,
        "crumb_score": crumb,
        "notes": notes,
    }
    store["batches"].append(entry)
    save_store(path, store)

    if args.json:
        print(json.dumps(entry, indent=2))
        return EXIT_OK

    summary = f"Logged batch #{entry['id']} for {entry['date']}: crumb {crumb}/{CRUMB_MAX}"
    if preset_name is not None:
        summary += f" \u00b7 preset {preset_name}"
    if notes:
        summary += f" \u00b7 notes {notes!r}"
    print(summary)
    return EXIT_OK


def cmd_log_list(args: argparse.Namespace, style: Style) -> int:
    path = data_file_path()
    batches = load_store(path)["batches"]
    batches.sort(
        key=lambda batch: (str(batch.get("date") or ""), int(batch.get("id") or 0)), reverse=True
    )

    if args.json:
        print(
            json.dumps(
                {"batches": batches, "count": len(batches), "data_file": str(path)}, indent=2
            )
        )
        return EXIT_OK

    if not batches:
        print(f"No batches logged yet - {path} has no batch entries.")
        print("  Log your first bake with:")
        print("    sdc log add --crumb 8 --notes 'open crumb, 4h bulk'")
        return EXIT_OK

    rows: list[list[str]] = []
    accents = set()
    shortened = False
    for index, batch in enumerate(batches):
        notes = batch.get("notes")
        notes_text = str(notes) if isinstance(notes, str) and notes.strip() else "\u2014"
        trimmed = truncate(notes_text, NOTE_WIDTH)
        shortened = shortened or trimmed != notes_text
        crumb = batch.get("crumb_score")
        rows.append(
            [
                str(batch.get("date") or "?"),
                f"{crumb}/{CRUMB_MAX}" if isinstance(crumb, int) else "?",
                str(batch.get("preset_name") or "\u2014"),
                trimmed,
            ]
        )
        accents.add((index, 1))
    print(
        render_table(
            style,
            ["DATE", "CRUMB", "PRESET", "NOTES"],
            rows,
            [LEFT, RIGHT, LEFT, LEFT],
            frozenset(accents),
        )
    )
    plural = "batch" if len(batches) == 1 else "batches"
    footer = f"{len(batches)} {plural} \u00b7 newest first \u00b7 data file: {path}"
    if shortened:
        footer += " \u00b7 full notes: sdc log list --json"
    print(style.dim(footer))
    return EXIT_OK


# --------------------------------------------------------------------------- #
# Argument parsing
# --------------------------------------------------------------------------- #
def _print_group_help(args: argparse.Namespace, style: Style) -> int:
    args.group_parser.print_help()
    return EXIT_OK


def _add_json_flag(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--json",
        action="store_true",
        help="print machine-readable JSON instead of a table",
    )


def build_parser() -> argparse.ArgumentParser:
    color_flag = argparse.ArgumentParser(add_help=False)
    color_flag.add_argument(
        "--no-color",
        action="store_true",
        default=argparse.SUPPRESS,
        help="disable ANSI colour (also honours NO_COLOR and non-TTY output)",
    )

    parser = argparse.ArgumentParser(
        prog="sdc",
        description=DESCRIPTION,
        epilog=EXAMPLES,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        parents=[color_flag],
    )
    parser.set_defaults(no_color=False)
    parser.add_argument(
        "--version",
        action="version",
        version=f"sdc {__version__} (SourDoughClock)",
        help="show the version and exit",
    )

    commands = parser.add_subparsers(dest="command", metavar="<command>", title="commands")

    preset = commands.add_parser(
        "preset",
        parents=[color_flag],
        help="create and list feed-to-bake presets",
        description=(
            "Create and list feed-to-bake presets: a unique name, the starter hydration, "
            "a 24h feed time and a rise duration. The bake time is derived, never stored."
        ),
    )
    preset.set_defaults(handler=_print_group_help, group_parser=preset)
    preset_actions = preset.add_subparsers(
        dest="preset_action", metavar="<action>", title="actions"
    )

    preset_add = preset_actions.add_parser(
        "add",
        parents=[color_flag],
        help="add a preset (name must be unique)",
        description=(
            "Add a preset. Hydration must be 50-150 percent, the feed time HH:MM between "
            "00:00 and 23:59, and the rise 1-48 hours. Duplicate names are rejected and the "
            "existing preset is left untouched."
        ),
    )
    preset_add.add_argument("name", help="unique preset name, e.g. morning")
    preset_add.add_argument(
        "--hydration", required=True, metavar="PCT", help="starter hydration percent (50-150)"
    )
    preset_add.add_argument(
        "--feed", required=True, metavar="HH:MM", help="24h feed time, e.g. 22:00"
    )
    preset_add.add_argument(
        "--rise", required=True, metavar="HOURS", help="rise duration in hours (1-48, decimals ok)"
    )
    preset_add.set_defaults(handler=cmd_preset_add)

    preset_list = preset_actions.add_parser(
        "list",
        parents=[color_flag],
        help="list presets with computed bake times",
        description="List presets with name, hydration, feed, rise and the derived bake time.",
    )
    _add_json_flag(preset_list)
    preset_list.set_defaults(handler=cmd_preset_list)

    rise = commands.add_parser(
        "rise",
        parents=[color_flag],
        help="estimate a rise duration from the built-in temperature table",
        description=(
            "Estimate rise hours from the built-in temperature-by-hydration table. Values "
            "between tabulated rows or columns snap to the nearest row and column, and the "
            "output always says which row and column were used."
        ),
    )
    rise.add_argument(
        "temperature",
        nargs="?",
        metavar="TEMP",
        help="temperature in Celsius, e.g. 24 (values outside 18-30C clamp to the nearest edge)",
    )
    rise.add_argument(
        "--hydration",
        metavar="PCT",
        help="starter hydration percent (50-150); required unless --table is used",
    )
    rise.add_argument(
        "--table", action="store_true", help="print the full temperature-by-hydration matrix"
    )
    _add_json_flag(rise)
    rise.set_defaults(handler=cmd_rise)

    log = commands.add_parser(
        "log",
        parents=[color_flag],
        help="append and list batches with crumb scores",
        description=(
            "Append bake results to a dated batch log and list them newest first. The batch "
            "date is recorded automatically as today."
        ),
    )
    log.set_defaults(handler=_print_group_help, group_parser=log)
    log_actions = log.add_subparsers(dest="log_action", metavar="<action>", title="actions")

    log_add = log_actions.add_parser(
        "add",
        parents=[color_flag],
        help="append a batch (dated today)",
        description=(
            "Append a batch for today: an integer crumb score 1-10, optional free-text notes, "
            "and an optional --preset that must match an existing preset."
        ),
    )
    log_add.add_argument("--crumb", required=True, metavar="1-10", help="crumb score, integer 1-10")
    log_add.add_argument(
        "--notes", metavar="TEXT", help="free-text notes, e.g. 'open crumb, 4h bulk'"
    )
    log_add.add_argument("--preset", metavar="NAME", help="link the batch to an existing preset")
    _add_json_flag(log_add)
    log_add.set_defaults(handler=cmd_log_add)

    log_list = log_actions.add_parser(
        "list",
        parents=[color_flag],
        help="list batches newest first",
        description="List batches newest first with date, crumb score, linked preset and notes.",
    )
    _add_json_flag(log_list)
    log_list.set_defaults(handler=cmd_log_list)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    style = Style(enabled=color_enabled(sys.stdout, getattr(args, "no_color", False)))

    handler = getattr(args, "handler", None)
    if handler is None:
        parser.print_help()
        return EXIT_OK

    try:
        return int(handler(args, style))
    except SdcError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return exc.exit_code
    except BrokenPipeError:
        # A reader closed the pipe early (e.g. `sdc preset list | head`): not an error.
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
