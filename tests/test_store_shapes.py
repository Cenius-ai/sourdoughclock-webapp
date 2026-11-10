"""Store-shape and edge-case tests for SourDoughClock.

These cover the paths a hand-edited or damaged JSON document can take, plus the
case-insensitive preset link, so a corrupt store always fails with a readable
message instead of a traceback.
"""

from __future__ import annotations

import json

import pytest


@pytest.mark.parametrize(
    "document",
    [
        "[]",
        '{"presets": {}, "batches": []}',
        '{"presets": [{"hydration_pct": 100}], "batches": []}',
        '{"presets": [], "batches": [{"crumb_score": 8}]}',
    ],
    ids=["not-an-object", "presets-not-a-list", "preset-without-name", "batch-without-id"],
)
def test_malformed_store_is_reported_without_touching_the_file(tmp_path, cli, document):
    store = tmp_path / "odd.json"
    store.write_text(document, encoding="utf-8")

    result = cli.run("preset", "list", data_file=store)

    assert result.returncode == 1
    assert "data file has" in result.stderr or "not valid JSON for SourDoughClock" in result.stderr
    assert str(store) in result.stderr
    assert store.read_text(encoding="utf-8") == document


def test_empty_file_is_an_empty_store(cli, tmp_path):
    store = tmp_path / "blank.json"
    store.write_text("", encoding="utf-8")

    listing = cli.run("preset", "list", data_file=store)
    assert listing.returncode == 0
    assert "No presets yet" in listing.stdout

    added = cli.run(
        "preset",
        "add",
        "morning",
        "--hydration",
        "100",
        "--feed",
        "22:00",
        "--rise",
        "8",
        data_file=store,
    )
    assert added.returncode == 0
    assert json.loads(store.read_text(encoding="utf-8"))["presets"][0]["name"] == "morning"


def test_preset_link_is_case_insensitive_and_stores_canonical_name(cli):
    cli.run("preset", "add", "Morning", "--hydration", "100", "--feed", "22:00", "--rise", "8")

    added = cli.run("log", "add", "--preset", "morning", "--crumb", "9")
    assert added.returncode == 0

    stored = json.loads(cli.data_file.read_text(encoding="utf-8"))
    assert stored["batches"][0]["preset_name"] == "Morning"


def test_preset_names_are_unique_case_insensitively(cli):
    cli.run("preset", "add", "Morning", "--hydration", "100", "--feed", "22:00", "--rise", "8")

    duplicate = cli.run(
        "preset", "add", "MORNING", "--hydration", "75", "--feed", "08:00", "--rise", "4"
    )

    assert duplicate.returncode == 2
    assert "already exists" in duplicate.stderr
    stored = json.loads(cli.data_file.read_text(encoding="utf-8"))
    assert len(stored["presets"]) == 1
