# StrengthLab Plan Engine — Build Specification

Explainable workout and diet plans that a human approves before any member sees
them. Every recommendation carries the reason it exists, plans are built around
when the member actually wakes, trains and sleeps, and clinical safety gates
cannot be overridden by staff.

- **Target:** Flask + SQLite, `app.py` and `services/`
- **Baseline:** branch `chore/ci-and-hardening`, 106 passing tests
- **Companion docs:** [`tasks/opencode-backend.md`](tasks/opencode-backend.md),
  [`tasks/antigravity-frontend.md`](tasks/antigravity-frontend.md)

---

## 1. What already exists — read before writing code

A working recommendation engine with human approval is **already in this
codebase**, for supplements only. The job is to extend that proven pattern to
plans, not to invent a new one.

| Already built | Where | Reuse it for |
|---|---|---|
| Draft → review → approve/reject/edit | `recommendations_review` in `app.py` | The plan approval flow, unchanged in shape |
| Per-item reasoning fields | `member_recommendations` table | Field naming for plan items |
| Contraindication safety gate | `services/supplement_recommendation_service.safety_gate` | The hard gate — call it for plans too |
| NIH evidence data (RDA, upper limits, URLs) | `services/evidence_rules.py` | Citations attached to diet items |
| Rule scoring | `calculate_need_score` | Confidence scores on plan items |
| Health questionnaire | `member_health_profiles` table | Inputs to both the gate and the reasoning |

### Prior art — `feature/ai-plan-engine-v2`

There is an **earlier, unmerged attempt** at this feature on the remote branch
`feature/ai-plan-engine-v2` (~745 changed lines in `app.py`). Know what is on it
before you start:

- It adds `member_plan_versions` — `version_number`, `plan_status` (defaults to
  `draft`), `workout_plan_json` / `diet_plan_json`, `created_by`, `notes`.
- It adds `workout_plan_json` and `diet_plan_json` columns to `members`.
- It has **no rationale, no evidence, and no safety gate** — zero matches for
  `rationale` or `blocked_reason` in the whole branch.

**Decision: do not build on it.** It stores each plan as one JSON blob per
version, which cannot support per-item rationale, per-item editing, or per-item
evidence — the three things this feature exists to provide. The `plan_versions` +
`plan_items` split in §3 is the right shape and supersedes it.

Worth harvesting from it before it is retired: the version-history UI in
`templates/member_detail.html`, and its JSON plan prompt work as a reference for
§7.

> **This branch is also the origin of a bug already fixed on
> `chore/ci-and-hardening`.** `main` *reads* `member["diet_plan_json"]` in
> `diet_pdf()` but has no migration creating that column — the function was
> written against this branch's schema and shipped without it, so the diet PDF
> returned HTTP 500 for every member. If you ever reintroduce a column read,
> reintroduce its migration in the same commit.

### What is genuinely missing

1. **Plans have no approval gate.** Workout and diet plans are free text saved
   straight onto `members.workout_plan` / `diet_plan`. No structure, no review
   record, no reasoning.
2. **The AI is never asked to explain itself.** `ai_plan_prompt` requests
   `workout_plan, diet_plan, progress_message, safety_notes` and nothing else;
   `validate_ai_plan_data` discards anything further. Reasoning cannot survive
   the round trip.
3. **The audit table is dead.** `recommendation_reviews` is written in exactly
   one place. Approve and reject update status directly and record no actor,
   reason or timestamp.
4. **Reasons are templated, not derived.** `why_appeared` is a fixed string per
   nutrient — "vegetarian pattern *or* medications that limit absorption" — so
   it cannot say which input actually fired.
5. **No time-of-day model.** Nothing records when the member wakes, trains or
   sleeps, so nothing can be scheduled against it.

---

## 2. Non-negotiables

Four rules the implementation must hold. A change that breaks any of these is
wrong even if the tests pass.

