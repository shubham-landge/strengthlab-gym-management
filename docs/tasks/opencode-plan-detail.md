# Task — OpenCode · Structured prescriptions

**Branch:** `feat/plan-detail`
**Base:** `main` (302 passing tests)
**Read first:** [`SHARED-CONTRACT.md`](SHARED-CONTRACT.md) — column names and the
`muscle_group` list are fixed there. Antigravity is building screens against
those exact fields in parallel.

---

## Work in a separate git worktree

```bash
cd /Users/shubhamlandge/Documents/antigravity/Strenthlab
git worktree add ../strengthlab-backend -b feat/plan-detail main
cd ../strengthlab-backend
python3 -m venv .venv && ./.venv/bin/pip install -q -r requirements.txt -r requirements-dev.txt
./.venv/bin/python -m pytest -q     # must print 302 passed
```

**Never run `git checkout`, `git reset --hard` or `git clean` in the original
directory.** On the last run a `reset --hard` there destroyed another agent's
uncommitted work. **Never delete a `.venv` you did not create** — that has
already cost this project two rebuilds.

Create your own venv in the worktree as above. Do not symlink the main one.

---

## The problem

Every prescription is one prose string in `plan_items.detail`:

```
"3-4 sets × 6-10 reps · RPE 6-7 · tempo 3-1-1-0 · rest 2-3 min."
```

An admin cannot change the sets without editing a sentence, weekly volume cannot
be totalled because sets are not a number, and a client card and a coach sheet
cannot both be rendered because there are no fields to render differently.

## Order of work

### 1 — Schema and backfill
Add the columns and `set_logs` exactly as specified in the shared contract.

- Follow the existing migration style in `init_db()`: `CREATE TABLE IF NOT
  EXISTS`, guarded `ALTER TABLE`, then indexes.
- **Backfill existing rows** by parsing the current `detail` strings. They follow
  a known shape — `N sets × A-B reps · RPE X-Y · tempo T · rest R`. Anything that
  will not parse keeps its `detail` and gets null fields; do not guess.
- Test against a copy of the real `gym_manager.db`, and seed your own legacy
  fixture into that copy rather than relying on what it happens to contain.

### 2 — Generator emits fields, not prose
`generate_rule_based_plans` already computes a prescription per movement through
`services/programming.py`. Write those values into the new columns instead of
formatting them into a sentence. `detail` becomes derived from the fields.

- `set_count` must be populated for every `item_type='exercise'` row — volume
  totals depend on it.
- `muscle_group` comes from `exercise_library.primary_muscle`, which the content
  library already carries. Map it onto the closed list in the contract.
- Conditioning rows get `reps` as a duration and null `rest_seconds`. They must
  never receive a set-and-rep prescription — the legacy data still contains
  `Cycle: 3-4 sets x 8-12 reps`, which is what this is fixing.

### 3 — Weekly volume
Implement `weekly_volume(member_id, plan_version_id)` with the signature in the
contract. Antigravity renders it; you decide the ranges.

Coaches count hard sets per muscle per week against landmarks — roughly 10-20 is
the productive range for most muscles in trained lifters, larger groups tolerate
more. Source the ranges you choose in a comment.

### 4 — Progression reads what actually happened
Once `set_logs` has rows, the progression rule stops being a sentence the member
applies themselves. Add a function that proposes the next load from the last
logged sets for that item, following the rule already in
`programming.progression_rule`.

### 5 — Diet checks
The ISSN position stand gives per-serving protein of 0.25 g/kg or 20-40 g
absolute, distributed every 3-4 hours. The generator currently sets a daily
target and never checks either.

- Flag a meal whose protein dose is below that range for the member's weight.
- Flag a gap between feedings longer than 4 hours.
- Surface both as a plan-level note the admin sees, not a hard block.

## Definition of done

- [ ] `python -m pytest -q` green, count above 302
- [ ] Backfill verified against a copy of the real database
- [ ] No `item_type='exercise'` row has a null `set_count`
- [ ] No conditioning row has `rest_seconds` or a set-and-rep `reps` value
- [ ] `weekly_volume` returns the documented shape
- [ ] `coach_note` survives a regeneration
- [ ] No files changed under `templates/` or `static/`
- [ ] Branch pushed to origin
- [ ] Commits scoped per step

## Conventions

- Tests: temporary DB via `GYM_DB_PATH`, `DISABLE_PAYMENT_AUTOMATION=1`, CSRF via
  `conftest.csrf_for`.
- Assert state changes, not that a string appears somewhere.
- A fixture needing two signed-in roles builds its own `test_client()`.
- Comments explain *why*, not *what*.
