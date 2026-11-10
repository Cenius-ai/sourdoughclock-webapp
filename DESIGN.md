# SourDoughClock — committed design direction

This is a terminal product, so the design source of truth is the `THEME` block at
the top of `sdc.py` (the CLI equivalent of a CSS `:root`) plus this document.
Every output surface — `preset list`, `preset add`, `rise`, `rise --table`,
`log list`, `log add`, the empty states and the error lines — consumes those
tokens through the single `Style` / `render_table` pair. There are no per-command
ad-hoc layouts.

## Tokens

| token | value | used for |
|---|---|---|
| archetype | `cli` | one command surface, no GUI |
| style family | calm-precise | short factual lines, no exclamation, no ASCII art |
| accent (CSS form) | `oklch(0.58 0.12 39)` | documented here only; never emitted to a terminal |
| accent (hex) | `#b55e42` | non-CSS contexts (`THEME["accent_hex"]`) |
| accent (terminal) | truecolor `38;2;181;94;66` | the **one** primary status cell per screen |
| neutral ramp | default terminal foreground + SGR `2` (dim) for secondary lines | footer/metadata lines |
| surface / mode | terminal dark | the only honest CLI surface; never re-theme the user's terminal |
| type | system monospace, no web fonts | the terminal's own font |
| density | compact | no blank-line padding inside tables, one line per record |
| rules | `─` `│` `┼` | aligned-column separators in every table |
| shape | no boxes, no corners, no elevation | rules only; no outer frame |

## Signature rules

1. **Aligned columns everywhere.** Names/notes left-aligned, numbers right-aligned,
   one space of padding either side of each `│` rule.
2. **One accent for primary status.** `preset list` → the BAKE cell; `rise` → the
   estimate; `log list` → the crumb score. Never a second accent.
3. **No colour-only signal.** Every accented value also carries its text
   (`06:00 +1 day`, `8h`, `8/10`), so the output is identical in meaning under
   `NO_COLOR`, in a pipe, or on a monochrome terminal.
4. **Colour is opt-in.** Only when stdout is a TTY, `TERM` is not `dumb`, and
   `NO_COLOR` is unset; `--no-color` always wins.
5. **Help-first.** `sdc` with no arguments prints the command map and copy-pasteable
   examples; each group and each action has its own `--help`.
6. **Honest empties.** An empty list prints why it is empty and the exact command
   that fills it — never a blank screen.
7. **Errors are one line, on stderr, actionable**: what was wrong, the value
   received, and what to do next.

## Screen map

| screen | shape |
|---|---|
| `sdc preset add` | one success line: hydration · feed · rise · accented bake (+N day marker) |
| `sdc preset list` | 5-column table (NAME, HYDRATION, FEED, RISE, BAKE) + dim footer with count and store path |
| `sdc rise` | headline estimate + accented hours, then aligned `temperature:` / `hydration:` notes naming the row and column used |
| `sdc rise --table` | matrix table with temperature rows, hydration columns, right-aligned hours |
| `sdc log add` | one success line: batch id · date · crumb · preset · notes |
| `sdc log list` | 4-column table (DATE, CRUMB, PRESET, NOTES) newest first + dim footer |

## Deliberately absent

No spinner, no progress bar, no colour picker, no ASCII logo, no animation:
every command finishes in milliseconds against a local file, and decoration would
be a lie about work being done.