**Rule 1 — Hard gate.** A plan blocked by clinical safety **cannot be approved
by anyone**, including an admin or owner. Enforced server side in the route, not
by hiding a button. An admin is not a clinician.

**Rule 2 — No reason, no item.** Every plan item carries a rationale. An item
without one is rejected at validation. This applies to AI output and
rule-generated items equally.

**Rule 3 — Nothing reaches a member unapproved.** Members read from the approved
plan version only. A draft or pending version is invisible to them. Generation
never writes directly to what a member sees.

**Rule 4 — Every decision is attributable.** Approve, reject and edit each write
who did it, when, and what changed.

---

## 3. Schema

Three new tables, three new columns. Follow the existing migration style in
`init_db()`: `CREATE TABLE IF NOT EXISTS`, then guarded `ALTER TABLE` for
columns, then indexes — and repair existing data before adding any constraint
(see how duplicate invoice numbers are repaired before the unique index).

### New columns on `members`

| Column | Type | Notes |
|---|---|---|
| `wake_time` | TEXT | `HH:MM`. Null means unknown — degrade, don't crash. |
| `sleep_time` | TEXT | `HH:MM`. May be past midnight; treat as next-day. |
| `workout_time` | TEXT | `HH:MM`. The member's usual training slot. |

### `plan_versions`

| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | |
| `member_id` | INTEGER | FK `members(id)` |
| `plan_type` | TEXT | `workout` \| `diet` |
| `status` | TEXT | `draft` \| `pending_review` \| `approved` \| `rejected` \| `superseded` \| `blocked` |
| `provenance` | TEXT | `rule` \| `ai` \| `admin` |
| `model` | TEXT | Model id when provenance is `ai`, else null |
| `blocked_reason` | TEXT | Non-null means permanently unapprovable — see §6 |
| `generated_at` | TEXT | |
| `reviewed_by` | INTEGER | FK `users(id)` |
| `reviewed_at` | TEXT | |
| `review_note` | TEXT | Required on reject |

Index `(member_id, plan_type, status)` — the member view queries it on every
page load.

### `plan_items`

| Column | Type | Notes |
|---|---|---|
| `plan_version_id` | INTEGER | FK, cascade delete |
| `day_label` | TEXT | e.g. `Day 1 · Push`; for diet, the weekday or `Every day` |
| `slot_time` | TEXT | `HH:MM`, derived by the circadian engine |
| `item_type` | TEXT | `exercise` \| `meal` \| `hydration` \| `supplement` \| `recovery` |
| `title` | TEXT | What the member does |
| `detail` | TEXT | Sets/reps/load, or portions/macros |
| `rationale` | TEXT NOT NULL | Why this item, for this member. Never empty. |
| `evidence_grade` | TEXT | `A`–`D`, from `evidence_rules.py` |
| `evidence_source` | TEXT | Human-readable citation |
| `source_url` | TEXT | |
| `confidence` | TEXT | `High` \| `Medium` \| `Low` |
| `position` | INTEGER | Order within the day |

### `plan_reviews`

Append-only. One row per decision: `plan_version_id`, `reviewed_by`, `action`
(`approve`|`reject`|`edit`), `note`, `before_json`, `after_json`, `created_at`.
Never updated, never deleted — this is the audit trail Rule 4 requires.

> **While you are here:** fix the existing supplement flow the same way. Approve
> and reject in `recommendations_review` must write to `recommendation_reviews`
> instead of silently updating status.

---

## 4. Circadian model

The engine builds a daily timeline from three inputs — wake, workout and sleep —
and places every meal, session and supplement against it. This is also what
makes the reasoning concrete: a time the member can check against their own day.

### Worked example

Member wakes `06:30`, trains `18:30`, sleeps `23:00`:

