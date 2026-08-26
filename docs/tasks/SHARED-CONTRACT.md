# Shared contract — read before either track starts

Both tracks read and write the same columns. Last time a shared field was
specified by name but not by value, the two sides each invented a reasonable
vocabulary, and seven tests failed the moment the branches met. This file is the
single source of truth for anything both tracks touch. **Changing anything here
means telling the other track.**

## New columns on `plan_items`

| Column | Type | Exact meaning | Example |
|---|---|---|---|
| `sets` | TEXT | Prescribed sets, as displayed. May be a range. | `"4"`, `"3-4"` |
| `set_count` | INTEGER | Top of the `sets` range, for volume totals. Never null for `item_type='exercise'`. | `4` |
| `reps` | TEXT | Prescribed reps, as displayed. For conditioning, a duration. | `"6-10"`, `"10-20 min"` |
| `rpe` | TEXT | Rate of perceived exertion range. Admin view only. | `"7-8"` |
| `tempo` | TEXT | Four-digit tempo. Admin view only. | `"3-1-1-0"` |
| `rest_seconds` | INTEGER | Rest between sets, in seconds. Null for conditioning. | `150` |
| `load_note` | TEXT | How to pick the weight. Free text. | `"70% 1RM"`, `"bodyweight"` |
| `muscle_group` | TEXT | Lowercase, singular, from the list below. What volume groups by. | `"chest"` |
| `superset_group` | TEXT | Label shared by paired items. Null for straight sets. | `"A1"`, `"A2"` |
| `week` | INTEGER | Which week of the block this row belongs to. Default `1`. | `2` |
| `coach_note` | TEXT | Written by staff, shown to the client. **Generation must never overwrite it.** | |

`detail` stays, and becomes **derived** — rendered from the fields above for
screens that have not been updated yet. Never parse it.

### `muscle_group` — closed list

```
chest, back, lats, front delts, side delts, rear delts, biceps, triceps,
quads, hamstrings, glutes, calves, abs, lower back, full body
```

Use exactly these strings. `full body` is for conditioning. If a movement needs
a group not on this list, add it here first and tell the other track.

## New table `set_logs`

| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | |
| `plan_item_id` | INTEGER | FK `plan_items(id)`, cascade delete |
| `member_id` | INTEGER | FK `members(id)` |
| `set_number` | INTEGER | 1-based |
| `reps_done` | INTEGER | |
| `load_kg` | REAL | Null for bodyweight |
| `rpe_reported` | REAL | Null if not asked |
| `logged_at` | TEXT | ISO timestamp |

Index `(member_id, plan_item_id)`.

## Helper both tracks use

Backend provides, UI consumes:

```python
def weekly_volume(member_id, plan_version_id):
    """Hard sets per muscle group for one plan version.

    Returns [{"muscle_group": str, "sets": int, "min": int, "max": int}, ...]
    where min/max are the productive range for that muscle (10-20 for most,
    wider for large groups). Sorted by muscle_group.
    """
```

## Ownership

| Track | Owns | Must not touch |
|---|---|---|
| OpenCode | `app.py` routes and generation, `services/`, `init_db()` | `templates/`, `static/` |
| Antigravity | `templates/`, `static/styles.css`, read-only view routes | `services/`, `init_db()`, generation and approval routes |

Both add tests under `tests/`. Neither edits the other's test files.
