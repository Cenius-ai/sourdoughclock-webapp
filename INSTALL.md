# Installing SourDoughClock

SourDoughClock is one Python file. There is no build step, no database, no
service and no configuration file to edit.

## 1. Prerequisites (installed on your machine, not by this project)

| requirement | why |
|---|---|
| Python **3.9+** (`python3` on PATH) | runs `sdc.py` |
| a POSIX shell (`bash`/`sh`) | runs `install.sh` and `demo.sh`; optional |
| `pip` for that Python | installs the test runner only |

Nothing else: no compilers, no `libsqlite3-dev`, no Node, no Docker. Verify with:

```bash
python3 --version
```

## 2. Unpack and enter the project

```bash
tar -xzf sourdoughclock.tar.gz
cd sourdoughclock
```

`sdc.py`, `requirements.txt` and `pyproject.toml` sit at the project root.

## 3. Install the project dependencies

The standard package manager for this project is **pip** (no lockfile is needed:
the only dependency is the test runner, and the tool itself has none).

```bash
bash install.sh
```

`install.sh` upgrades pip/setuptools/wheel, installs `requirements.txt`, imports
`sdc` to prove the file is complete, and **exits** — it never starts a
long-running process. It is safe to re-run, and it uses only project-level pip
commands (never `sudo`, `apt-get` or any system package).

Shortcut if you only want to use the tool: skip this step. `python3 sdc.py --help`
already works, because the runtime is the standard library.

## 4. Verify the install

```bash
python3 sdc.py --version      # sdc 1.0.0 (SourDoughClock)
python3 sdc.py --help         # preset / rise / log command groups
```

If `install.sh` managed an editable install, the shorter `sdc --version` works too.

## 5. Populate a demo store (optional, recommended for a first look)

```bash
bash demo.sh
```

`demo.sh` runs a complete non-interactive transcript (presets, validations, rise
lookups, the full table, the batch log, `--json` output) against an **isolated**
store at `.sdc-demo/sourdoughclock.json`, so your real data is untouched. It
recreates that file on every run, so it is idempotent.

Keep using the demo data afterwards with:

```bash
SDC_DATA=.sdc-demo/sourdoughclock.json python3 sdc.py preset list
```

Your own store at `~/.sourdoughclock.json` starts empty on purpose — the first
`preset list` prints the exact `preset add` command to create your first preset.

## 6. Run it (dev use)

```bash
python3 sdc.py preset add morning --hydration 100 --feed 22:00 --rise 8
python3 sdc.py preset list
python3 sdc.py rise 24 --hydration 100
python3 sdc.py log add --preset morning --crumb 8 --notes 'open crumb'
python3 sdc.py log list
```

`python3 main.py ...` is an equivalent entry point, and `bash install.sh` also
installs an `sdc` console command when the environment permits it.

## 7. Run the tests

```bash
python3 -m pytest              # 41 behavioural tests, no network, no services
python3 tests/test_smoke.py    # standalone smoke test; prints PASS
```

The suite drives the real CLI through subprocesses with `SDC_DATA` pointed at
temporary files, so it never touches your own store.

## 8. Uninstall / clean up

```bash
python3 -m pip uninstall sourdoughclock   # only if you installed the sdc command
rm -f ~/.sourdoughclock.json              # your presets and batch log
rm -rf .sdc-demo                          # the demo store
```

## Environment variables

| variable | default | meaning |
|---|---|---|
| `SDC_DATA` | `~/.sourdoughclock.json` | path to the JSON store |
| `NO_COLOR` | unset | any value disables ANSI colour (colour is already off when stdout is not a TTY) |

There are no secrets, keys or API tokens: the tool never makes a network call.
