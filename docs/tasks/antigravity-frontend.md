# Task — Antigravity · Circadian engine + UI track

**Branch:** `feat/plan-engine-ui`
**Spec:** [`../plan-engine-spec.md`](../plan-engine-spec.md) — read it in full first
**Phases:** 2 → 5 → 7
**Do not touch:** `init_db()`, or the approval/generation routes (the OpenCode
track owns those)

---

## Why you have this track

Phase 2 is pure logic you can start immediately in parallel. Phases 5 and 7 are
screens that need to be *looked at* — the browser tooling in Antigravity is the
right instrument for verifying them in both light and dark themes and at phone
width, which matters because members use this on a phone.

## Before you start — prior art

`feature/ai-plan-engine-v2` has a plan version-history UI in
`templates/member_detail.html` worth reading before you build Phase 5. Its data
model is superseded (spec §1 "Prior art") but its screen layout is a reasonable
starting point.

## Setup

```bash
cd /Users/shubhamlandge/Documents/antigravity/Strenthlab
git checkout chore/ci-and-hardening
git checkout -b feat/plan-engine-ui
source .venv/bin/activate
python -m pytest -q          # must print 106 passed before you start
PORT=5001 python app.py      # http://localhost:5001 — admin / admin123
```

> Port 5001, not 5000 — macOS AirPlay Receiver holds 5000 and returns a
> confusing 403 that is not your app.

## Order of work

### Phase 2 — Circadian service — start now, blocks nothing
Spec §4. Create `services/circadian_service.py`.

```python
def build_day_slots(wake_time, workout_time, sleep_time) -> list[dict]:
    """Returns ordered slots: {slot_time, item_type, purpose, rationale}."""
```

- **Pure functions, no database imports.** The backend track is coding against
  this signature, so land it early and do not change it without telling them.
- Implement all ten rules in the spec §4 table, including the missing-anchor
  fallback (07:00 / 18:00 / 23:00, `confidence = Low`).
- Handle a `sleep_time` past midnight as next-day.
- Each slot carries a rationale naming the actual times — "2 hours clear of your
  23:00 bedtime", not "eat earlier".
- Test this hardest. It is pure, so every rule and boundary is cheap to cover:
  fasted start, late training, short sleep, all anchors null, midnight wrap.

### Phase 5 — Admin review screen — needs backend Phase 4
Spec §5, §6. Extend the pattern already in `templates/recommendations_review.html`.

- Item-by-item: title, detail, rationale, evidence grade + source link,
  confidence, provenance marker.
- Editing any field inline; each edit marks that item `provenance = admin`.
- Bulk "approve this day".
- **Blocked plans:** show `blocked_reason` prominently and *what would clear it*.
  Render **no approve control at all** — the server also returns 403, but the
  screen should never offer an action that cannot succeed.
- Reuse the existing `.notice` / `.pill` classes and the CSS custom properties
  already in `static/styles.css`. Do not introduce a second design language.

### Phase 7 — Member plan view — needs Phase 5
Spec §8. The member's daily timeline.

- Vertical timeline ordered by `slot_time`, times in `tabular-nums`.
- Each item's rationale is expandable — visible on demand, not shouting.
- Evidence grade and source link where present; provenance marker per item.
- No approved version yet → honest empty state ("Your coach is preparing your
  plan"). **Never render draft content to a member.**
- Fix the supplement audit gap from spec §3 in this pass if the backend track
  has not already.

## Verify visually, not just by test

For Phases 5 and 7, check each screen in **all four** combinations before calling
it done:

|  | Light | Dark |
|---|---|---|
| Desktop 1280px | ☐ | ☐ |
| Phone 375px | ☐ | ☐ |

Members are on phones. The admin review screen is dense — confirm nothing
overlaps or overflows horizontally at 375px.

## Definition of done

- [ ] `python -m pytest -q` green, count above 106
- [ ] Every circadian rule in spec §4 has a test, including boundaries
- [ ] Blocked plans render no approve control
- [ ] A member with only a draft sees the empty state
- [ ] All four theme/width combinations verified by screenshot
- [ ] No changes to `init_db()` or the approval routes

## Conventions

- Every `<form method="post">` needs
  `<input type="hidden" name="csrf_token" value="{{ csrf_token() }}">` or the
  request is rejected with 400.
- Money renders through `{{ money(value) }}` for Indian digit grouping.
- Colours come from the CSS custom properties in `static/styles.css`
  (`--accent`, `--warn`, `--bad`, …) so both themes keep working.
