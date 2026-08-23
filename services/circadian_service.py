"""
Circadian timing service for StrengthLab.

Pure functional module for building daily timeline slots based on member circadian anchors:
wake_time, workout_time, and sleep_time.

No database dependencies.
"""
from typing import Dict, List, Optional, Any


def parse_time(time_str: Optional[str]) -> Optional[int]:
    """Parse HH:MM time string into minutes from 00:00 midnight."""
    if not time_str:
        return None
    try:
        parts = time_str.strip().split(":")
        hours = int(parts[0])
        minutes = int(parts[1])
        return hours * 60 + minutes
    except (ValueError, IndexError):
        return None


def format_time(minutes: int) -> str:
    """Format minutes from 00:00 midnight into HH:MM string (00:00 to 23:59)."""
    norm = minutes % 1440
    hours = norm // 60
    mins = norm % 60
    return f"{hours:02d}:{mins:02d}"


def calculate_sleep_duration_minutes(sleep_mins: int, wake_mins: int) -> int:
    """
    Calculate sleep duration in minutes when sleeping at sleep_mins and waking at wake_mins.
    Handles sleep times past midnight.
    """
    if wake_mins >= sleep_mins:
        duration = wake_mins - sleep_mins
    else:
        duration = (1440 - sleep_mins) + wake_mins
    return duration


