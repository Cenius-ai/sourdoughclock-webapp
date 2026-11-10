"""Behavioural tests for SourDoughClock (sdc.py).

Each test drives the CLI end to end with an isolated SDC_DATA file and asserts
on stdout, stderr, exit code and the JSON document that lands on disk.
"""

from __future__ import annotations

import json
import os
from datetime import date

import pytest

import sdc


# --------------------------------------------------------------------------- #
# Help / version
# --------------------------------------------------------------------------- #
def test_help_lists_every_command_group(cli):
    result = cli.run("--help")

    assert result.returncode == 0
    assert "create and list feed-to-bake presets" in result.stdout
    assert "estimate a rise duration" in result.stdout
    assert "append and list batches" in result.stdout
    assert result.stderr == ""


def test_bare_invocation_prints_help_and_succeeds(cli):
    result = cli.run()

    assert result.returncode == 0
    assert "usage:" in result.stdout


def test_version_flag(cli):
    result = cli.run("--version")

    assert result.returncode == 0
    assert "sdc 1.0.0" in result.stdout


# --------------------------------------------------------------------------- #
# F1: presets
# --------------------------------------------------------------------------- #
def test_preset_add_derives_bake_time_across_midnight(cli):
    add = cli.run(
        "preset", "add", "morning", "--hydration", "100", "--feed", "22:00", "--rise", "8"
    )

    assert add.returncode == 0
    assert "feed 22:00" in add.stdout
    assert "06:00 +1 day" in add.stdout
    assert add.stderr == ""

    listing = cli.run("preset", "list")
    assert listing.returncode == 0
    assert "morning" in listing.stdout
    assert "100%" in listing.stdout
    assert "22:00" in listing.stdout
    assert "8h" in listing.stdout
    assert "06:00 +1 day" in listing.stdout


def test_preset_add_rejects_unparsable_feed_time_without_writing(cli):
    result = cli.run("preset", "add", "bad", "--hydration", "100", "--feed", "25:00", "--rise", "6")

    assert result.returncode != 0
    assert "feed time must be HH:MM between 00:00 and 23:59" in result.stderr
    assert "25:00" in result.stderr
    assert not cli.data_file.exists()

    listing = cli.run("preset", "list")
    assert "No presets yet" in listing.stdout
    assert "sdc preset add morning --hydration 100 --feed 22:00 --rise 8" in listing.stdout


def test_preset_add_rejects_duplicate_name_and_keeps_original(cli):
    first = cli.run(
        "preset", "add", "morning", "--hydration", "100", "--feed", "22:00", "--rise", "8"
    )
    assert first.returncode == 0

    duplicate = cli.run(
        "preset", "add", "morning", "--hydration", "80", "--feed", "08:00", "--rise", "4"
    )

    assert duplicate.returncode != 0
    assert "already exists" in duplicate.stderr

    document = json.loads(cli.data_file.read_text(encoding="utf-8"))
    assert len(document["presets"]) == 1
    assert document["presets"][0]["hydration_pct"] == 100

    listing = cli.run("preset", "list")
    assert "22:00" in listing.stdout
    assert "08:00" not in listing.stdout


def test_preset_add_rejects_hydration_out_of_range(cli):
    result = cli.run("preset", "add", "noon", "--hydration", "40", "--feed", "12:00", "--rise", "6")

    assert result.returncode != 0
    assert "hydration must be between 50 and 150 percent" in result.stderr
    assert not cli.data_file.exists()


def test_preset_add_rejects_rise_out_of_range(cli):
    result = cli.run(
        "preset", "add", "noon", "--hydration", "100", "--feed", "12:00", "--rise", "60"
    )

    assert result.returncode != 0
    assert "rise hours must be between 1 and 48" in result.stderr
    assert not cli.data_file.exists()


def test_preset_add_rejects_missing_and_non_numeric_values(cli):
    missing = cli.run("preset", "add", "x", "--hydration", "100", "--rise", "6")
    assert missing.returncode != 0
    assert "--feed" in missing.stderr

    non_numeric = cli.run(
        "preset", "add", "x", "--hydration", "wet", "--feed", "12:00", "--rise", "6"
    )
    assert non_numeric.returncode != 0
    assert "hydration must be a whole number" in non_numeric.stderr
    assert not cli.data_file.exists()


def test_preset_list_empty_invites_first_preset(cli):
    result = cli.run("preset", "list")

    assert result.returncode == 0
    assert "No presets yet" in result.stdout
    assert "sdc preset add morning --hydration 100 --feed 22:00 --rise 8" in result.stdout


def test_preset_list_marks_rollover_only_on_the_crossing_row(cli):
    cli.run("preset", "add", "morning", "--hydration", "100", "--feed", "22:00", "--rise", "8")
    cli.run("preset", "add", "noon", "--hydration", "75", "--feed", "12:00", "--rise", "6")

    result = cli.run("preset", "list")

    assert result.returncode == 0
    assert result.stdout.count("+1 day") == 1
    data_rows = [line for line in result.stdout.splitlines() if "morning" in line or "noon" in line]
    assert any("morning" in row and "06:00 +1 day" in row for row in data_rows)
    assert any("noon" in row and "18:00" in row and "+1 day" not in row for row in data_rows)


