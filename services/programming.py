"""Coach-grade prescription: what to do on each lift, and how it changes weekly.

The rule engine previously gave every exercise the same line - same sets, reps,
RPE and rest whether it was a leg press or a lateral raise - and described a
single week with no progression. This module supplies the two things a coach
actually provides: a prescription matched to the movement, and a block that
tells the member what changes next week.

Nothing here touches the database or Flask, so every rule is cheap to test.
"""

# Movement roles. Prescription follows the role, not the exercise name, so an
# exercise the gym adds later still gets a sensible default from its keywords.
COMPOUND = "compound"
ISOLATION = "isolation"
CORE = "core"
CONDITIONING = "conditioning"

_COMPOUND_HINTS = (
    "press", "squat", "deadlift", "row", "pulldown", "chin-up", "pull-up",
    "dip", "lunge", "split squat", "leg press", "hip thrust",
)
_ISOLATION_HINTS = (
    "curl", "fly", "lateral raise", "extension", "calf raise", "pec deck",
    "kickback", "pullover", "shrug",
)
_CORE_HINTS = ("raise stand", "knee raise", "leg raise", "plank", "hanging")
_CONDITIONING_HINTS = ("treadmill", "cycle", "row erg", "walk", "conditioning", "bike")


def classify_exercise(name):
    lowered = (name or "").lower()
    for hint in _CONDITIONING_HINTS:
        if hint in lowered:
            return CONDITIONING
    for hint in _CORE_HINTS:
        if hint in lowered:
            return CORE
    # Isolation is checked before compound: "leg extension" contains neither a
    # compound hint nor ambiguity, but "preacher curl" must not match "press".
    for hint in _ISOLATION_HINTS:
        if hint in lowered:
            return ISOLATION
    for hint in _COMPOUND_HINTS:
        if hint in lowered:
            return COMPOUND
    return COMPOUND


# Goal shapes the rep range and rest; role shapes tempo and set count.
_GOAL_SCHEMES = {
    "strength": {COMPOUND: ("4-5", "3-5"), ISOLATION: ("3", "8-10")},
    "hypertrophy": {COMPOUND: ("3-4", "6-10"), ISOLATION: ("3", "10-15")},
    "endurance": {COMPOUND: ("2-3", "12-15"), ISOLATION: ("2-3", "15-20")},
}

_REST = {
    "strength": {COMPOUND: "3-5 min", ISOLATION: "90 sec"},
    "hypertrophy": {COMPOUND: "2-3 min", ISOLATION: "60-90 sec"},
    "endurance": {COMPOUND: "60-90 sec", ISOLATION: "45-60 sec"},
}

_TEMPO = {
    COMPOUND: "3-1-1-0 (3 s lower, 1 s pause, drive up)",
    ISOLATION: "2-0-1-1 (2 s lower, squeeze 1 s at the top)",
    CORE: "controlled, no swing",
    CONDITIONING: "steady, conversational pace",
}


def goal_bucket(goal_text):
    """Map a free-text member goal onto a training intent."""
    lowered = (goal_text or "").lower()
    if any(word in lowered for word in ("strength", "strong", "power", "1rm", "lift heavy")):
        return "strength"
    if any(word in lowered for word in ("endurance", "stamina", "conditioning", "fitness", "tone")):
        return "endurance"
    return "hypertrophy"


# A four-week accumulation block with a planned deload. Intensity climbs while
# volume holds, then week 4 backs both off so adaptation can surface.
BLOCK_WEEKS = (
    {
        "week": 1,
        "name": "Week 1 · Introduce",
        "rpe": "RPE 6-7 (4-3 reps in reserve)",
        "set_modifier": 0,
        "focus": "Establish loads and technique. Finish every set feeling you had more in you.",
    },
    {
        "week": 2,
        "name": "Week 2 · Build",
        "rpe": "RPE 7-8 (3-2 reps in reserve)",
        "set_modifier": 1,
        "focus": "Same loads, one extra set on the main lifts. Volume is the driver this week.",
    },
    {
        "week": 3,
        "name": "Week 3 · Push",
        "rpe": "RPE 8-9 (2-1 reps in reserve)",
        "set_modifier": 1,
        "focus": "Heaviest week. Add load where week 2 felt controlled; keep technique identical.",
    },
    {
        "week": 4,
        "name": "Week 4 · Deload and re-test",
        "rpe": "RPE 5-6 (well short of failure)",
        "set_modifier": -1,
        "focus": "Cut sets and load by roughly 40%. Re-test one main lift at the end of the week.",
    },
)


def progression_rule(role, goal):
    """The concrete condition under which the member adds load."""
    bucket = goal_bucket(goal)
    if role == CONDITIONING:
        return "Add 1-2 minutes or a small incline once the session feels conversational throughout."
    if role == CORE:
        return "Add 2-3 reps per set before adding any external load."
    if bucket == "strength":
        return ("Add 2.5 kg to the bar once you complete every prescribed set at the top of the "
                "rep range with 2 reps still in reserve.")
    if bucket == "endurance":
        return ("Add reps first. Once you reach the top of the range on all sets, add 2.5 kg and "
                "return to the bottom of the range.")
    return ("Double progression: add reps until every set hits the top of the range, then add "
            "2.5 kg (5 kg on leg press) and start again at the bottom.")


