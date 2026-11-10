#!/usr/bin/env bash
#
# SourDoughClock end-to-end demo - non-interactive, no network, no prompts.
#
# Runs a full transcript against a throwaway demo store so your real
# ~/.sourdoughclock.json is never touched. Re-runnable: the demo store is
# recreated from scratch on every run, and it is left in place afterwards so
# you can keep poking at the same data:
#
#   SDC_DATA="$PWD/.sdc-demo/sourdoughclock.json" python3 sdc.py preset list
#
set -euo pipefail
cd "$(dirname "$0")"

SDC=(python3 sdc.py)
DEMO_DIR="$PWD/.sdc-demo"
DEMO_DATA="$DEMO_DIR/sourdoughclock.json"

mkdir -p "$DEMO_DIR"
rm -f "$DEMO_DATA"
export SDC_DATA="$DEMO_DATA"
export PYTHONIOENCODING="utf-8"

step() {
    printf '\n$ sdc %s\n' "$*"
    if "${SDC[@]}" "$@"; then
        return 0
    else
        printf '(exit %s)\n' "$?"
        return 0
    fi
}

printf 'SourDoughClock demo · data file: %s\n' "$DEMO_DATA"
"${SDC[@]}" --version

step --help

printf '\n--- presets: feed-to-bake schedules ---\n'
step preset add morning --hydration 100 --feed 22:00 --rise 8
step preset add rye-sunday --hydration 75 --feed 07:30 --rise 4.5
step preset add sandwich-loaf --hydration 60 --feed 18:15 --rise 12
step preset add cold-retard --hydration 125 --feed 20:00 --rise 30
step preset list

printf '\n--- validation: nothing is written on a bad value ---\n'
step preset add morning --hydration 80 --feed 08:00 --rise 4
step preset add bad --hydration 100 --feed 25:00 --rise 6
step preset add noon --hydration 40 --feed 12:00 --rise 6
step preset add noon --hydration 100 --feed 12:00 --rise 60

printf '\n--- rise estimator: nearest row and column always explained ---\n'
step rise --table
step rise 24 --hydration 100
step rise 23 --hydration 100
step rise 24 --hydration 80
step rise 10 --hydration 100
step rise 34 --hydration 125
step rise 24

printf '\n--- batch log: dated, scored, optionally linked to a preset ---\n'
step log add --preset morning --crumb 8 --notes 'open crumb, 4h bulk, cold retard'
step log add --preset rye-sunday --crumb 9 --notes 'airy, sour finish, strong oven spring'
step log add --preset sandwich-loaf --crumb 6 --notes 'tight crumb, cut the bulk 45 min short'
step log add --preset cold-retard --crumb 10 --notes 'best yet - blistered crust, custardy interior'
step log add --crumb 4 --notes 'no preset link: overproofed on a 27C afternoon'
step log add --crumb 11
step log add --preset rye --crumb 7
step log list

printf '\n--- scripting ---\n'
step preset list --json
step log list --json

printf '\n--- the store is plain JSON ---\n'
printf '$ cat %s\n' "$DEMO_DATA"
cat "$DEMO_DATA"

printf '\nDemo complete. Your own store stays at ~/.sourdoughclock.json.\n'
printf 'Reuse this demo data with: SDC_DATA="%s" python3 sdc.py preset list\n' "$DEMO_DATA"