def test_preset_list_json_contract(cli):
    cli.run("preset", "add", "morning", "--hydration", "100", "--feed", "22:00", "--rise", "8")

    result = cli.run("preset", "list", "--json")

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["count"] == 1
    assert payload["presets"][0] == {
        "name": "morning",
        "hydration_pct": 100,
        "feed_time": "22:00",
        "rise_hours": 8.0,
        "bake_time": "06:00",
        "days_ahead": 1,
    }


# --------------------------------------------------------------------------- #
# F2: rise estimator
# --------------------------------------------------------------------------- #
def test_rise_exact_match(cli):
    result = cli.run("rise", "24", "--hydration", "100")

    assert result.returncode == 0
    assert "8h" in result.stdout
    assert "exact tabulated temperature 24C" in result.stdout
    assert "exact hydration column 100%" in result.stdout


def test_rise_snaps_to_nearest_temperature(cli):
    result = cli.run("rise", "23", "--hydration", "100")

    assert result.returncode == 0
    assert "nearest tabulated temperature 24C" in result.stdout
    assert "requested 23C" in result.stdout
    assert "8h" in result.stdout


def test_rise_snaps_to_nearest_hydration(cli):
    result = cli.run("rise", "24", "--hydration", "80")

    assert result.returncode == 0
    assert "nearest tabulated hydration 75%" in result.stdout
    assert "requested 80%" in result.stdout
    assert "10h" in result.stdout


def test_rise_clamps_below_and_above_the_table(cli):
    below = cli.run("rise", "10", "--hydration", "100")
    assert below.returncode == 0
    assert "clamped to nearest table edge 18C" in below.stdout
    assert "16h" in below.stdout

    above = cli.run("rise", "34", "--hydration", "60")
    assert above.returncode == 0
    assert "clamped to nearest table edge 30C" in above.stdout


def test_rise_requires_hydration(cli):
    result = cli.run("rise", "24")

    assert result.returncode != 0
    assert "--hydration is required" in result.stderr
    assert "Rise estimate" not in result.stdout


def test_rise_rejects_out_of_range_hydration(cli):
    result = cli.run("rise", "24", "--hydration", "40")

    assert result.returncode != 0
    assert "hydration must be between 50 and 150 percent" in result.stderr


def test_rise_rejects_non_numeric_temperature(cli):
    result = cli.run("rise", "warm", "--hydration", "100")

    assert result.returncode != 0
    assert "temperature must be a number in Celsius" in result.stderr


def test_rise_table_prints_full_matrix(cli):
    result = cli.run("rise", "--table")

    assert result.returncode == 0
    for header in ("TEMPERATURE", "60%", "75%", "100%", "125%"):
        assert header in result.stdout
    for temperature in ("18C", "21C", "24C", "27C", "30C"):
        assert temperature in result.stdout
    assert "20h" in result.stdout
    assert "3.5h" in result.stdout


def test_rise_json_contract(cli):
    result = cli.run("rise", "23", "--hydration", "80", "--json")

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["requested_temperature_c"] == 23.0
    assert payload["requested_hydration_pct"] == 80
    assert payload["table_temperature_c"] == 24
    assert payload["table_hydration_pct"] == 75
    assert payload["rise_hours"] == 10.0
    assert "nearest tabulated temperature 24C" in payload["temperature_note"]
    assert "nearest tabulated hydration 75%" in payload["hydration_note"]


# --------------------------------------------------------------------------- #
# F3: batch log
# --------------------------------------------------------------------------- #
def test_log_add_records_today_and_links_preset(cli):
    cli.run("preset", "add", "morning", "--hydration", "100", "--feed", "22:00", "--rise", "8")

    add = cli.run("log", "add", "--preset", "morning", "--crumb", "8", "--notes", "open crumb")

    today = date.today().isoformat()
    assert add.returncode == 0
    assert today in add.stdout
    assert "crumb 8/10" in add.stdout
    assert "preset morning" in add.stdout
    assert "open crumb" in add.stdout

    listing = cli.run("log", "list")
    assert today in listing.stdout
    assert "8/10" in listing.stdout
    assert "morning" in listing.stdout
    assert "open crumb" in listing.stdout


def test_log_add_rejects_invalid_crumb_without_writing(cli):
    result = cli.run("log", "add", "--crumb", "11")

    assert result.returncode != 0
    assert "crumb score must be between 1 and 10" in result.stderr
    assert not cli.data_file.exists()


def test_log_add_rejects_unknown_preset_without_writing(cli):
    result = cli.run("log", "add", "--preset", "rye", "--crumb", "7")

    assert result.returncode != 0
    assert "unknown preset 'rye'" in result.stderr
    assert not cli.data_file.exists()


