# Task — Antigravity · Catalogue screen, then the two plan views

**Branch:** `feat/plan-views`
**Base:** `main` (302 passing tests)
**Read first:** [`SHARED-CONTRACT.md`](SHARED-CONTRACT.md) — the fields you render
are fixed there. OpenCode is filling those columns in parallel.

---

## Work in a separate git worktree

```bash
cd /Users/shubhamlandge/Documents/antigravity/Strenthlab
git worktree add ../strengthlab-views -b feat/plan-views main
cd ../strengthlab-views
python3 -m venv .venv && ./.venv/bin/pip install -q -r requirements.txt -r requirements-dev.txt
./.venv/bin/python -m pytest -q     # must print 302 passed
PORT=5003 ./.venv/bin/python app.py
```

Port 5003 — 5001 and 5002 are taken, 5000 is macOS AirPlay.

**Never delete a `.venv` you did not create**, and never run `git checkout` or
`git reset` in the original directory. Create your own venv as above rather than
symlinking. **Push your branch when you finish a part** — last time the work sat
only on this machine.

---

## Part 1 — Catalogue screen · start now, blocks nothing

The content library landed on `main`: `exercise_library` (25 movements) and
`food_library` (37 foods). There is no way to see or edit either.

Build `/settings/catalogue`, admin and owner only:

- **Movements** — name, pattern, role, target muscle, level, equipment,
  contraindications, cues. Edit any field. Deactivate a movement when the
  machine breaks, so plans stop prescribing it. Add a movement.
- **Foods** — name, category, macros per 100 g, veg/vegan flags, allergens,
  exchange group, portion, **source**. Edit any field. Add a food.
- Show the **source** on every food row. A trainer correcting a macro needs to
  see where the current number came from.
- Warn, do not block, when stated calories disagree with stated macros by more
  than about 20% — that is how a transposed row gets noticed.
- Seeding uses `INSERT OR IGNORE`, so edits made here survive a restart. Say so
  on the page.

This part needs nothing from OpenCode. Do it first.

## Part 2 — Client session card · needs OpenCode step 2

`/members/<id>/plan` currently renders a timeline of everything. Replace it with
**today's session only**.

- One card per exercise: sets, reps and rest as **large single numbers**, not a
  sentence. Tick each set as it is completed.
- Show `load_note`, and the last logged load and reps for that movement so
  progression is obvious — "last time 42.5 kg × 8".
- Log what was actually done: reps and load per set, written to `set_logs`.
- Rationale is available **on tap**, not shouting. `coach_note` shows above it.
- No RPE, no tempo, no evidence grades. Those are coach language.
- The phase label — "Week 2 · Build" — is the one piece of block context to keep,
  so the member knows why this week feels heavier.
- Supersets: items sharing a `superset_group` render as one grouped card.

Members use this on a phone, standing up, mid-set. Design for that.

## Part 3 — Admin programme sheet · needs OpenCode steps 2 and 3

`/members/<id>/plan/review` currently lists items with rationale. Make it the
sheet a coach edits.

- A dense table: exercise, sets, reps, RPE, tempo, rest, load. **Every cell
  editable in place.**
- Swap an exercise, add one, remove one, reorder within the day.
- Group two items into a superset.
- Show **weekly sets per muscle** from `weekly_volume()`, with the productive
  range, and mark a muscle over or under it. This is the coach's actual decision
  tool — a bar per muscle beats a number in a list.
- Keep the approve and reject controls already there, and keep the rule that a
  blocked plan renders no approve control.

## Design constraints

- Reuse the token system in `static/styles.css` — `--accent`, `--warn`, `--bad`,
  `--good`, `--panel`, `--line`, `--muted`. Both themes must keep working.
- Density over decoration. This is a working tool.
- Every `<form method="post">` needs
  `<input type="hidden" name="csrf_token" value="{{ csrf_token() }}">`.
- Wide tables scroll inside their own container so the page never scrolls
  sideways.

## Verify visually — and actually do it

Check every screen you touch in all four before calling it done:

|  | Light | Dark |
|---|---|---|
| Desktop 1280px | ☐ | ☐ |
| Phone 375px | ☐ | ☐ |

## Tests must assert behaviour, not strings

This is the one thing to change from last time. Tests of the form
`assert "Plans & Review" in html` passed while that tab pointed at an element
that did not exist, and while the check-in box wrote rows belonging to nobody.

Every test must assert a **state change or a resolved link**:

- Logging a set creates a `set_logs` row with the right reps and load.
- Editing a cell changes the column, and marks the item `provenance = 'admin'`.
- Every tab or anchor target you render **exists on the page**.
- Deactivating a movement removes it from a newly generated plan.
- A blocked plan renders no approve control.

## Definition of done

- [ ] `python -m pytest -q` green, count above 302
- [ ] Every existing URL still resolves
- [ ] Catalogue edits persist across a restart
- [ ] A set logged on the client card appears in `set_logs`
- [ ] Weekly volume renders with its range and flags an out-of-range muscle
- [ ] All four theme/width combinations verified by screenshot
- [ ] No files changed under `services/` or in `init_db()`
- [ ] Branch pushed to origin