| Time | Item | Rationale produced |
|---|---|---|
| 06:30 | Wake | Anchor — reported by the member |
| 07:00 | Breakfast · 35 g protein | Within 30–60 min of waking. Front-loading protein supports the 131 g daily target across four feedings rather than two large ones. |
| 13:00 | Lunch · 40 g protein | Midpoint between breakfast and the pre-workout meal, keeping feedings roughly 4 hours apart. |
| 15:00 | Caffeine cut-off | 8 hours before a 23:00 bedtime. Caffeine's half-life is roughly 5–6 hours, so later intake measurably delays sleep onset. |
| 17:00 | Pre-workout meal · carb-led | 90 minutes before training — long enough to clear the stomach, close enough to fuel the session. |
| 18:30 | Training · Push A | Anchor. Evening slot, so core temperature is near peak and heavier top sets are appropriate. |
| 19:45 | Post-workout · 40 g protein | Within 60 minutes of finishing. Also the largest carb feeding of the day, placed where it is most likely to be used. |
| 21:00 | Last meal | 2 hours clear of 23:00. Eating closer to sleep worsens sleep quality and next-morning appetite control. |
| 23:00 | Sleep · 7 h 30 m target | Anchor. Above the 7-hour floor, so training volume is not reduced. |

### Rules to implement

| Rule | Condition | Effect |
|---|---|---|
| First meal | Always | wake + 30–60 min |
| Pre-workout meal | workout > 2 h after wake | workout − 90 min, carb-led |
| Fasted start | workout < 60 min after wake | Skip pre-workout meal; light carb only; full breakfast moves to post-workout |
| Post-workout feed | Always | Within 60 min of session end; largest protein and carb feeding |
| Last meal | Always | ≥ 2 h before sleep |
| Caffeine cut-off | Any caffeine item | ≥ 8 h before sleep; if training is inside that window, drop pre-workout caffeine entirely |
| Late training | workout < 3 h before sleep | Cap intensity, add a wind-down block, no stimulants |
| Early training | workout < 2 h after wake | Extend warm-up — core temperature and joint readiness are lowest on waking |
| Short sleep | sleep window < 7 h | Reduce weekly volume ~20 %, flag it in the plan, surface it to the admin |
| Missing times | Any anchor null | Fall back to 07:00 / 18:00 / 23:00, mark those items `confidence = Low`, prompt the admin to collect real times |

Put this in a new `services/circadian_service.py`. It takes the three times and
returns an ordered list of slots with a rationale string each — **it does not
touch the database**, which keeps it trivially testable.

---

## 5. Approval flow

```
draft ──► pending_review ──► approved      (member can see it)
                        └──► rejected      (note required)
                        └──► blocked       (terminal — see §6)

approved ──► superseded  (when a newer version is approved)
```

- Generating a plan creates a `draft`. It never overwrites anything a member is
  reading.
- The admin reviews item by item, editing any `title`, `detail` or `rationale`.
  An edit sets `provenance = admin` on that item and writes a `plan_reviews` row.
- Approving flips the previous `approved` version of that `plan_type` to
  `superseded` **in the same transaction**, so exactly one is live at any moment.
- Rejecting requires a note. The plan stays visible to staff as history.
- Members read the single `approved` version. If none exists, they see an honest
  empty state — "Your coach is preparing your plan" — never a draft.

**Migration.** Existing `members.workout_plan` / `diet_plan` text becomes one
`approved` `plan_versions` row per member with `provenance = admin` and a single
item carrying the original text, so nobody loses a plan on upgrade. Keep the old
columns readable for one release, then drop them.

---

## 6. The hard gate

This is the section to get exactly right. Everything else is convenience; this
is the part that protects a member.

Before a plan can move to `pending_review`, run the member's health profile
through the existing `safety_gate`. If it returns a contraindication requiring
clinician review — pregnancy or lactation, active kidney disease, active liver
disease, or a flagged medication interaction — the version is written with
`status = 'blocked'` and a populated `blocked_reason`.

**Enforcement.** The approve route returns **403** when `blocked_reason` is
non-null, *before it reads any form field*. Disabling the button in the template
is a courtesy, not the control — an admin can still post the form. There is no
override flag, no force parameter, and no role that bypasses it.

