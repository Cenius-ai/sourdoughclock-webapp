# Using SourDoughClock

All examples run from the project root and use `python3 sdc.py`; if `install.sh`
installed the console command, `sdc` alone is equivalent. Add `--no-color` (or
export `NO_COLOR=1`) for plain text.

## 1. Presets: when do I feed, when do I bake?

A preset stores four things: a unique name, the starter hydration, a 24-hour feed
time and a rise duration. The bake time is **derived**, never stored, so it can
never drift from the values you entered.

```bash
python3 sdc.py preset add morning --hydration 100 --feed 22:00 --rise 8
# Preset 'morning' saved: 100% hydration · feed 22:00 · rise 8h · bake 06:00 +1 day
```

```bash
python3 sdc.py preset list
# NAME          │ HYDRATION │ FEED  │ RISE │ BAKE
# ──────────────┼───────────┼───────┼──────┼──────────────
# morning       │      100% │ 22:00 │ 8h   │ 06:00 +1 day
# rye-sunday    │       75% │ 07:30 │ 4.5h │ 12:00
# cold-retard   │      125% │ 20:00 │ 30h  │ 02:00 +2 days
```

Rules the tool enforces — each failure prints one line to stderr, exits 2 and
writes nothing:

| input | message |
|---|---|
| `--feed 25:00` | `feed time must be HH:MM between 00:00 and 23:59 (got '25:00')` |
| `--hydration 40` | `hydration must be between 50 and 150 percent (got 40)` |
| `--rise 60` | `rise hours must be between 1 and 48 (got 60)` |
| duplicate name | `a preset named 'morning' already exists; ... choose a different name` |

Name matching is case-insensitive, so `Morning` and `morning` are the same preset.
Presets are create-and-list only in this version: there is no edit or delete.

An empty list tells you exactly what to type next:

```
No presets yet - /home/you/.sourdoughclock.json is empty.
  Add the first one with:
    sdc preset add morning --hydration 100 --feed 22:00 --rise 8
```

## 2. Rise estimator: how long at this temperature?

`--hydration` is required — there is no ambiguous default column.

```bash
python3 sdc.py rise 24 --hydration 100
# Rise estimate: 8h  ·  24C × 100% hydration
#   temperature: exact tabulated temperature 24C
#   hydration: exact hydration column 100%
```

Between tabulated values the tool snaps and says so:

```bash
python3 sdc.py rise 23 --hydration 100
# Rise estimate: 8h  ·  24C × 100% hydration
#   temperature: nearest tabulated temperature 24C (requested 23C)
#   hydration: exact hydration column 100%

python3 sdc.py rise 24 --hydration 80
# Rise estimate: 10h  ·  24C × 75% hydration
#   temperature: exact tabulated temperature 24C
#   hydration: nearest tabulated hydration 75% (requested 80%)
```

Outside the table the value clamps to the nearest edge:

```bash
python3 sdc.py rise 10 --hydration 100
#   temperature: requested 10C is below the table minimum; clamped to nearest table edge 18C
```

Print the whole matrix:

```bash
python3 sdc.py rise --table
# TEMPERATURE │ 60% │  75% │ 100% │  125%
# ────────────┼─────┼──────┼──────┼──────
# 18C         │ 20h │  18h │  16h │ 14.5h
# ...
```

Errors: a missing `--hydration`, a non-numeric temperature, or a hydration outside
50-150 each print one line to stderr and exit 2 — no estimate is printed.

## 3. Batch log: was it any good?

```bash
python3 sdc.py log add --preset morning --crumb 8 --notes 'open crumb, 4h bulk'
# Logged batch #1 for 2026-11-10: crumb 8/10 · preset morning · notes 'open crumb, 4h bulk'
```

* the batch date is recorded automatically as today (no backdating in this version)
* `--crumb` must be an integer 1-10
* `--notes` is free text and optional
* `--preset` must match an existing preset; the check runs before anything is written

```bash
python3 sdc.py log list
# DATE       │ CRUMB │ PRESET     │ NOTES
# ───────────┼───────┼────────────┼──────────────────────────────────
# 2026-11-10 │  9/10 │ rye-sunday │ airy, sour finish, strong oven…
# 2026-11-10 │  8/10 │ morning    │ open crumb, 4h bulk, cold retard
```

Newest first. Long notes are elided in the table; `--json` returns the full text.
The empty log invites the first entry:

```
No batches logged yet - /home/you/.sourdoughclock.json has no batch entries.
  Log your first bake with:
    sdc log add --crumb 8 --notes 'open crumb, 4h bulk'
```

## 4. Scripting

```bash
python3 sdc.py preset list --json | jq '.presets[].name'
python3 sdc.py rise 24 --hydration 100 --json | jq .rise_hours
python3 sdc.py log list --json | jq '.batches[0].crumb_score'
```

`--json` payloads:

* `preset list` → `{"presets": [{name, hydration_pct, feed_time, rise_hours, bake_time, days_ahead}], "count", "data_file"}`
* `rise` → `{requested_temperature_c, requested_hydration_pct, table_temperature_c, table_hydration_pct, rise_hours, temperature_note, hydration_note}`
* `rise --table` → `{temperatures_c: [...], hydrations_pct: [...], rise_hours: {"24": {"100": 8.0, ...}}}`
* `log list` → `{"batches": [{id, date, preset_name, crumb_score, notes}], "count", "data_file"}`
* `log add --json` → the created batch entry

## 5. Separate stores (demos, tests, two kitchens)

```bash
SDC_DATA=./.sdc-demo/sourdoughclock.json python3 sdc.py preset list
SDC_DATA=/tmp/rye-only.json python3 sdc.py preset add rye --hydration 75 --feed 07:30 --rise 4.5
```

The parent directory is created if missing. If the store cannot be written (a
read-only directory, or a path whose parent is a regular file) the command prints
`could not write data file <path>: <reason>` and exits 1 — the previous file is
left exactly as it was and no temporary file remains.

A store with invalid JSON is reported with its path and line/column and is
**never** overwritten:

```
error: data file is not valid JSON: /tmp/broken.json (line 1, column 14: Expecting value); fix or remove the file - SourDoughClock will not overwrite it
```

## 6. Exit codes

| code | meaning |
|---|---|
| 0 | success (including an empty list, which still exits 0) |
| 1 | data-file problem: unreadable, corrupt, or unwritable |
| 2 | invalid input: bad flag, bad `HH:MM`, value out of range |