def prescribe(exercise, goal, week=1):
    """The full prescription for one exercise in one week of the block."""
    role = classify_exercise(exercise)
    bucket = goal_bucket(goal)
    week_plan = next((w for w in BLOCK_WEEKS if w["week"] == week), BLOCK_WEEKS[0])

    if role in (CORE, CONDITIONING):
        sets, reps = ("2-3", "12-20") if role == CORE else ("1", "10-20 min")
        rest = "45-60 sec" if role == CORE else "n/a"
    else:
        scheme_role = ISOLATION if role == ISOLATION else COMPOUND
        sets, reps = _GOAL_SCHEMES[bucket][scheme_role]
        rest = _REST[bucket][scheme_role]
        sets = _apply_set_modifier(sets, week_plan["set_modifier"])

    return {
        "role": role,
        "sets": sets,
        "reps": reps,
        "rpe": week_plan["rpe"],
        "tempo": _TEMPO[role],
        "rest": rest,
        "progression": progression_rule(role, goal),
        "week_focus": week_plan["focus"],
    }


def _apply_set_modifier(sets, modifier):
    """Shift a '3-4' style set range by the week's modifier, floored at 1."""
    if not modifier:
        return sets
    parts = [int(p) for p in sets.split("-") if p.strip().isdigit()]
    if not parts:
        return sets
    shifted = [max(1, p + modifier) for p in parts]
    return "-".join(str(p) for p in dict.fromkeys(shifted))


def format_prescription(prescription):
    """One line a member can read on the gym floor."""
    if prescription["role"] == CONDITIONING:
        return f"{prescription['reps']} at {prescription['tempo']}."
    return (
        f"{prescription['sets']} sets × {prescription['reps']} reps · {prescription['rpe']} · "
        f"tempo {prescription['tempo']} · rest {prescription['rest']}."
    )


# --- diet swaps -------------------------------------------------------------

# Each protein source with alternatives at a comparable protein cost. A plan a
# member cannot eat is a plan they abandon, so every meal should name a way out.
_PROTEIN_SWAPS = {
    "paneer": ["tofu 180 g", "tempeh 150 g", "curd/greek yoghurt 300 g"],
    "chicken": ["fish 150 g", "eggs 4", "paneer 150 g", "soya chunks 60 g dry"],
    "eggs": ["paneer 120 g", "tofu 180 g", "curd 300 g"],
    "whey": ["plant protein 1 scoop", "curd 300 g", "sattu 40 g"],
    "fish": ["chicken 150 g", "eggs 4", "tofu 180 g"],
    "curd": ["greek yoghurt 200 g", "buttermilk 400 ml", "paneer 100 g"],
    "soya": ["rajma 150 g cooked", "chana 150 g cooked", "tofu 180 g"],
    "sprouts": ["chana 150 g cooked", "moong dal 150 g cooked", "tofu 150 g"],
    "peanuts": ["almonds 20 g", "walnuts 20 g", "pumpkin seeds 25 g"],
    "almonds": ["peanuts 25 g", "walnuts 20 g", "sunflower seeds 25 g"],
    "milk": ["lactose-free milk 250 ml", "soya milk 250 ml", "curd 200 g"],
}

_CARB_SWAPS = {
    "rice": ["roti 2", "poha 80 g dry", "quinoa 60 g dry"],
    "roti": ["rice 60 g dry", "oats 60 g", "millet roti 2"],
    "oats": ["poha 80 g", "dalia 60 g", "rice flakes 70 g"],
    "banana": ["apple 1 with 5 g honey", "dates 3", "mango 100 g"],
    "potato": ["sweet potato 200 g", "rice 50 g dry", "roti 2"],
}

_VEGETARIAN_BLOCKED = ("chicken", "fish", "egg", "mutton", "prawn")


def _excluded(term, exclusions, dietary_style):
    lowered = term.lower()
    if any(x and x.lower() in lowered for x in exclusions):
        return True
    style = (dietary_style or "").lower()
    if any(word in style for word in ("vegan", "vegetarian")):
        if any(block in lowered for block in _VEGETARIAN_BLOCKED):
            return True
    if "vegan" in style and any(word in lowered for word in ("paneer", "curd", "milk", "whey", "yoghurt", "egg")):
        return True
    return False


def swaps_for(ingredients, exclusions=(), dietary_style=""):
    """Alternatives for the foods in a meal, filtered by what the member avoids.

    Returns a list of "source → alternative, alternative" strings, at most three,
    so the line stays readable on a phone.
    """
    lowered = (ingredients or "").lower()
    found = []
    for table in (_PROTEIN_SWAPS, _CARB_SWAPS):
        for source, options in table.items():
            if source not in lowered:
                continue
            usable = [o for o in options if not _excluded(o, exclusions, dietary_style)]
            if usable:
                found.append(f"{source} → {', '.join(usable[:3])}")
    return found[:3]