def build_day_slots(
    wake_time: Optional[str],
    workout_time: Optional[str],
    sleep_time: Optional[str]
) -> List[Dict[str, Any]]:
    """
    Returns ordered daily circadian slots based on wake_time, workout_time, and sleep_time.
    Each slot carries: {slot_time, item_type, title, purpose, rationale, confidence}.

    Implements all 10 rules from Spec §4:
    1. First meal: wake + 30-60 min
    2. Pre-workout meal: workout > 2h after wake -> workout - 90 min, carb-led
    3. Fasted start: workout < 60 min after wake -> skip pre-workout meal, light carb only, breakfast post-workout
    4. Post-workout feed: within 60 min of session end; largest protein & carb feeding
    5. Last meal: >= 2h before sleep
    6. Caffeine cut-off: >= 8h before sleep; if workout inside that window, drop pre-workout caffeine
    7. Late training: workout < 3h before sleep -> cap intensity, wind-down block, no stimulants
    8. Early training: workout < 2h after wake -> extend warm-up
    9. Short sleep: sleep window < 7h -> reduce weekly volume ~20%, flag to admin
    10. Missing times: fallback to 07:00 / 18:00 / 23:00, confidence = Low, prompt admin
    """
    missing_anchors = False
    actual_wake = wake_time
    actual_workout = workout_time
    actual_sleep = sleep_time

    if not actual_wake or parse_time(actual_wake) is None:
        actual_wake = "07:00"
        missing_anchors = True
    if not actual_workout or parse_time(actual_workout) is None:
        actual_workout = "18:00"
        missing_anchors = True
    if not actual_sleep or parse_time(actual_sleep) is None:
        actual_sleep = "23:00"
        missing_anchors = True

    wake_mins = parse_time(actual_wake) or 420
    workout_mins = parse_time(actual_workout) or 1080
    sleep_mins = parse_time(actual_sleep) or 1380

    confidence = "Low" if missing_anchors else "High"
    fallback_note = (
        " (Missing anchor: defaulted to fallback times 07:00 wake / 18:00 workout / 23:00 sleep. Collect exact times from member.)"
        if missing_anchors
        else ""
    )

    # Relative workout timing calculations
    if workout_mins >= wake_mins:
        workout_offset_from_wake = workout_mins - wake_mins
    else:
        workout_offset_from_wake = (1440 - wake_mins) + workout_mins

    if sleep_mins >= workout_mins:
        time_to_sleep = sleep_mins - workout_mins
    else:
        time_to_sleep = (1440 - workout_mins) + sleep_mins

    sleep_duration_mins = calculate_sleep_duration_minutes(sleep_mins, wake_mins)

    is_fasted_start = workout_offset_from_wake < 60
    is_early_training = workout_offset_from_wake < 120
    is_late_training = time_to_sleep < 180
    is_short_sleep = sleep_duration_mins < 420

    caffeine_cutoff_mins = (sleep_mins - 480) % 1440
    workout_in_caffeine_cutoff_window = time_to_sleep <= 480

    raw_slots: List[Dict[str, Any]] = []

    # 1. Wake slot
    wake_rationale = (
        f"Wake anchor reported at {actual_wake}. Establishes circadian start for the day." + fallback_note
    )
    if is_short_sleep:
        hours_str = f"{sleep_duration_mins / 60:.1f}".rstrip("0").rstrip(".")
        wake_rationale += (
            f" Short sleep window detected ({hours_str} hours between {actual_sleep} and {actual_wake}, floor is 7 hours). "
            "Reduce weekly training volume by ~20% and focus on sleep recovery."
        )

    raw_slots.append({
        "slot_time": actual_wake,
        "minutes": wake_mins,
        "item_type": "recovery",
        "title": "Wake Anchor & Hydration",
        "purpose": "Circadian alignment",
        "rationale": wake_rationale,
        "confidence": confidence,
    })

    # 2. First meal / Breakfast
    if is_fasted_start:
        first_meal_mins = wake_mins + 30
        raw_slots.append({
            "slot_time": format_time(first_meal_mins),
            "minutes": first_meal_mins,
            "item_type": "meal",
            "title": "Pre-Workout Light Carb Snack",
            "purpose": "Fasted session energy boost",
            "rationale": (
                f"Workout at {actual_workout} is within 60 min of waking at {actual_wake}. "
                "Full breakfast is deferred until post-workout; take a light, easy-to-digest carb only."
            ) + fallback_note,
            "confidence": confidence,
        })
    else:
        first_meal_mins = wake_mins + 30
        raw_slots.append({
            "slot_time": format_time(first_meal_mins),
            "minutes": first_meal_mins,
            "item_type": "meal",
            "title": "Breakfast · 35g Protein",
            "purpose": "First protein feeding",
            "rationale": (
                f"Placed at {format_time(first_meal_mins)} (within 30–60 min of waking at {actual_wake}). "
                "Front-loading protein supports daily targets across distributed feedings."
            ) + fallback_note,
            "confidence": confidence,
        })

    # 3. Pre-workout meal (if workout > 2h after wake and not fasted)
    if workout_offset_from_wake >= 120:
        pre_workout_mins = workout_mins - 90
        raw_slots.append({
            "slot_time": format_time(pre_workout_mins),
            "minutes": pre_workout_mins,
            "item_type": "meal",
            "title": "Pre-Workout Meal · Carb-Led",
            "purpose": "Session fueling",
            "rationale": (
                f"Placed at {format_time(pre_workout_mins)} (90 minutes before your {actual_workout} workout). "
                "Provides accessible glycogen while allowing stomach emptying before training."
            ) + fallback_note,
            "confidence": confidence,
        })

    # 4. Caffeine Cut-off Slot
    caffeine_rationale = (
        f"Caffeine cut-off at {format_time(caffeine_cutoff_mins)} (8 hours clear of your {actual_sleep} bedtime). "
        "Caffeine half-life is 5–6 hours; late consumption disrupts sleep architecture."
    )
    if workout_in_caffeine_cutoff_window:
        caffeine_rationale += (
            f" Training at {actual_workout} falls inside the 8-hour pre-sleep window; "
            "drop pre-workout caffeine/stimulants entirely."
        )

    raw_slots.append({
        "slot_time": format_time(caffeine_cutoff_mins),
        "minutes": caffeine_cutoff_mins,
        "item_type": "hydration",
        "title": "Caffeine & Stimulant Cut-Off",
        "purpose": "Sleep protection",
        "rationale": caffeine_rationale + fallback_note,
        "confidence": confidence,
    })

    # 5. Workout Session Slot
    workout_title = "Training Session"
    if is_late_training:
        workout_title = "Late Training Session (Controlled Intensity)"
    elif is_early_training:
        workout_title = "Early Training Session (Extended Warm-Up)"

    workout_rationale = f"Anchor workout slot at {actual_workout}."
    if is_early_training:
        workout_rationale += (
            f" Scheduled less than 2 hours after waking at {actual_wake}. "
            "Extend warm-up phase by 10 minutes as core temperature and joint readiness are lowest upon waking."
        )
    elif is_late_training:
        workout_rationale += (
            f" Scheduled at {actual_workout} (less than 3 hours before your {actual_sleep} bedtime). "
            "Cap RPE/intensity, exclude pre-workout stimulants, and include a dedicated cool-down/wind-down protocol."
        )

    raw_slots.append({
        "slot_time": actual_workout,
        "minutes": workout_mins,
        "item_type": "exercise",
        "title": workout_title,
        "purpose": "Primary stimulus",
        "rationale": workout_rationale + fallback_note,
        "confidence": confidence,
    })

    # 6. Post-Workout Feeding Slot
    post_workout_mins = workout_mins + 75
    if is_fasted_start:
        post_title = "Post-Workout Full Breakfast · 40g Protein"
        post_rationale = (
            f"Placed at {format_time(post_workout_mins)} (within 60 minutes of finishing your {actual_workout} session). "
            "Serves as main post-workout protein feed and full breakfast deferred from wake."
        )
    else:
        post_title = "Post-Workout Refuel · 40g Protein & Carbs"
        post_rationale = (
            f"Placed at {format_time(post_workout_mins)} (within 60 minutes of finishing your {actual_workout} session). "
            "Largest protein and carbohydrate intake of the day placed when muscle glycogen synthesis peak is highest."
        )

    raw_slots.append({
        "slot_time": format_time(post_workout_mins),
        "minutes": post_workout_mins,
        "item_type": "meal",
        "title": post_title,
        "purpose": "Recovery & protein synthesis",
        "rationale": post_rationale + fallback_note,
        "confidence": confidence,
    })

    # 7. Last Meal Slot
    last_meal_mins = sleep_mins - 120
    raw_slots.append({
        "slot_time": format_time(last_meal_mins),
        "minutes": last_meal_mins,
        "item_type": "meal",
        "title": "Last Meal / Evening Feeding",
        "purpose": "Overnight protein retention",
        "rationale": (
            f"Placed at {format_time(last_meal_mins)} (at least 2 hours clear of your {actual_sleep} bedtime). "
            "Eating closer to sleep impairs nocturnal HRV and delays sleep onset."
        ) + fallback_note,
        "confidence": confidence,
    })

    # 8. Sleep Slot
    raw_slots.append({
        "slot_time": actual_sleep,
        "minutes": sleep_mins,
        "item_type": "sleep",
        "title": "Sleep Anchor & Recovery Window",
        "purpose": "Systemic adaptation",
        "rationale": (
            f"Sleep anchor at {actual_sleep}. Target bedtime to preserve recovery window before {actual_wake} wake."
        ) + fallback_note,
        "confidence": confidence,
    })

    # Sort slots chronologically starting from wake_mins
    def get_sort_key(slot: Dict[str, Any]) -> int:
        m = slot["minutes"]
        if m < wake_mins:
            return m + 1440
        return m

    raw_slots.sort(key=get_sort_key)

    final_slots = []
    for slot in raw_slots:
        item = {
            "slot_time": slot["slot_time"],
            "item_type": slot["item_type"],
            "title": slot["title"],
            "purpose": slot["purpose"],
            "rationale": slot["rationale"],
            "confidence": slot["confidence"],
        }
        final_slots.append(item)

    return final_slots