**The only way out.** A block clears when the underlying health fact changes —
the member is no longer pregnant, or a condition was recorded in error and
corrected in the questionnaire. Updating the health profile regenerates the plan
and the gate runs again on fresh data. Staff resolve a block by fixing the
record, never by overruling the gate.

Show the admin the reason plainly, alongside what would clear it:

> Blocked — active kidney disease reported. This plan includes creatine and
> electrolytes, which require renal clearance. Update the health questionnaire
> or refer to a clinician.

---

## 7. AI contract

The current prompt cannot return reasoning and the validator would drop it.
Replace both.

### Request

Extend `ai_plan_prompt` to send the derived circadian slots and demand a
rationale on every item:

```python
"requirements": [
    "Return only valid JSON matching the schema below.",
    "Every item MUST include a non-empty 'rationale' of at least 40 characters "
    "explaining why THIS item suits THIS member, referencing their goal, "
    "experience, injuries, or schedule.",
    "Place items at the supplied slot times. Do not invent times.",
    "Exercises must come from available_gym_equipment.",
    "Cite an evidence grade and source where a nutrition claim is made.",
    "Do not diagnose, treat disease, or override medical advice.",
]
```

### Response

```json
{
  "plan_type": "workout",
  "days": [{
    "day_label": "Day 1 · Push",
    "items": [{
      "slot_time": "18:30",
      "item_type": "exercise",
      "title": "Barbell bench press",
      "detail": "3 × 6–8 @ RPE 7, 2 min rest",
      "rationale": "Primary horizontal press for the stated chest and triceps goal. 6–8 reps at RPE 7 leaves 2–3 reps in reserve, appropriate while shoulder discomfort is still noted in the injury log.",
      "evidence": { "grade": "B", "source": "ACSM resistance training guidelines", "url": "https://..." },
      "confidence": "High"
    }]
  }]
}
```

### Validation — replace `validate_ai_plan_data`

- Reject the **entire response** if any item is missing `rationale`, or it is
  under 40 characters. Do not silently keep the good items — a partially
  explained plan is the failure mode this whole feature exists to prevent.
- Reject any `slot_time` not in the set the engine supplied.
- Reject any exercise not in `equipment_names()`.
- On rejection, fall back to the rule-based generator and record
  `provenance = rule` with a note explaining the AI output was refused. The
  admin sees a usable plan either way.

**Keep** the existing multi-provider fallback in `generate_ai_plans` — it
already tries each key and model in turn and degrades to rules. Only the prompt,
the schema and the validator change.

---

## 8. Explanations

A reason is only auditable if it names the input that produced it. Templated
strings fail this test — that is the flaw in the current `why_appeared`.

| | Not this | This |
|---|---|---|
| Supplement | "Vegetarian pattern *or* medications that limit absorption." | "Diet recorded as vegetarian and no B12 source in the current supplement list. Score 5/6 — vegetarian +3, low energy reported +2." |
| Meal timing | "Eat dinner earlier." | "Last meal at 21:00 — 2 hours before your 23:00 bedtime." |
| Exercise | "Good for building strength." | "Leg press instead of back squat while lower-back pain is noted in the injury log; supported back position, same quad emphasis." |

Every rationale must reference at least one of: a value from the member record,
a rule that fired with its threshold, or a named contraindication. Build them by
string composition from the actual inputs — **never pick from a fixed list keyed
on the item name**.

Surface on the member's plan, per item: the rationale, the evidence grade and
source link where one exists, and a provenance marker — `rule`, `ai · model`, or
`edited by coach`. Members trust guidance they can interrogate.

---

## 9. Build order

Numbered because each phase genuinely depends on the one before it. Every phase
ends green — run `python -m pytest` before moving on.

