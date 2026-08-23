# Task — OpenCode · Backend track

**Branch:** `feat/plan-engine-backend`
**Spec:** [`../plan-engine-spec.md`](../plan-engine-spec.md) — read it in full first
**Phases:** 1 → 3 → 4 → 6
**Do not touch:** `templates/`, `static/` (the Antigravity track owns those)

---

## Why you have this track

It is entirely Python, entirely testable from the terminal, and needs no browser
to verify. Every phase is provable with `pytest`.

## Setup

```bash
cd /Users/shubhamlandge/Documents/antigravity/Strenthlab
git checkout chore/ci-and-hardening
git checkout -b feat/plan-engine-backend
source .venv/bin/activate
python -m pytest -q          # must print 106 passed before you start
```

## Order of work

### Phase 1 — Schema and migration
Spec §3. Add three columns to `members`, create `plan_versions`, `plan_items`,
`plan_reviews`, add the index.

- Follow the existing migration style in `init_db()`: `CREATE TABLE IF NOT
  EXISTS`, guarded `ALTER TABLE`, then indexes.
- Copy the pattern used for the invoice-number unique index — it repairs
  existing duplicate data *before* creating the constraint, so upgrading a live
  database cannot fail halfway. Do the same for anything you constrain.
- Migrate existing `members.workout_plan` / `diet_plan` text into one `approved`
  `plan_versions` row per member (spec §5, "Migration"). Nobody loses a plan.
- Test the migration against a **copy of `gym_manager.db`**, not only a fresh
  database.

### Phase 2 is not yours
`services/circadian_service.py` is being written on the other track. Code against
this interface and stub it locally until it lands:

```python
def build_day_slots(wake_time, workout_time, sleep_time) -> list[dict]:
    """Returns ordered slots: {slot_time, item_type, purpose, rationale}."""
```

### Phase 3 — Rule-based structured plans
Spec §4, §8. Rewrite `generate_rule_based_plans` to emit `plan_items` placed at
circadian slots, each with a **composed** rationale.

- Build rationales by string composition from actual member values. Never pick
  from a fixed list keyed on item name — that is the existing `why_appeared` bug
  the spec calls out (§1.4, §8).
- Zero API keys configured must still produce a complete, fully explained plan.

### Phase 4 — Safety gate and approval
Spec §5, §6. **Write the 403 test first**, before the route exists.

- Wire the existing `safety_gate` into generation; set `status='blocked'` and
  `blocked_reason`.
- Approve / reject / edit routes, each appending a `plan_reviews` row.
- The approve route returns 403 when `blocked_reason` is non-null, **before
  reading any form field**. No override flag, no force parameter, no role that
  bypasses. Test it as admin *and* as owner.
- Approving supersedes the previous approved version **in the same transaction**
  — use the `transaction()` helper in `app.py`, not bare `execute()` calls.
- Point the member-facing query at `status='approved'` only.

### Phase 6 — AI with mandatory reasoning
Spec §7. New prompt schema, new validator.

- Reject the **entire** AI response if any item lacks a rationale or it is under
  40 characters. Do not keep the good items.
- Fall back to the rule-based generator on rejection, recording why.
- AI output always lands as `draft`. There must be no configuration in which it
  auto-approves.
- Keep the existing multi-provider fallback in `generate_ai_plans` intact.

## Also fix while you are in here
`recommendations_review` approve/reject currently update status directly and
write nothing to `recommendation_reviews`. Make them append audit rows (spec §3).

## Definition of done

- [ ] `python -m pytest -q` green, and the count is above 106
- [ ] Every test in spec §10 that is backend-shaped exists and passes
- [ ] Migration verified against a copy of the real `gym_manager.db`
- [ ] The app boots and serves: `PORT=5001 python app.py`
- [ ] No files changed under `templates/` or `static/`
- [ ] Commits are scoped per phase, not one large commit

## Conventions

- Tests: temporary DB via `GYM_DB_PATH`, `DISABLE_PAYMENT_AUTOMATION=1`, CSRF
  tokens via `conftest.csrf_for`.
- A fixture needing two signed-in roles must build its own `test_client()` — the
  shared `client` fixture collapses two logins into one session. See
  `trainer_client` in `tests/test_plans_and_services.py`.
- Match the surrounding code's comment density and naming. Comments explain
  *why*, not *what*.