def test_log_list_empty_invites_first_batch(cli):
    result = cli.run("log", "list")

    assert result.returncode == 0
    assert "No batches logged yet" in result.stdout
    assert "sdc log add --crumb 8 --notes" in result.stdout


def test_log_list_shows_newest_first(cli):
    cli.run("preset", "add", "morning", "--hydration", "100", "--feed", "22:00", "--rise", "8")
    cli.run("log", "add", "--preset", "morning", "--crumb", "6", "--notes", "first bake")
    cli.run("log", "add", "--crumb", "9", "--notes", "second bake")

    payload = json.loads(cli.run("log", "list", "--json").stdout)

    assert payload["count"] == 2
    assert [batch["crumb_score"] for batch in payload["batches"]] == [9, 6]
    assert payload["batches"][0]["id"] > payload["batches"][1]["id"]
    assert all(batch["date"] == date.today().isoformat() for batch in payload["batches"])


def test_log_add_records_optional_fields_as_empty(cli):
    add = cli.run("log", "add", "--crumb", "7")
    assert add.returncode == 0

    payload = json.loads(cli.run("log", "list", "--json").stdout)
    assert payload["batches"][0]["notes"] == ""
    assert payload["batches"][0]["preset_name"] is None


# --------------------------------------------------------------------------- #
# Hardening: atomic writes and corrupt stores
# --------------------------------------------------------------------------- #
def test_corrupt_json_is_reported_with_path_and_left_alone(tmp_path, cli):
    broken = tmp_path / "broken.json"
    broken.write_text('{"presets": [', encoding="utf-8")

    result = cli.run("preset", "list", data_file=broken)

    assert result.returncode == 1
    assert "data file is not valid JSON" in result.stderr
    assert str(broken) in result.stderr
    assert broken.read_text(encoding="utf-8") == '{"presets": ['


def test_unwritable_data_path_reports_and_leaves_no_partial_file(tmp_path, cli):
    blocker = tmp_path / "blocker"
    blocker.write_text("not a directory", encoding="utf-8")
    target = blocker / "store.json"

    result = cli.run(
        "preset",
        "add",
        "x",
        "--hydration",
        "100",
        "--feed",
        "10:00",
        "--rise",
        "4",
        data_file=target,
    )

    assert result.returncode == 1
    assert "could not write data file" in result.stderr
    assert str(target) in result.stderr
    assert not target.exists()
    assert blocker.read_text(encoding="utf-8") == "not a directory"


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores directory permissions")
def test_read_only_directory_reports_and_leaves_no_partial_file(tmp_path, cli):
    locked = tmp_path / "locked"
    locked.mkdir()
    locked.chmod(0o555)
    try:
        result = cli.run(
            "preset",
            "add",
            "x",
            "--hydration",
            "100",
            "--feed",
            "10:00",
            "--rise",
            "4",
            data_file=locked / "store.json",
        )

        assert result.returncode == 1
        assert "could not write data file" in result.stderr
        assert list(locked.iterdir()) == []
    finally:
        locked.chmod(0o755)


def test_successful_write_leaves_no_temporary_files(tmp_path, cli):
    cli.run("preset", "add", "morning", "--hydration", "100", "--feed", "22:00", "--rise", "8")

    leftovers = [entry.name for entry in tmp_path.iterdir() if entry.name != "store.json"]
    assert leftovers == []


def test_store_document_shape(cli):
    cli.run("preset", "add", "morning", "--hydration", "100", "--feed", "22:00", "--rise", "8")
    cli.run("log", "add", "--preset", "morning", "--crumb", "8")

    document = json.loads(cli.data_file.read_text(encoding="utf-8"))

    assert document["version"] == 1
    assert document["presets"] == [
        {"name": "morning", "hydration_pct": 100, "feed_time": "22:00", "rise_hours": 8.0}
    ]
    assert document["batches"][0]["crumb_score"] == 8
    assert document["batches"][0]["preset_name"] == "morning"


# --------------------------------------------------------------------------- #
# Pure functions
# --------------------------------------------------------------------------- #
def test_compute_bake_handles_rollover_and_multi_day():
    assert sdc.bake_label(sdc.compute_bake((22, 0), 8)) == "06:00 +1 day"
    assert sdc.bake_label(sdc.compute_bake((12, 0), 6)) == "18:00"
    assert sdc.bake_label(sdc.compute_bake((20, 0), 30)) == "02:00 +2 days"
    assert sdc.bake_label(sdc.compute_bake((23, 30), 1.5)) == "01:00 +1 day"


def test_feed_time_parser_rejects_impossible_clock_values():
    for bad in ("25:00", "12:60", "noon", ""):
        with pytest.raises(sdc.UsageError):
            sdc.parse_feed_time(bad)
    assert sdc.parse_feed_time("7:05") == (7, 5)