| Phase | Work | Depends on | Track |
|---|---|---|---|
| 1 | Schema and migration | — | Backend |
| 2 | Circadian service (pure functions) | — | Frontend track, parallel-safe |
| 3 | Rule-based structured plans | 1, 2 | Backend |
| 4 | Safety gate and approval routes | 3 | Backend |
| 5 | Admin review screen | 4 | Frontend |
| 6 | AI with mandatory reasoning | 4 | Backend |
| 7 | Member-facing plan view | 5 | Frontend |

**Phase 1 — Schema and migration.** Add the three time columns, the three
tables, the index. Migrate existing plan text into approved `plan_versions`
rows. Add wake / sleep / workout time inputs to the member add and edit forms.
Verify against a copy of a real database, not just a fresh one.

**Phase 2 — Circadian service.** `services/circadian_service.py`, pure
functions, no database. Implement every rule in §4 including the missing-anchor
fallback. Test this hardest — it is the easiest to get subtly wrong and the
easiest to test.

**Phase 3 — Rule-based structured plans.** Rewrite `generate_rule_based_plans`
to emit `plan_items` against circadian slots, each with a composed rationale. No
AI yet — the whole feature must work with zero API keys configured.

**Phase 4 — Safety gate and approval.** Wire `safety_gate` into generation; set
`blocked` and `blocked_reason`. Approve / reject / edit routes, each writing
`plan_reviews`. Enforce the 403 in the route — **write that test first**. Point
the member view at the approved version only.

**Phase 5 — Admin review screen.** Item-by-item review: title, detail,
rationale, evidence, confidence, provenance. Blocked plans show the reason and
what would clear it, with no approve control. Bulk approve a day; edit any
single item inline.

**Phase 6 — AI with mandatory reasoning.** New prompt schema, new validator,
all-or-nothing rejection. Record `provenance` and `model`; fall back to rules on
refusal. AI output always lands as `draft` — never auto-approved, under any
configuration.

**Phase 7 — Member-facing plan.** Daily timeline view with each item's rationale
expandable. Evidence links where present; provenance marker per item. Fix the
supplement audit gap from §3 in the same pass.

---

## 10. Tests

The suite is at 106 and green — keep it that way. These cases must exist before
the feature is done.

| Area | Must prove |
|---|---|
| Hard gate | Posting approve on a blocked plan returns 403 — as admin *and* as owner. The plan stays blocked. No parameter combination approves it. |
| Visibility | A member requesting their plan while only a draft exists sees the empty state, never draft content. |
| Supersede | Approving a second plan leaves exactly one approved version for that member and type. |
| Audit | Approve, reject and edit each append a `plan_reviews` row with the acting user. Reject without a note fails. |
| AI validation | A response with one item missing a rationale is rejected whole, and the fallback plan is rule-based. |
| Circadian | Each rule in §4 gets a case, including fasted start, late training, short sleep, and all-anchors-null. |
| Rationale | Every generated item has a non-empty rationale referencing at least one member input. |
| Migration | An existing member with plan text ends up with one approved version containing that text. |

Follow the existing conventions in `tests/`: a temporary database via
`GYM_DB_PATH`, `DISABLE_PAYMENT_AUTOMATION=1`, and CSRF tokens pulled from a
rendered form via `conftest.csrf_for`.

> **Gotcha:** a fixture needing both an admin and another signed-in role must
> build its own `test_client()`. The shared `client` fixture collapses two
> logins into one session — see `trainer_client` in
> `tests/test_plans_and_services.py`.

---

## 11. Out of scope

Named so they do not creep in mid-build.

- **Clinician accounts.** The gate refers out; it does not add a clinician role
  or an in-app clearance workflow.
- **Wearable or sleep-tracker import.** Times are self-reported for now. The
  schema does not preclude it later.
- **Per-meal photo logging and calorie scanning.** Different feature, different
  scope.
- **Changing the supplement engine's scoring.** Only its audit gap and its
  templated reasons are in scope.
- **Splitting `app.py` into blueprints.** Worth doing, but not tangled into this.
