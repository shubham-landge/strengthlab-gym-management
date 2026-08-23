"""
Tests for services/circadian_service.py
"""
import pytest
from services.circadian_service import (
    build_day_slots,
    parse_time,
    format_time,
    calculate_sleep_duration_minutes,
)


def test_time_parsing_and_formatting():
    assert parse_time("07:30") == 450
    assert parse_time("00:00") == 0
    assert parse_time("23:59") == 1439
    assert parse_time(None) is None
    assert parse_time("invalid") is None

    assert format_time(450) == "07:30"
    assert format_time(0) == "00:00"
    assert format_time(1440) == "00:00"
    assert format_time(1500) == "01:00"


def test_sleep_duration_calculation():
    # Sleep 23:00 (1380), Wake 07:00 (420) -> 8 hours (480 min)
    assert calculate_sleep_duration_minutes(1380, 420) == 480
    # Sleep 01:30 (90), Wake 07:30 (450) -> 6 hours (360 min)
    assert calculate_sleep_duration_minutes(90, 450) == 360


def test_standard_day_slots():
    slots = build_day_slots(wake_time="06:30", workout_time="18:30", sleep_time="23:00")
    assert len(slots) > 0
    times = [s["slot_time"] for s in slots]

    # Wake at 06:30
    assert "06:30" in times
    # Workout at 18:30
    assert "18:30" in times
    # Sleep at 23:00
    assert "23:00" in times
    # Pre-workout meal 90 min before 18:30 -> 17:00
    assert "17:00" in times
    # Caffeine cut-off 8h before 23:00 -> 15:00
    assert "15:00" in times
    # Last meal 2h before 23:00 -> 21:00
    assert "21:00" in times

    # All slots should have confidence = High
    for slot in slots:
        assert slot["confidence"] == "High"
        assert len(slot["rationale"]) > 10


def test_missing_anchors_fallback():
    slots = build_day_slots(wake_time=None, workout_time=None, sleep_time=None)
    assert len(slots) > 0
    times = [s["slot_time"] for s in slots]

    assert "07:00" in times  # fallback wake
    assert "18:00" in times  # fallback workout
    assert "23:00" in times  # fallback sleep

    # Confidence must be Low when anchors are missing
    for slot in slots:
        assert slot["confidence"] == "Low"
        assert "Missing anchor" in slot["rationale"] or "07:00" in slot["rationale"]


def test_fasted_start():
    # Workout at 07:30 is within 60 min of wake at 07:00
    slots = build_day_slots(wake_time="07:00", workout_time="07:30", sleep_time="23:00")

    snack_slot = next(s for s in slots if s["title"] == "Pre-Workout Light Carb Snack")
    assert "Pre-Workout Light Carb Snack" in snack_slot["title"]
    assert "within 60 min of waking at 07:00" in snack_slot["rationale"]

    post_slot = next(s for s in slots if "Post-Workout Full Breakfast" in s["title"])
    assert "full breakfast deferred from wake" in post_slot["rationale"].lower()


def test_early_training():
    # Workout at 08:00 is within 2 hours of wake at 06:30
    slots = build_day_slots(wake_time="06:30", workout_time="08:00", sleep_time="23:00")
    workout_slot = next(s for s in slots if s["slot_time"] == "08:00")
    assert "Early Training Session" in workout_slot["title"]
    assert "Extend warm-up" in workout_slot["rationale"]


def test_late_training():
    # Workout at 21:00 is within 3 hours of sleep at 23:00
    slots = build_day_slots(wake_time="07:00", workout_time="21:00", sleep_time="23:00")
    workout_slot = next(s for s in slots if s["slot_time"] == "21:00")
    assert "Late Training Session" in workout_slot["title"]
    assert "Cap RPE/intensity" in workout_slot["rationale"]


def test_short_sleep():
    # Sleep at 01:00, wake at 06:00 -> 5 hours sleep window (< 7 hours)
    slots = build_day_slots(wake_time="06:00", workout_time="17:00", sleep_time="01:00")
    wake_slot = next(s for s in slots if s["slot_time"] == "06:00")
    assert "Short sleep window detected" in wake_slot["rationale"]
    assert "5 hours" in wake_slot["rationale"] or "5.0 hours" in wake_slot["rationale"]


def test_midnight_wrap_sleep():
    # Sleep at 01:30 (past midnight)
    slots = build_day_slots(wake_time="08:30", workout_time="18:00", sleep_time="01:30")
    times = [s["slot_time"] for s in slots]
    assert "01:30" in times
    # Caffeine cut-off 8 hours before 01:30 -> 17:30
    assert "17:30" in times
    # Last meal 2 hours before 01:30 -> 23:30
    assert "23:30" in times
