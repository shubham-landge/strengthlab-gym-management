# Task — Antigravity · Admin UX: daily workflow + information architecture

**Branch:** `feat/admin-ux`
**Base:** `main` (currently 242 passing tests)
**Owns:** `templates/`, `static/styles.css`, and read-only view routes
**Does NOT own:** `services/`, `init_db()`, plan generation, the approval routes,
`ai_settings`. Claude is working on plan content in parallel and owns those.

---

## Work in a separate worktree — this is not optional

Last time both agents shared one working directory and it caused two failures
that were invisible to everyone: an untracked file leaked across branches so
each agent believed its branch was green when it was not, and a `git reset
--hard` destroyed the other agent's uncommitted work. Use:

```bash
cd /Users/shubhamlandge/Documents/antigravity/Strenthlab
git worktree add ../strengthlab-ux -b feat/admin-ux main
cd ../strengthlab-ux
ln -s ../Strenthlab/.venv .venv
python -m pytest -q          # must print 242 passed before you start
PORT=5002 ./.venv/bin/python app.py
```

Port 5002, not 5001 — Claude is running the app on 5001, and 5000 is macOS
AirPlay. Never `git checkout` or `git reset` in the original directory.

---

## The goal

Two things, in this order. **Daily workflow speed first**, because it pays off
immediately and does not require moving anything.

The user is a gym owner/admin in India running a single-location gym with a
few hundred members. They are on a laptop at reception, and on a phone on the
gym floor. Assume interruptions: they will start a task, get pulled away, and
come back.

---

## Part 1 — Daily workflow speed

### Find out what the day actually is before designing it

These are the real daily jobs, in rough frequency order:

1. **Check members in** — currently `/attendance`, a dropdown plus a button, one
   member at a time.
2. **Take a payment** — currently `/payments`, open drawer, pick member, fill
   seven fields.
3. **Chase dues** — currently the reminder queue, one WhatsApp click per member.
4. **Approve plans** — `/members/<id>/plan/review`, reachable only by knowing
   the URL or going through the member.
5. **Add a member** — a long single form on `/members`.

### What to build

- **A real "today" queue on the dashboard.** Not four stat cards that link to
  four screens — an action list: who is due in, who owes money, which plans are
  waiting for approval, which equipment is due service. Each row does the thing
  inline where that is possible.
- **Check-in without leaving the dashboard.** Search-as-you-type over members,
  Enter checks them in. This is the single most repeated action in the app.
- **Cut the payment form down.** Amount and method are the only fields that
  change most of the time; plan, dates and invoice can be derived and shown as a
  confirmable default rather than seven empty inputs.
- **Bulk actions that already exist should be reachable.** `payment_batch_action`
  supports batches; the UI mostly does not use it.
- Keyboard: `/` focuses search, `Esc` closes any drawer. Do not invent a large
  shortcut scheme — two that work beat ten that are undiscoverable.

### What NOT to do

Do not add a second dashboard. Improve the one at `/`.

---

## Part 2 — Information architecture

### The problem

The sidebar has 12 destinations and no grouping. A member's information is
spread across Members, Assignments, Attendance, Payments, plan review, and
recommendations — six places for one person.

### What to build

- **Group the sidebar** into sections that match how the work is thought about,
  e.g. *Today* (dashboard, check-in), *People* (members, trainers, assignments),
  *Money* (payments, reports), *Programme* (plans, supplements, content), *Setup*
  (equipment, AI settings). Names are yours to choose — these are a starting
  point, not a specification.
- **Make the member record the hub.** `/members/<id>` should be where a member's
  plan, payments, attendance, progress and recommendations are reachable as tabs
  or sections, rather than five separate destinations that each filter down to
  one person. The separate list screens stay — they are how you find someone —
  but once you are on a person you should not have to leave.
- **Surface the plan review.** Plans waiting for approval are currently
  invisible unless you know the URL. They belong in the today queue and on the
  member record.

### Constraint

Keep every existing URL working. Other screens, the tests, and any bookmark the
user has all rely on them. Add new routes if you need them; do not rename or
remove existing ones.

---

## Design constraints

- **Reuse the existing token system** in `static/styles.css` — `--accent`,
  `--warn`, `--bad`, `--good`, `--panel`, `--line`, `--muted`. Both light and
  dark themes must keep working. Do not introduce a second design language or a
  CSS framework.
- **Phone matters.** The owner uses this on the gym floor. Every screen you
  touch must work at 375px: no horizontal page scroll, nothing behind the fixed
  bottom nav, tap targets not smaller than the existing buttons.
- **Density over decoration.** This is a working tool, used many times a day, not
  a landing page. Prefer information the admin needs over whitespace and
  illustration. Avoid emoji as section markers.
- **Every `<form method="post">` needs**
  `<input type="hidden" name="csrf_token" value="{{ csrf_token() }}">`
  or the request is rejected with 400.
- Money renders through `{{ money(value) }}` for Indian digit grouping.

---

## Verify visually — this was skipped last time and it mattered

For every screen you change, check all four before calling it done:

|  | Light | Dark |
|---|---|---|
| Desktop 1280px | ☐ | ☐ |
| Phone 375px | ☐ | ☐ |

Last time the fixed bottom nav wrapped to two rows at 375px and covered page
content including an approve button. No test caught it. Only looking did.

---

## Definition of done

- [ ] `python -m pytest -q` green, count at or above 242
- [ ] Every existing URL still resolves
- [ ] Check-in achievable from the dashboard without a page load per member
- [ ] Plans awaiting approval visible without knowing the URL
- [ ] A member's plan, payments and attendance reachable from their record
- [ ] All four theme/width combinations verified by screenshot
- [ ] No files changed under `services/`, and none of the routes listed as
      not-yours

## Conventions

- Tests: temporary DB via `GYM_DB_PATH`, `DISABLE_PAYMENT_AUTOMATION=1`, CSRF
  tokens via `conftest.csrf_for`.
- A fixture needing two signed-in roles must build its own `test_client()` — the
  shared `client` fixture collapses two logins into one session.
- Assert against real generated data, not monkeypatched query results. A test
  that patches `query_one` to fabricate a row proves nothing about the system.
- Commit per part, not one large commit.
