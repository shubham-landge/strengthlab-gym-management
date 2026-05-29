from datetime import date, datetime, timedelta
from functools import wraps
from io import BytesIO
import json
import os
import secrets
import sqlite3
import threading
import textwrap
import time
from urllib.parse import quote

from flask import Flask, g, redirect, render_template, request, send_file, session, url_for
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from openpyxl import Workbook
from werkzeug.security import check_password_hash, generate_password_hash


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "gym_manager.db")

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "local-gym-secret")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-5.2")
PAYMENT_REMINDER_DAYS = int(os.environ.get("PAYMENT_REMINDER_DAYS", "3"))
PAYMENT_REMINDER_INTERVAL_SECONDS = int(os.environ.get("PAYMENT_REMINDER_INTERVAL_SECONDS", "3600"))
_payment_automation_started = False
_payment_automation_lock = threading.Lock()


PREBUILT_EQUIPMENT = [
    ("Lat Pulldown", "Back", 1, "Good", 60),
    ("Preacher Curl", "Arms", 1, "Good", 60),
    ("Seated Calf Raise", "Calves", 1, "Good", 60),
    ("Standing Calf Raise", "Calves", 1, "Good", 60),
    ("Pec Deck Fly", "Chest", 1, "Good", 60),
    ("Seated Leg Curl", "Legs", 1, "Good", 60),
    ("Decline Bench Olympic", "Bench", 1, "Good", 60),
    ("Adjustable Olympia Flat to Decline Bench", "Bench", 1, "Good", 60),
    ("Back Extension", "Posterior Chain", 1, "Good", 60),
    ("Parallel Bar / Chin-Up / Leg Raise Stand", "Bodyweight", 1, "Good", 60),
    ("Three Tier Dumbbell Rack with Rubber Holder", "Storage", 1, "Good", 60),
    ("Dumbbells 2.5-70 lbs", "Free Weights", 1, "Good", 60),
    ("Leg Press", "Legs", 1, "Good", 60),
    ("Seated Lateral Raise Machine", "Shoulders", 1, "Good", 60),
    ("Casting Plates", "Free Weights", 1, "Good", 60),
    ("Vertical Barbell Rack", "Storage", 1, "Good", 60),
    ("Fixed Flat Bench", "Bench", 1, "Good", 60),
    ("Treadmill", "Cardio", 1, "Good", 30),
    ("Cycle", "Cardio", 1, "Good", 30),
]


EQUIPMENT_GUIDE_SOURCE = "https://gym-equipment-guide-b4pkphb.gamma.site/#"
GAMMA_IMAGE_BASE = "https://cdn.gamma.app/4zqg9rmb9y23m2c/generated-images"
BEGINNER_EQUIPMENT_GUIDE = [
    {
        "title": "Start Here",
        "image": f"{GAMMA_IMAGE_BASE}/tPMZRJcafORTUwYmlfgVD.jpg",
        "intro": "Use this guide when a new member feels unsure around machines, benches, dumbbells, plates, or cardio equipment. The safest pattern is simple: adjust the machine, start light, move slowly, and ask staff before increasing weight.",
        "items": [
            {
                "name": "Beginner setup rules",
                "image": f"{GAMMA_IMAGE_BASE}/sfakoFbEqjmjy85y-AG9R.jpg",
                "target": "Safety and confidence",
                "how_to": [
                    "Start with a weight that feels easy for the first set.",
                    "Adjust seats, pads, and pins before loading or lifting.",
                    "Use controlled reps and avoid swinging the body to move weight.",
                    "Stop for sharp pain, dizziness, chest pain, numbness, or worsening joint pain.",
                ],
            },
        ],
    },
    {
        "title": "Cable and Selectorized Machines",
        "image": f"{GAMMA_IMAGE_BASE}/yyQOKNgqiYLM0Bb9C86Sp.jpg",
        "intro": "These machines use guided movement and pin-selected weight stacks, which makes them beginner-friendly for learning muscle control.",
        "items": [
            {
                "name": "Lat Pulldown Machine",
                "image": f"{GAMMA_IMAGE_BASE}/zE1CLayy1fLKXyCtUTDeh.jpg",
                "target": "Upper back and lats",
                "how_to": [
                    "Adjust the thigh pad so your legs are held firmly down.",
                    "Grip the bar slightly wider than shoulder width.",
                    "Lean back slightly, pull elbows down toward your sides, and bring the bar to the upper chest.",
                    "Return slowly until arms are straight; do not swing your torso.",
                ],
            },
            {
                "name": "Pec Deck Fly Machine",
                "image": f"{GAMMA_IMAGE_BASE}/MIho_jaBq4wjCKpDL8bVh.jpg",
                "target": "Chest isolation",
                "how_to": [
                    "Set the seat so handles line up around mid-to-lower chest.",
                    "Keep back and head against the pad.",
                    "Move handles together in a wide arc, squeeze the chest, then open slowly.",
                    "Do not let the weight stack slam.",
                ],
            },
            {
                "name": "Seated Leg Curl",
                "image": f"{GAMMA_IMAGE_BASE}/LwuNt8Y_PQGkWpn0-UDiW.jpg",
                "target": "Hamstrings",
                "how_to": [
                    "Align knees with the machine pivot point.",
                    "Place the lower pad just above the shoes.",
                    "Curl the legs down under control, squeeze briefly, and return slowly.",
                ],
            },
            {
                "name": "Seated Lateral Raise Machine",
                "image": f"{GAMMA_IMAGE_BASE}/aFcy8i0TEpXtSGARcfKAe.jpg",
                "target": "Side shoulders",
                "how_to": [
                    "Sit with the shoulder joint aligned to the machine pivot.",
                    "Place outer elbows on the pads.",
                    "Raise elbows outward until level with shoulders, then lower slowly.",
                ],
            },
        ],
    },
    {
        "title": "Plate-Loaded and Heavy Equipment",
        "image": f"{GAMMA_IMAGE_BASE}/gq6K3aVnl3gAdS9WrZWOG.jpg",
        "intro": "Plate-loaded equipment can be very effective, but beginners should practice with the empty machine or light plates first.",
        "items": [
            {
                "name": "Leg Press Machine",
                "image": f"{GAMMA_IMAGE_BASE}/iMHLIPaY4Gsc0x2lRYNcV.jpg",
                "target": "Quads, glutes, and hamstrings",
                "how_to": [
                    "Sit deep with the lower back flat against the pad.",
                    "Place feet high and shoulder-width on the platform.",
                    "Unlock the safety handles only after pressing the platform up slightly.",
                    "Lower to a comfortable knee bend, press through the full foot, and keep knees softly bent at the top.",
                    "Re-lock the safety before stepping out.",
                ],
            },
            {
                "name": "Seated Calf Raise",
                "image": f"{GAMMA_IMAGE_BASE}/HU1RK1T-p5a11xl0lwbnS.jpg",
                "target": "Lower calf / soleus",
                "how_to": [
                    "Place balls of the feet on the block with heels free.",
                    "Secure knees under the pad.",
                    "Lift heels high, lower into a safe stretch, and repeat under control.",
                ],
            },
            {
                "name": "Standing Calf Raise",
                "image": f"{GAMMA_IMAGE_BASE}/HU1RK1T-p5a11xl0lwbnS.jpg",
                "target": "Upper visible calf / gastrocnemius",
                "how_to": [
                    "Set shoulder pads so you can stand tall with slightly soft knees.",
                    "Place balls of the feet on the block.",
                    "Lower heels below the step, then rise onto toes and squeeze at the top.",
                ],
            },
        ],
    },
    {
        "title": "Free Weights and Benches",
        "image": f"{GAMMA_IMAGE_BASE}/j4XsCz9prx2I50WXpFWTA.jpg",
        "intro": "Free weights train stabilizer muscles and allow long-term progression. Beginners should choose loads they can control from start to finish.",
        "items": [
            {
                "name": "Preacher Curl Bench",
                "image": f"{GAMMA_IMAGE_BASE}/DAF1wyjdJf8bKI7S9KC4z.jpg",
                "target": "Biceps",
                "how_to": [
                    "Adjust seat so upper arms rest securely on the angled pad.",
                    "Use an EZ bar or dumbbells with palms facing up.",
                    "Curl without lifting the upper arms, squeeze, and lower slowly.",
                ],
            },
            {
                "name": "Decline Bench Olympic",
                "image": f"{GAMMA_IMAGE_BASE}/j4XsCz9prx2I50WXpFWTA.jpg",
                "target": "Chest pressing",
                "how_to": [
                    "Lock ankles behind the rollers before pressing.",
                    "Use a grip slightly wider than shoulder width.",
                    "Lower the bar toward the lower chest and press up under control.",
                    "Use a spotter when pressing a free barbell.",
                ],
            },
            {
                "name": "Adjustable Flat-to-Decline Bench",
                "image": f"{GAMMA_IMAGE_BASE}/j4XsCz9prx2I50WXpFWTA.jpg",
                "target": "Variable chest and dumbbell work",
                "how_to": [
                    "Set the bench angle before loading weights.",
                    "Confirm the selector pin is fully locked.",
                    "Keep feet planted and body stable before beginning the set.",
                ],
            },
            {
                "name": "Fixed Flat Bench",
                "image": f"{GAMMA_IMAGE_BASE}/j4XsCz9prx2I50WXpFWTA.jpg",
                "target": "Dumbbell press, rows, and seated arm work",
                "how_to": [
                    "No setup is needed beyond stable foot position.",
                    "Keep back supported for pressing movements.",
                    "Use controlled dumbbell paths and avoid bouncing weights.",
                ],
            },
            {
                "name": "Back Extension Bench",
                "image": f"{GAMMA_IMAGE_BASE}/DAF1wyjdJf8bKI7S9KC4z.jpg",
                "target": "Lower back, glutes, and hamstrings",
                "how_to": [
                    "Set the hip pad just below the hip bones.",
                    "Lock feet under the rollers.",
                    "Fold from the hips, then rise until the body is straight.",
                    "Do not over-arch beyond a straight line.",
                ],
            },
            {
                "name": "Parallel Bar / Chin-Up / Leg Raise Stand",
                "image": f"{GAMMA_IMAGE_BASE}/zE1CLayy1fLKXyCtUTDeh.jpg",
                "target": "Bodyweight upper body and core",
                "how_to": [
                    "For beginner leg raises, rest the back against the pad and forearms on the rails.",
                    "Grip handles firmly, lift feet, and raise knees toward the chest.",
                    "Lower slowly and avoid swinging.",
                ],
            },
        ],
    },
    {
        "title": "Storage and Accessories",
        "image": f"{GAMMA_IMAGE_BASE}/j4XsCz9prx2I50WXpFWTA.jpg",
        "intro": "Good storage keeps the gym safe and easy to use. Re-racking is part of the workout culture.",
        "items": [
            {
                "name": "Three-Tier Dumbbell Rack",
                "image": f"{GAMMA_IMAGE_BASE}/j4XsCz9prx2I50WXpFWTA.jpg",
                "target": "Organized dumbbell storage",
                "how_to": [
                    "Return each dumbbell to the matching weight slot.",
                    "Lift heavier dumbbells from lower shelves with bent knees.",
                    "Keep walkways clear.",
                ],
            },
            {
                "name": "Dumbbells 2.5-70 lbs",
                "image": f"{GAMMA_IMAGE_BASE}/j4XsCz9prx2I50WXpFWTA.jpg",
                "target": "Free-weight strength training",
                "how_to": [
                    "Use lighter dumbbells for lateral raises, curls, and learning movement paths.",
                    "Progress gradually as form improves.",
                    "Do not drop dumbbells unless the gym specifically allows it.",
                ],
            },
            {
                "name": "Casting Plates and Vertical Barbell Rack",
                "image": f"{GAMMA_IMAGE_BASE}/j4XsCz9prx2I50WXpFWTA.jpg",
                "target": "Plate loading and barbell storage",
                "how_to": [
                    "Load plates evenly on both sides.",
                    "Remove plates from machines and barbells when finished.",
                    "Store barbells upright in the rack and keep the floor clear.",
                ],
            },
        ],
    },
    {
        "title": "Cardio Equipment",
        "image": f"{GAMMA_IMAGE_BASE}/sfakoFbEqjmjy85y-AG9R.jpg",
        "intro": "Cardio machines are useful for 5-10 minute warm-ups before lifting and for conditioning after workouts.",
        "items": [
            {
                "name": "Treadmill",
                "image": f"{GAMMA_IMAGE_BASE}/sfakoFbEqjmjy85y-AG9R.jpg",
                "target": "Walking, jogging, and incline conditioning",
                "how_to": [
                    "Attach the safety clip before starting.",
                    "Stand on the side rails, press start, then step onto the belt at slow speed.",
                    "Increase speed and incline gradually.",
                ],
            },
            {
                "name": "Stationary Cycle",
                "image": f"{GAMMA_IMAGE_BASE}/yyQOKNgqiYLM0Bb9C86Sp.jpg",
                "target": "Low-impact cardio",
                "how_to": [
                    "Set the seat close to hip height before sitting.",
                    "At the bottom pedal position, keep a small bend in the knee.",
                    "Start with light resistance for 2-3 minutes before increasing effort.",
                ],
            },
        ],
    },
]


MEMBER_PROFILE_OPTIONS = {
    "primary_fitness_goal": [
        "Weight Loss / Fat Loss",
        "Muscle Gain / Hypertrophy",
        "Body Recomposition",
        "Weight Maintenance & Healthy Living",
    ],
    "activity_level": [
        "Sedentary",
        "Lightly Active",
        "Moderately Active",
        "Very Active",
    ],
    "dietary_style": [
        "Non-Vegetarian",
        "Ovo-Vegetarian",
        "Lacto-Vegetarian",
        "Pure Vegetarian",
        "Vegan",
    ],
    "food_exclusions": [
        "Lactose Intolerant",
        "Gluten-Free / Celiac",
        "No Seafood / Fish Allergies",
        "No Nuts / Peanuts",
        "No Soy / Tofu",
    ],
    "meals_per_day": [
        "2 Large Meals",
        "3 Main Meals",
        "3 Main Meals + 1 Snack",
        "4 to 5 Small Meals",
    ],
    "cooking_preference": [
        "Cook Fresh Daily",
        "Batch Meal Prep",
        "Tiffin / Mess Service",
    ],
    "medical_conditions": [
        "Diabetes / Pre-Diabetes",
        "Hypertension",
        "Thyroid issues",
        "Uric Acid / Gout",
        "Digestive Issues",
        "None / Perfectly Healthy",
    ],
    "supplements": [
        "Whey Protein Powder",
        "Creatine Monohydrate",
        "Omega-3 Fish Oil / Algae Oil",
        "Daily Multivitamin",
        "No supplements, 100% whole foods",
    ],
}


PREBUILT_WORKOUT_PLANS = {
    "beginner": {
        "name": "Beginner - 3 Day Full Body",
        "plan": """Universal Gym Workout Plan - Beginner

Best for: new members, deconditioned people, or people returning after a long break.
Frequency: 3 days per week
Style: Full body
Example: Monday, Wednesday, Friday
Goal: Learn movements, build consistency, and avoid excessive soreness.

Equipment used:
Lat pulldown, preacher curl, seated calf raise, standing calf raise, pec deck fly, seated leg curl, adjustable bench, back extension, parallel bar/chin-up/leg raise stand, dumbbells, leg press, seated lateral raise machine, treadmill, and cycle.

General warm-up before every workout:
1. Treadmill or cycle - 5 to 10 minutes easy pace
2. Joint warm-up - shoulders, hips, knees, ankles
3. One light warm-up set before the first big exercise

Intensity:
RPE 6-7. Keep 3-4 reps in reserve. Do not train to failure.

Rest:
Big movements: 90-150 seconds
Isolation movements: 45-90 seconds
Calves/abs: 45-75 seconds

Day 1 - Full Body A
- Leg Press: 2 sets x 12-15 reps, RPE 6
- Dumbbell Flat Bench Press: 2 sets x 10-12 reps, RPE 6
- Lat Pulldown: 2 sets x 10-12 reps, RPE 6
- Seated Leg Curl: 2 sets x 12-15 reps, RPE 6
- Seated Lateral Raise Machine: 2 sets x 12-15 reps, RPE 6
- Seated Calf Raise: 2 sets x 12-15 reps, RPE 6
- Back Extension: 2 sets x 10-12 reps, RPE 6
- Treadmill or Cycle: 10 minutes easy

Day 2 - Full Body B
- Dumbbell Goblet Squat: 2 sets x 10-12 reps, RPE 6
- Pec Deck Fly: 2 sets x 12-15 reps, RPE 6
- One-Arm Dumbbell Row: 2 sets each side x 10-12 reps, RPE 6
- Seated Leg Curl: 2 sets x 12-15 reps, RPE 6
- Preacher Curl: 2 sets x 10-12 reps, RPE 6
- Standing Calf Raise: 2 sets x 12-15 reps, RPE 6
- Parallel Bar Knee Raise: 2 sets x 8-12 reps, RPE 6
- Cycle: 10 minutes easy

Day 3 - Full Body C
- Leg Press: 2 sets x 12-15 reps, RPE 6-7
- Dumbbell Bench Press: 2 sets x 10-12 reps, RPE 6-7
- Lat Pulldown: 2 sets x 10-12 reps, RPE 6-7
- Dumbbell Romanian Deadlift: 2 sets x 10-12 reps, RPE 6
- Seated Lateral Raise Machine: 2 sets x 12-15 reps, RPE 6
- Seated or Standing Calf Raise: 2 sets x 12-15 reps, RPE 6
- Back Extension: 2 sets x 10-12 reps, RPE 6
- Treadmill: 10-15 minutes easy

Beginner progression:
When all sets reach the top of the rep range with clean form, increase weight slightly next session. Example: if Leg Press is 2 x 15 easily, add a small amount of weight next session.

Cardio:
10-15 minutes after workout, easy treadmill or cycle.

Substitutions:
- Chin-up too hard: Lat pulldown
- Dumbbell bench too hard: Pec deck plus light dumbbell press
- Lunges painful: Leg press
- Back extension uncomfortable: Light dumbbell Romanian deadlift
- Standing calf raise busy: Seated calf raise
- Treadmill busy: Cycle

Safety:
Stop or reduce intensity for sharp pain, dizziness, chest pain, severe shortness of breath, numbness, or joint pain that worsens during the set.""",
    },
    "intermediate": {
        "name": "Intermediate - 4 Day Upper/Lower",
        "plan": """Universal Gym Workout Plan - Intermediate

Best for: people with 6+ months of consistent training.
Frequency: 4 days per week
Style: Upper/lower split
Example: Monday, Tuesday, Thursday, Friday
Goal: Muscle gain, strength, better shape, and better conditioning.

General warm-up before every workout:
1. Treadmill or cycle - 5 to 10 minutes easy pace
2. Joint warm-up - shoulders, hips, knees, ankles
3. One light warm-up set before the first big exercise

Intensity:
RPE 7-8. Keep 1-3 reps in reserve. Avoid failure for general gym members.

Rest:
Big movements: 90-150 seconds
Isolation movements: 45-90 seconds
Calves/abs: 45-75 seconds

Day 1 - Upper Body A
- Dumbbell Flat Bench Press: 3 sets x 8-10 reps, RPE 7-8
- Lat Pulldown: 3 sets x 8-12 reps, RPE 7-8
- Pec Deck Fly: 3 sets x 12-15 reps, RPE 7
- Seated Lateral Raise Machine: 3 sets x 12-15 reps, RPE 7-8
- One-Arm Dumbbell Row: 3 sets each side x 10-12 reps, RPE 7
- Preacher Curl: 3 sets x 10-12 reps, RPE 7-8
- Parallel Bar Knee Raise: 3 sets x 10-15 reps, RPE 7

Day 2 - Lower Body A
- Leg Press: 4 sets x 8-12 reps, RPE 7-8
- Dumbbell Romanian Deadlift: 3 sets x 8-10 reps, RPE 7
- Seated Leg Curl: 3 sets x 10-12 reps, RPE 7-8
- Back Extension: 3 sets x 10-15 reps, RPE 7
- Standing Calf Raise: 3 sets x 10-15 reps, RPE 7-8
- Seated Calf Raise: 2 sets x 12-15 reps, RPE 7
- Cycle: 10-15 minutes moderate

Day 3 - Upper Body B
- Dumbbell Decline Bench Press: 3 sets x 8-10 reps, RPE 7-8
- Chin-Up or Assisted Chin-Up / Lat Pulldown: 3 sets x 6-10 reps, RPE 7-8
- Dumbbell Shoulder Press: 3 sets x 8-10 reps, RPE 7
- Pec Deck Fly: 2-3 sets x 12-15 reps, RPE 7
- Dumbbell Row: 3 sets x 8-12 reps, RPE 7-8
- Preacher Curl: 3 sets x 10-12 reps, RPE 7-8
- Leg Raise Stand: 3 sets x 8-15 reps, RPE 7

Day 4 - Lower Body B
- Leg Press: 3 sets x 12-15 reps, RPE 7
- Dumbbell Walking Lunge: 3 sets each leg x 10-12 reps, RPE 7-8
- Seated Leg Curl: 3 sets x 10-15 reps, RPE 7-8
- Dumbbell Romanian Deadlift: 3 sets x 10-12 reps, RPE 7
- Back Extension: 2-3 sets x 12-15 reps, RPE 7
- Seated Calf Raise: 3 sets x 12-15 reps, RPE 7-8
- Treadmill Incline Walk: 10-15 minutes moderate

Intermediate progression:
Use double progression:
1. Stay within the rep range.
2. Add reps first.
3. When all sets reach the top of the range, increase weight.
4. Keep form strict.

Example:
Dumbbell Bench Press:
Week 1: 40 lb x 8, 8, 7
Week 2: 40 lb x 9, 8, 8
Week 3: 40 lb x 10, 10, 9
Week 4: increase to 45 lb.

Cardio:
15-20 minutes, 2-4 times per week. For fat loss, add more walking and moderate cardio. For muscle gain, keep cardio moderate and avoid excessive fatigue.

Safety:
Stop or reduce intensity for sharp pain, dizziness, chest pain, severe shortness of breath, numbness, or joint pain that worsens during the set.""",
    },
    "advanced": {
        "name": "Advanced - 6 Day Push/Pull/Legs",
        "plan": """Universal Gym Workout Plan - Advanced

Best for: people with 1-2+ years of consistent training.
Frequency: 5-6 days per week
Style: Push / Pull / Legs
Goal: Hypertrophy, strength, physique development, and higher volume.

General warm-up before every workout:
1. Treadmill or cycle - 5 to 10 minutes easy pace
2. Joint warm-up - shoulders, hips, knees, ankles
3. One light warm-up set before the first big exercise

Intensity:
RPE 8-9. Keep 1-2 reps in reserve. Avoid repeated failure for general gym members.

Rest:
Big movements: 90-150 seconds
Isolation movements: 45-90 seconds
Calves/abs: 45-75 seconds

Day 1 - Push A
- Dumbbell Flat Bench Press: 4 sets x 6-10 reps, RPE 8
- Dumbbell Decline Bench Press: 3 sets x 8-10 reps, RPE 8
- Pec Deck Fly: 3 sets x 12-15 reps, RPE 8
- Dumbbell Shoulder Press: 3 sets x 8-10 reps, RPE 8
- Seated Lateral Raise Machine: 4 sets x 12-20 reps, RPE 8-9
- Parallel Bar Dip: 3 sets x 6-12 reps, RPE 8

Day 2 - Pull A
- Chin-Up or Lat Pulldown: 4 sets x 6-10 reps, RPE 8
- One-Arm Dumbbell Row: 4 sets each side x 8-12 reps, RPE 8
- Lat Pulldown, Different Grip: 3 sets x 10-12 reps, RPE 8
- Back Extension: 3 sets x 10-15 reps, RPE 8
- Preacher Curl: 4 sets x 8-12 reps, RPE 8-9
- Dumbbell Hammer Curl: 3 sets x 10-12 reps, RPE 8
- Leg Raise Stand: 3 sets x 10-15 reps, RPE 8

Day 3 - Legs A
- Leg Press: 5 sets x 6-10 reps, RPE 8-9
- Dumbbell Romanian Deadlift: 4 sets x 8-10 reps, RPE 8
- Seated Leg Curl: 4 sets x 10-15 reps, RPE 8-9
- Dumbbell Walking Lunge: 3 sets each leg x 10-12 reps, RPE 8
- Standing Calf Raise: 4 sets x 8-12 reps, RPE 8-9
- Seated Calf Raise: 3 sets x 12-20 reps, RPE 8
- Cycle: 10 minutes easy recovery

Day 4 - Push B
- Dumbbell Bench Press: 4 sets x 8-12 reps, RPE 8
- Pec Deck Fly: 4 sets x 12-15 reps, RPE 8-9
- Dumbbell Incline-Style Press if bench allows / Flat Press if not: 3 sets x 8-12 reps, RPE 8
- Dumbbell Shoulder Press: 3 sets x 8-10 reps, RPE 8
- Seated Lateral Raise Machine: 4 sets x 15-20 reps, RPE 8-9
- Parallel Bar Dip: 3 sets x 8-12 reps, RPE 8

Day 5 - Pull B
- Lat Pulldown: 4 sets x 8-12 reps, RPE 8
- Dumbbell Row: 4 sets x 10-12 reps, RPE 8
- Chin-Up: 3 sets max clean reps, stop before failure, RPE 8-9
- Back Extension: 3 sets x 12-15 reps, RPE 8
- Preacher Curl: 4 sets x 10-12 reps, RPE 8-9
- Dumbbell Curl: 3 sets x 10-15 reps, RPE 8
- Hanging Knee Raise: 3 sets x 10-15 reps, RPE 8

Day 6 - Legs B
- Leg Press: 4 sets x 12-15 reps, RPE 8
- Dumbbell Romanian Deadlift: 4 sets x 10-12 reps, RPE 8
- Seated Leg Curl: 4 sets x 12-15 reps, RPE 8-9
- Dumbbell Split Squat: 3 sets each leg x 8-12 reps, RPE 8
- Standing Calf Raise: 4 sets x 10-15 reps, RPE 8-9
- Seated Calf Raise: 4 sets x 12-20 reps, RPE 8-9
- Treadmill Incline Walk: 10-15 minutes moderate

Day 7 - Rest
Optional: easy walking, mobility, stretching, or light cycling.

Advanced 5-day alternative:
Day 1 Push
Day 2 Pull
Day 3 Legs
Day 4 Upper
Day 5 Lower
Day 6 Rest
Day 7 Rest

Advanced progression:
Week 1: RPE 7
Week 2: RPE 8
Week 3: RPE 8-9
Week 4: Deload by reducing sets 30-40%
Repeat with slightly heavier weights.

Cardio:
20-30 minutes, 2-5 times per week depending on goal.

Safety:
Stop or reduce intensity for sharp pain, dizziness, chest pain, severe shortness of breath, numbness, or joint pain that worsens during the set.""",
    },
}


def db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(_error):
    connection = g.pop("db", None)
    if connection is not None:
        connection.close()


def execute(query, params=()):
    db().execute(query, params)
    db().commit()


def query_all(query, params=()):
    return db().execute(query, params).fetchall()


def query_one(query, params=()):
    return db().execute(query, params).fetchone()


def init_db():
    connection = sqlite3.connect(DB_PATH)
    cursor = connection.cursor()
    cursor.executescript(
        """
        CREATE TABLE IF NOT EXISTS members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            phone TEXT NOT NULL,
            email TEXT,
            address TEXT,
            emergency_contact TEXT,
            age INTEGER,
            gender TEXT,
            height_cm REAL,
            weight_kg REAL,
            goal TEXT,
            primary_location TEXT,
            primary_fitness_goal TEXT,
            activity_level TEXT,
            dietary_style TEXT,
            food_exclusions TEXT,
            other_foods_avoided TEXT,
            meals_per_day TEXT,
            cooking_preference TEXT,
            medical_conditions TEXT,
            supplements TEXT,
            fitness_level TEXT,
            food_preference TEXT,
            medical_notes TEXT,
            injury_notes TEXT,
            plan_name TEXT DEFAULT 'Monthly',
            premium INTEGER DEFAULT 0,
            trainer_id INTEGER,
            subscription_start TEXT,
            subscription_end TEXT,
            payment_status TEXT DEFAULT 'Due',
            workout_plan TEXT,
            diet_plan TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS trainers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            specialty TEXT,
            phone TEXT,
            active INTEGER DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS equipment (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            category TEXT,
            quantity INTEGER DEFAULT 1,
            condition_status TEXT DEFAULT 'Good',
            maintenance_due TEXT
        );

        CREATE TABLE IF NOT EXISTS attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            member_id INTEGER NOT NULL,
            check_in TEXT NOT NULL,
            check_out TEXT,
            FOREIGN KEY(member_id) REFERENCES members(id)
        );

        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            member_id INTEGER NOT NULL,
            invoice_number TEXT,
            amount REAL NOT NULL,
            discount_amount REAL DEFAULT 0,
            net_amount REAL,
            status TEXT NOT NULL,
            payment_method TEXT,
            upi_transaction_id TEXT,
            paid_on TEXT,
            due_on TEXT,
            notes TEXT,
            FOREIGN KEY(member_id) REFERENCES members(id)
        );

        CREATE TABLE IF NOT EXISTS renewal_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            member_id INTEGER NOT NULL,
            payment_id INTEGER,
            plan_name TEXT,
            renewal_start TEXT,
            renewal_end TEXT,
            amount REAL,
            discount_amount REAL DEFAULT 0,
            payment_method TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(member_id) REFERENCES members(id),
            FOREIGN KEY(payment_id) REFERENCES payments(id)
        );

        CREATE TABLE IF NOT EXISTS announcements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            message TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            member_id INTEGER,
            channel TEXT DEFAULT 'WhatsApp',
            message TEXT NOT NULL,
            attachment TEXT,
            status TEXT DEFAULT 'Ready',
            event_key TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(member_id) REFERENCES members(id)
        );

        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('admin', 'trainer', 'member', 'owner', 'accountant')),
            member_id INTEGER,
            trainer_id INTEGER,
            active INTEGER DEFAULT 1,
            must_change_password INTEGER DEFAULT 0,
            reset_token TEXT,
            reset_token_created_at TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(member_id) REFERENCES members(id),
            FOREIGN KEY(trainer_id) REFERENCES trainers(id)
        );

        CREATE TABLE IF NOT EXISTS progress_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            member_id INTEGER NOT NULL,
            entry_date TEXT NOT NULL,
            weight_kg REAL,
            body_fat_percent REAL,
            chest_cm REAL,
            waist_cm REAL,
            hips_cm REAL,
            workout_completion INTEGER DEFAULT 0,
            energy_level INTEGER,
            notes TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(member_id) REFERENCES members(id)
        );

        CREATE TABLE IF NOT EXISTS workout_checkins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            member_id INTEGER NOT NULL,
            checkin_date TEXT NOT NULL,
            focus TEXT,
            completed_items TEXT,
            completion_percent INTEGER DEFAULT 0,
            notes TEXT,
            created_by INTEGER,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(member_id) REFERENCES members(id),
            FOREIGN KEY(created_by) REFERENCES users(id)
        );
        """
    )

    user_table_sql = cursor.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'users'"
    ).fetchone()[0]
    if "owner" not in user_table_sql or "accountant" not in user_table_sql:
        cursor.executescript(
            """
            ALTER TABLE users RENAME TO users_old;
            CREATE TABLE users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('admin', 'trainer', 'member', 'owner', 'accountant')),
                member_id INTEGER,
                trainer_id INTEGER,
                active INTEGER DEFAULT 1,
                must_change_password INTEGER DEFAULT 0,
                reset_token TEXT,
                reset_token_created_at TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(member_id) REFERENCES members(id),
                FOREIGN KEY(trainer_id) REFERENCES trainers(id)
            );
            INSERT INTO users (id, username, password_hash, role, member_id, trainer_id, active, created_at)
            SELECT id, username, password_hash, role, member_id, trainer_id, active, created_at
            FROM users_old;
            DROP TABLE users_old;
            """
        )

    member_columns = {row[1] for row in cursor.execute("PRAGMA table_info(members)").fetchall()}
    extra_member_columns = {
        "address": "TEXT",
        "emergency_contact": "TEXT",
        "fitness_level": "TEXT",
        "food_preference": "TEXT",
        "injury_notes": "TEXT",
        "primary_location": "TEXT",
        "primary_fitness_goal": "TEXT",
        "activity_level": "TEXT",
        "dietary_style": "TEXT",
        "food_exclusions": "TEXT",
        "other_foods_avoided": "TEXT",
        "meals_per_day": "TEXT",
        "cooking_preference": "TEXT",
        "medical_conditions": "TEXT",
        "supplements": "TEXT",
    }
    for column, column_type in extra_member_columns.items():
        if column not in member_columns:
            cursor.execute(f"ALTER TABLE members ADD COLUMN {column} {column_type}")

    notification_columns = {row[1] for row in cursor.execute("PRAGMA table_info(notifications)").fetchall()}
    if "event_key" not in notification_columns:
        cursor.execute("ALTER TABLE notifications ADD COLUMN event_key TEXT")

    payment_columns = {row[1] for row in cursor.execute("PRAGMA table_info(payments)").fetchall()}
    payment_extra_columns = {
        "payment_method": "TEXT",
        "invoice_number": "TEXT",
        "discount_amount": "REAL DEFAULT 0",
        "net_amount": "REAL",
        "upi_transaction_id": "TEXT",
    }
    for column, column_type in payment_extra_columns.items():
        if column not in payment_columns:
            cursor.execute(f"ALTER TABLE payments ADD COLUMN {column} {column_type}")

    user_columns = {row[1] for row in cursor.execute("PRAGMA table_info(users)").fetchall()}
    if "must_change_password" not in user_columns:
        cursor.execute("ALTER TABLE users ADD COLUMN must_change_password INTEGER DEFAULT 0")
    if "reset_token" not in user_columns:
        cursor.execute("ALTER TABLE users ADD COLUMN reset_token TEXT")
    if "reset_token_created_at" not in user_columns:
        cursor.execute("ALTER TABLE users ADD COLUMN reset_token_created_at TEXT")

    progress_count = cursor.execute("SELECT COUNT(*) FROM progress_entries").fetchone()[0]
    if progress_count == 0:
        cursor.executemany(
            """
            INSERT INTO progress_entries
            (member_id, entry_date, weight_kg, body_fat_percent, chest_cm, waist_cm, hips_cm,
             workout_completion, energy_level, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    1,
                    str(date.today() - timedelta(days=21)),
                    84,
                    27,
                    102,
                    94,
                    101,
                    62,
                    6,
                    "Baseline check-in. Focus on consistency and sleep.",
                ),
                (
                    1,
                    str(date.today() - timedelta(days=7)),
                    82,
                    25.5,
                    101,
                    91,
                    100,
                    78,
                    7,
                    "Improved attendance and better meal timing.",
                ),
            ],
        )

    trainer_count = cursor.execute("SELECT COUNT(*) FROM trainers").fetchone()[0]
    if trainer_count == 0:
        cursor.executemany(
            "INSERT INTO trainers (name, specialty, phone) VALUES (?, ?, ?)",
            [
                ("Aarav Sharma", "Strength and hypertrophy", "+919999000111"),
                ("Meera Patil", "Weight loss and mobility", "+919999000222"),
                ("Kabir Rao", "Functional fitness", "+919999000333"),
            ],
        )
        cursor.executemany(
            "INSERT INTO equipment (name, category, quantity, condition_status, maintenance_due) VALUES (?, ?, ?, ?, ?)",
            [
                ("Treadmill", "Cardio", 4, "Good", str(date.today() + timedelta(days=20))),
                ("Olympic Barbell", "Strength", 6, "Good", str(date.today() + timedelta(days=60))),
                ("Cable Crossover", "Strength", 1, "Service Soon", str(date.today() + timedelta(days=7))),
            ],
        )
        cursor.execute(
            """
            INSERT INTO members
            (name, phone, email, age, gender, height_cm, weight_kg, goal, fitness_level,
             food_preference, medical_notes, injury_notes,
             plan_name, premium, trainer_id, subscription_start, subscription_end, payment_status,
             workout_plan, diet_plan)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "Demo Member",
                "+919999111222",
                "demo@gym.local",
                29,
                "Male",
                175,
                82,
                "Fat loss with muscle gain",
                "Intermediate",
                "High-protein Indian vegetarian and eggs",
                "No major conditions",
                "No current injuries",
                "Quarterly",
                1,
                2,
                str(date.today() - timedelta(days=12)),
                str(date.today() + timedelta(days=78)),
                "Due",
                "",
                "",
            ),
        )
        connection.commit()

    for name, category, quantity, condition_status, due_days in PREBUILT_EQUIPMENT:
        existing_equipment = cursor.execute(
            "SELECT id FROM equipment WHERE lower(name) = lower(?) LIMIT 1",
            (name,),
        ).fetchone()
        if not existing_equipment:
            cursor.execute(
                """
                INSERT INTO equipment (name, category, quantity, condition_status, maintenance_due)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    name,
                    category,
                    quantity,
                    condition_status,
                    str(date.today() + timedelta(days=due_days)),
                ),
            )

    user_count = cursor.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    if user_count == 0:
        cursor.executemany(
            """
            INSERT INTO users (username, password_hash, role, member_id, trainer_id)
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                ("admin", generate_password_hash("admin123"), "admin", None, None),
                ("trainer", generate_password_hash("trainer123"), "trainer", None, 2),
                ("member", generate_password_hash("member123"), "member", 1, None),
            ],
        )
        connection.commit()

    for username, password, role in [
        ("owner", "owner123", "owner"),
        ("accountant", "accountant123", "accountant"),
    ]:
        existing_staff_user = cursor.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
        if not existing_staff_user:
            cursor.execute(
                "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
                (username, generate_password_hash(password), role),
            )

    connection.commit()
    connection.close()

    with app.app_context():
        for member in query_all("SELECT id, phone FROM members WHERE phone IS NOT NULL"):
            create_member_user(member["id"], member["phone"])
        for trainer in query_all("SELECT id, phone FROM trainers WHERE phone IS NOT NULL"):
            create_trainer_user(trainer["id"], trainer["phone"], reset_password=True)


def bmi(height_cm, weight_kg):
    if not height_cm or not weight_kg:
        return None
    meters = height_cm / 100
    return round(weight_kg / (meters * meters), 1)


def pack_choices(values):
    return "|".join(value for value in values if value)


def unpack_choices(value):
    if not value:
        return []
    return [item for item in value.split("|") if item]


def generate_rule_based_plans(member):
    member_bmi = bmi(member["height_cm"], member["weight_kg"])
    goal = (member["goal"] or "general fitness").lower()
    premium = bool(member["premium"])
    fitness_level = member["fitness_level"] or "Beginner"
    food_preference = member["food_preference"] or "balanced local meals"

    if "loss" in goal or "fat" in goal:
        nutrition_focus = "high-protein calorie deficit with high-fiber carbs"
        cardio = "25 minutes incline walk or cycling after strength work"
        calories = "Reduce portions by 10-15% while keeping protein high"
    elif "gain" in goal or "muscle" in goal:
        nutrition_focus = "lean calorie surplus with protein at every meal"
        cardio = "10 minutes easy cardio warm-up, no long cardio after lifting"
        calories = "Add one protein-rich snack and one carb serving around training"
    else:
        nutrition_focus = "balanced macros, hydration, and consistent meal timing"
        cardio = "15-20 minutes mixed cardio three times per week"
        calories = "Keep portions steady and track weekly progress"

    if member_bmi and member_bmi >= 30:
        safety_note = "Use joint-friendly progressions and avoid max-effort lifts until conditioning improves."
    elif member["injury_notes"] and member["injury_notes"].lower() not in {"none", "no"}:
        safety_note = f"Modify exercises for injury note: {member['injury_notes']}."
    elif member["medical_notes"] and member["medical_notes"].lower() not in {"none", "no"}:
        safety_note = f"Respect health note: {member['medical_notes']}. Get trainer clearance for pain or dizziness."
    else:
        safety_note = "Progress gradually and stop any movement that causes sharp pain."

    workout_days = [
        f"Level: {fitness_level}. Keep 1-2 reps in reserve on most sets.",
        "Day 1: Full-body strength - squats or leg press, chest press, seated row, plank.",
        f"Day 2: Cardio and mobility - {cardio}, hips, hamstrings, shoulders.",
        "Day 3: Upper body - lat pulldown, dumbbell press, cable row, curls, triceps pressdown.",
        "Day 4: Lower body - deadlift pattern, lunges, leg curl, calf raises, core holds.",
        "Day 5: Conditioning - intervals, sled pushes or battle ropes, stretching.",
    ]
    if premium:
        workout_days.append("Premium: Weekly trainer review, form videos, and progression adjustment every Monday.")

    diet_lines = [
        f"Goal focus: {nutrition_focus}.",
        f"Food preference: {food_preference}.",
        f"Calories: {calories}.",
        "Breakfast: Eggs or paneer/tofu bhurji, oats or poha, fruit.",
        "Lunch: Dal/chicken/fish/paneer, rice or roti, salad, curd.",
        "Snack: Whey/curd/sprouts plus nuts or fruit.",
        "Dinner: Lean protein, vegetables, small carb portion if training late.",
        "Hydration: 2.5-3.5 litres water daily; add electrolytes after heavy sweating.",
    ]
    if premium:
        diet_lines.extend(
            [
                "Premium add-on: Sunday meal-prep list and two flexible restaurant meals per week.",
                "Supplement note: Consider creatine monohydrate only if suitable and approved by your trainer.",
            ]
        )

    workout_plan = "\n".join(workout_days + [f"Safety: {safety_note}"])
    diet_plan = "\n".join(diet_lines + [f"Safety: {safety_note}"])
    return workout_plan, diet_plan


def member_ai_payload(member):
    return {
        "name": member["name"],
        "age": member["age"],
        "gender": member["gender"],
        "height_cm": member["height_cm"],
        "weight_kg": member["weight_kg"],
        "bmi": bmi(member["height_cm"], member["weight_kg"]),
        "goal": member["goal"],
        "primary_location": member["primary_location"],
        "primary_fitness_goal": member["primary_fitness_goal"],
        "activity_level": member["activity_level"],
        "dietary_style": member["dietary_style"],
        "food_exclusions": unpack_choices(member["food_exclusions"]),
        "other_foods_avoided": member["other_foods_avoided"],
        "meals_per_day": member["meals_per_day"],
        "cooking_preference": member["cooking_preference"],
        "medical_conditions": unpack_choices(member["medical_conditions"]),
        "supplements": unpack_choices(member["supplements"]),
        "fitness_level": member["fitness_level"],
        "food_preference": member["food_preference"],
        "medical_notes": member["medical_notes"],
        "injury_notes": member["injury_notes"],
        "membership_plan": member["plan_name"],
        "premium": bool(member["premium"]),
    }


def generate_ai_plans(member):
    if not os.environ.get("OPENAI_API_KEY"):
        return None

    try:
        from openai import OpenAI

        client = OpenAI()
        prompt = {
            "task": "Create a safe, practical gym workout plan and diet plan for this member.",
            "member": member_ai_payload(member),
            "requirements": [
                "Return only valid JSON with keys workout_plan, diet_plan, progress_message, safety_notes.",
                "Workout plan should be 5-6 clear training days with sets/reps/intensity and trainer-friendly notes.",
                "Diet plan should match food preference, Indian/local meal patterns when appropriate, hydration, and premium add-ons if premium is true.",
                "Respect medical and injury notes. Do not diagnose, treat disease, or override medical advice.",
                "Use concise plain text strings. No Markdown tables.",
            ],
        }
        response = client.responses.create(
            model=OPENAI_MODEL,
            input=[
                {
                    "role": "system",
                    "content": (
                        "You are a certified gym programming assistant for a gym management app. "
                        "Create fitness and nutrition guidance that is conservative, practical, and safe. "
                        "Advise professional medical clearance when health risks are present."
                    ),
                },
                {"role": "user", "content": json.dumps(prompt)},
            ],
        )
        data = json.loads(response.output_text)
        workout_plan = data.get("workout_plan", "").strip()
        diet_plan = data.get("diet_plan", "").strip()
        safety_notes = data.get("safety_notes", "").strip()
        progress_message = data.get("progress_message", "").strip()
        if not workout_plan or not diet_plan:
            return None
        if safety_notes:
            workout_plan = f"{workout_plan}\n\nSafety notes: {safety_notes}"
            diet_plan = f"{diet_plan}\n\nSafety notes: {safety_notes}"
        if progress_message:
            workout_plan = f"{workout_plan}\n\nProgress message: {progress_message}"
        return workout_plan, diet_plan
    except Exception as error:
        app.logger.warning("AI plan generation failed; using fallback. Error: %s", error)
        return None


def generate_plans(member, prefer_ai=True):
    if prefer_ai:
        ai_plans = generate_ai_plans(member)
        if ai_plans:
            return ai_plans
    return generate_rule_based_plans(member)


def dashboard_stats():
    return {
        "members": query_one("SELECT COUNT(*) AS count FROM members")["count"],
        "trainers": query_one("SELECT COUNT(*) AS count FROM trainers WHERE active = 1")["count"],
        "due_payments": query_one("SELECT COUNT(*) AS count FROM members WHERE payment_status = 'Due'")["count"],
        "today_attendance": query_one(
            "SELECT COUNT(*) AS count FROM attendance WHERE date(check_in) = date('now')"
        )["count"],
    }


def finance_stats():
    current_month_filter = "strftime('%Y-%m', COALESCE(paid_on, due_on)) = strftime('%Y-%m', 'now')"
    collected = query_one(
        f"SELECT COALESCE(SUM(COALESCE(net_amount, amount)), 0) AS total FROM payments WHERE status = 'Received' AND {current_month_filter}"
    )["total"]
    pending = query_one(
        f"SELECT COALESCE(SUM(COALESCE(net_amount, amount)), 0) AS total FROM payments WHERE status = 'Due' AND {current_month_filter}"
    )["total"]
    churn_risk = query_one(
        """
        SELECT COUNT(*) AS count
        FROM members
        WHERE payment_status != 'Paid'
          AND subscription_end IS NOT NULL
          AND date(subscription_end) < date('now')
          AND date(subscription_end) >= date('now', '-2 day')
        """
    )["count"]
    return {
        "monthly_revenue": query_one(
            "SELECT COALESCE(SUM(amount), 0) AS total FROM payments WHERE status = 'Received' AND strftime('%Y-%m', paid_on) = strftime('%Y-%m', 'now')"
        )["total"],
        "due_total": query_one("SELECT COALESCE(SUM(amount), 0) AS total FROM payments WHERE status = 'Due'")["total"],
        "cash_total": query_one(
            "SELECT COALESCE(SUM(amount), 0) AS total FROM payments WHERE status = 'Received' AND payment_method = 'Cash' AND strftime('%Y-%m', paid_on) = strftime('%Y-%m', 'now')"
        )["total"],
        "upi_total": query_one(
            "SELECT COALESCE(SUM(amount), 0) AS total FROM payments WHERE status = 'Received' AND payment_method = 'UPI' AND strftime('%Y-%m', paid_on) = strftime('%Y-%m', 'now')"
        )["total"],
        "card_total": query_one(
        "SELECT COALESCE(SUM(amount), 0) AS total FROM payments WHERE status = 'Received' AND payment_method = 'Card' AND strftime('%Y-%m', paid_on) = strftime('%Y-%m', 'now')"
        )["total"],
        "current_month_collected": collected,
        "current_month_pending": pending,
        "mrr": collected + pending,
        "churn_risk": churn_risk,
    }


def next_invoice_number():
    year = date.today().year
    count = query_one(
        "SELECT COUNT(*) AS count FROM payments WHERE invoice_number LIKE ?",
        (f"SL-{year}-%",),
    )["count"]
    return f"SL-{year}-{count + 1:05d}"


def money_value(value):
    try:
        return round(float(value or 0), 2)
    except (TypeError, ValueError):
        return 0.0


def finance_chart_data():
    daily_rows = query_all(
        """
        SELECT paid_on AS day, COALESCE(SUM(COALESCE(net_amount, amount)), 0) AS total
        FROM payments
        WHERE status = 'Received'
          AND paid_on IS NOT NULL
          AND strftime('%Y-%m', paid_on) = strftime('%Y-%m', 'now')
        GROUP BY paid_on
        ORDER BY paid_on
        """
    )
    method_rows = query_all(
        """
        SELECT COALESCE(payment_method, 'Unspecified') AS method, COALESCE(SUM(COALESCE(net_amount, amount)), 0) AS total
        FROM payments
        WHERE status = 'Received'
          AND strftime('%Y-%m', paid_on) = strftime('%Y-%m', 'now')
        GROUP BY COALESCE(payment_method, 'Unspecified')
        """
    )
    max_daily = max([row["total"] for row in daily_rows], default=1)
    points = []
    for index, row in enumerate(daily_rows):
        x = 20 + index * (260 / max(len(daily_rows) - 1, 1))
        y = 120 - ((row["total"] / max_daily) * 90)
        points.append({"x": round(x, 1), "y": round(y, 1), "day": row["day"], "total": row["total"]})
    total_methods = sum(row["total"] for row in method_rows) or 1
    methods = [
        {"method": row["method"], "total": row["total"], "percent": round((row["total"] / total_methods) * 100)}
        for row in method_rows
    ]
    return {"daily_points": points, "method_split": methods}


def wa_link(phone, message):
    digits = "".join(ch for ch in (phone or "") if ch.isdigit())
    return f"https://wa.me/{digits}?text={quote(message)}" if digits else "#"


def log_notification(member_id, message, attachment=None, event_key=None):
    if event_key:
        existing = query_one(
            "SELECT id FROM notifications WHERE event_key = ? LIMIT 1",
            (event_key,),
        )
        if existing:
            return False
    execute(
        "INSERT INTO notifications (member_id, message, attachment, event_key) VALUES (?, ?, ?, ?)",
        (member_id, message, attachment, event_key),
    )
    return True


def days_until(date_text):
    if not date_text:
        return None
    try:
        due_date = datetime.strptime(date_text, "%Y-%m-%d").date()
    except ValueError:
        return None
    return (due_date - date.today()).days


def progress_summary(progress_entries):
    if not progress_entries:
        return {
            "latest": None,
            "weight_change": None,
            "waist_change": None,
            "completion_change": None,
        }
    ordered = list(reversed(progress_entries))
    first = ordered[0]
    latest = ordered[-1]

    def diff(field):
        if first[field] is None or latest[field] is None:
            return None
        return round(latest[field] - first[field], 1)

    return {
        "latest": latest,
        "weight_change": diff("weight_kg"),
        "waist_change": diff("waist_cm"),
        "completion_change": diff("workout_completion"),
    }


def subscription_days_left(member):
    remaining = days_until(member["subscription_end"])
    return remaining


def infer_training_level(member):
    workout_plan = (member["workout_plan"] or "").lower()
    level = (member["fitness_level"] or "").lower()
    if "advanced" in workout_plan or "advanced" in level:
        return "Advanced"
    if "intermediate" in workout_plan or "intermediate" in level:
        return "Intermediate"
    return "Beginner"


def level_schedule(level):
    if level == "Advanced":
        return [
            "Push A",
            "Pull A",
            "Legs A",
            "Push B",
            "Pull B",
            "Legs B",
            "Rest and mobility",
        ]
    if level == "Intermediate":
        return [
            "Upper Body A",
            "Lower Body A",
            "Active recovery",
            "Upper Body B",
            "Lower Body B",
            "Mobility and cardio",
            "Rest",
        ]
    return [
        "Full Body A",
        "Recovery walk",
        "Full Body B",
        "Mobility",
        "Full Body C",
        "Easy cardio",
        "Rest",
    ]


def extract_day_plan(workout_plan, day_label):
    if not workout_plan:
        return []
    lines = [line.strip("- ").strip() for line in workout_plan.splitlines() if line.strip()]
    label_words = [word.lower() for word in day_label.replace("/", " ").split() if len(word) > 1]
    start = None
    for index, line in enumerate(lines):
        lower = line.lower()
        if lower.startswith("day") and all(word in lower for word in label_words[:2]):
            start = index
            break
        if day_label.lower() in lower and (lower.startswith("day") or " - " in line):
            start = index
            break
    if start is None:
        return []
    picked = []
    for line in lines[start + 1 :]:
        if line.lower().startswith("day ") and picked:
            break
        if line.lower().endswith("progression:") or line.lower().startswith("cardio:"):
            break
        if line.startswith("Universal Gym Workout Plan"):
            continue
        picked.append(line)
        if len(picked) >= 8:
            break
    return picked


def personalized_today_plan(member):
    level = infer_training_level(member)
    schedule = level_schedule(level)
    try:
        start_date = datetime.strptime(member["subscription_start"], "%Y-%m-%d").date()
    except (TypeError, ValueError):
        start_date = date.today()
    day_number = (date.today() - start_date).days % 7
    focus = schedule[day_number]
    workout_items = extract_day_plan(member["workout_plan"], focus)
    if not workout_items and "rest" not in focus.lower() and "recovery" not in focus.lower() and "mobility" not in focus.lower():
        workout_items = [
            f"{focus}: follow your saved workout plan with controlled form.",
            "Keep 1-3 reps in reserve unless your trainer says otherwise.",
            "Log completion percentage after training.",
        ]
    if not workout_items:
        workout_items = [
            "Easy walk or cycle for 15-25 minutes.",
            "Mobility flow for hips, shoulders, ankles, and thoracic spine.",
            "Prepare meals and hydrate well for the next training day.",
        ]

    if level == "Advanced":
        warmup = ["Cycle or treadmill 8-10 min", "2 ramp-up sets for first lift", "Shoulder/hip activation"]
        stretch = ["Chest doorway stretch", "Lat stretch", "Hip flexor stretch", "Hamstring stretch"]
        cardio = "20-30 min moderate, 2-5x/week depending on goal"
    elif level == "Intermediate":
        warmup = ["Treadmill or cycle 6-8 min", "Dynamic shoulder and hip circles", "1-2 light warm-up sets"]
        stretch = ["Shoulder stretch", "Quad stretch", "Hamstring stretch", "Calf stretch"]
        cardio = "15-20 min, 2-4x/week"
    else:
        warmup = ["Treadmill or cycle 5-10 min easy", "Joint warm-up: shoulders, hips, knees, ankles", "1 light warm-up set"]
        stretch = ["Neck and shoulder release", "Hip opener", "Hamstring stretch", "Calf stretch"]
        cardio = "10-15 min easy treadmill or cycle after workout"

    goal = member["primary_fitness_goal"] or member["goal"] or "General fitness"
    if "loss" in goal.lower() or "fat" in goal.lower():
        nutrition = "Prioritize protein, vegetables, water, and a controlled calorie deficit today."
    elif "muscle" in goal.lower() or "gain" in goal.lower():
        nutrition = "Hit protein target and include carbs around training for performance."
    else:
        nutrition = "Keep meals consistent and match portions to appetite and activity."

    return {
        "level": level,
        "day_number": day_number + 1,
        "focus": focus,
        "workout_items": workout_items,
        "warmup": warmup,
        "stretch": stretch,
        "cardio": cardio,
        "nutrition": nutrition,
        "subscription_days_left": subscription_days_left(member),
    }


def today_checkin(member_id):
    return query_one(
        "SELECT * FROM workout_checkins WHERE member_id = ? AND checkin_date = ? ORDER BY id DESC LIMIT 1",
        (member_id, date.today().isoformat()),
    )


def payment_due_message(member_name, amount, due_on, days_left):
    amount_text = f"Rs {amount:.2f}" if amount is not None else "your gym fee"
    if days_left is None:
        timing = "is due"
    elif days_left < 0:
        timing = f"was due {abs(days_left)} day(s) ago"
    elif days_left == 0:
        timing = "is due today"
    else:
        timing = f"is due in {days_left} day(s)"
    due_text = f" on {due_on}" if due_on else ""
    return f"Hi {member_name}, payment reminder: {amount_text} {timing}{due_text}. Please complete your gym payment."


def renewal_due_message(member_name, renewal_date, days_left):
    if days_left is None:
        timing = "is due soon"
    elif days_left < 0:
        timing = f"was due {abs(days_left)} day(s) ago"
    elif days_left == 0:
        timing = "is due today"
    else:
        timing = f"is due in {days_left} day(s)"
    return f"Hi {member_name}, your gym membership renewal {timing} on {renewal_date}. Please renew on time to continue your plan."


def queue_payment_due_reminders(days_ahead=PAYMENT_REMINDER_DAYS):
    created = 0
    scanned = 0
    today_text = date.today().isoformat()

    due_payments = query_all(
        """
        SELECT payments.*, members.name AS member_name, members.phone
        FROM payments JOIN members ON members.id = payments.member_id
        WHERE payments.status = 'Due'
          AND payments.due_on IS NOT NULL
          AND date(payments.due_on) <= date('now', ?)
        ORDER BY payments.due_on ASC
        """,
        (f"+{days_ahead} day",),
    )
    for payment in due_payments:
        scanned += 1
        days_left = days_until(payment["due_on"])
        event_key = f"payment:{payment['id']}:{today_text}"
        message = payment_due_message(payment["member_name"], payment["amount"], payment["due_on"], days_left)
        if log_notification(payment["member_id"], message, event_key=event_key):
            created += 1

    expiring_members = query_all(
        """
        SELECT *
        FROM members
        WHERE subscription_end IS NOT NULL
          AND (
            date(subscription_end) = date('now')
            OR date(subscription_end) = date('now', '+7 day')
            OR (payment_status = 'Due' AND date(subscription_end) <= date('now', ?))
          )
        ORDER BY subscription_end ASC
        """,
        (f"+{days_ahead} day",),
    )
    for member in expiring_members:
        scanned += 1
        days_left = days_until(member["subscription_end"])
        if days_left == 7:
            reminder_stage = "week-before"
        elif days_left == 0:
            reminder_stage = "renewal-day"
        elif days_left is not None and days_left < 0:
            reminder_stage = "overdue"
        else:
            reminder_stage = "due-window"
        event_key = f"renewal:{member['id']}:{member['subscription_end']}:{reminder_stage}:{today_text}"
        message = renewal_due_message(member["name"], member["subscription_end"], days_left)
        if log_notification(member["id"], message, event_key=event_key):
            created += 1

    return {"created": created, "scanned": scanned, "days_ahead": days_ahead}


def seed_prebuilt_equipment():
    created = 0
    for name, category, quantity, condition_status, due_days in PREBUILT_EQUIPMENT:
        existing_equipment = query_one(
            "SELECT id FROM equipment WHERE lower(name) = lower(?) LIMIT 1",
            (name,),
        )
        if existing_equipment:
            continue
        execute(
            """
            INSERT INTO equipment (name, category, quantity, condition_status, maintenance_due)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                name,
                category,
                quantity,
                condition_status,
                str(date.today() + timedelta(days=due_days)),
            ),
        )
        created += 1
    return created


def payment_reminder_worker():
    with app.app_context():
        init_db()
    while True:
        try:
            with app.app_context():
                queue_payment_due_reminders()
        except Exception as error:
            app.logger.warning("Payment reminder automation failed: %s", error)
        time.sleep(PAYMENT_REMINDER_INTERVAL_SECONDS)


def start_payment_automation():
    global _payment_automation_started
    with _payment_automation_lock:
        if _payment_automation_started:
            return
        _payment_automation_started = True
        thread = threading.Thread(target=payment_reminder_worker, daemon=True)
        thread.start()


def current_user():
    user_id = session.get("user_id")
    if not user_id:
        return None
    return query_one("SELECT * FROM users WHERE id = ? AND active = 1", (user_id,))


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user():
            return redirect(url_for("login"))
        return view(*args, **kwargs)

    return wrapped


def role_required(*roles):
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            user = current_user()
            if not user:
                return redirect(url_for("login"))
            if user["role"] not in roles:
                return redirect(url_for("index"))
            return view(*args, **kwargs)

        return wrapped

    return decorator


def password_change_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        user = current_user()
        allowed_endpoints = {"change_password", "logout", "static"}
        if user and user["must_change_password"] and request.endpoint not in allowed_endpoints:
            return redirect(url_for("change_password"))
        return view(*args, **kwargs)

    return wrapped


def can_view_member(user, member):
    if not user or not member:
        return False
    if user["role"] in {"admin", "owner"}:
        return True
    if user["role"] == "member":
        return user["member_id"] == member["id"]
    if user["role"] == "trainer":
        return user["trainer_id"] == member["trainer_id"] or member["trainer_id"] is None
    return False


def mobile_login_id(phone):
    username = "".join(ch for ch in (phone or "") if ch.isdigit())[-10:]
    return username or None


def default_mobile_password(phone):
    username = mobile_login_id(phone)
    if not username:
        return None
    return username[-4:] if len(username) >= 4 else "1234"


def create_or_update_mobile_user(role, phone, member_id=None, trainer_id=None, reset_password=False):
    username = mobile_login_id(phone)
    if not username:
        return None
    password = default_mobile_password(phone)
    username_owner = query_one("SELECT id FROM users WHERE username = ?", (username,))
    existing = query_one(
        "SELECT id FROM users WHERE role = ? AND (member_id = ? OR trainer_id = ?)",
        (role, member_id, trainer_id),
    )
    if username_owner:
        execute(
            "UPDATE users SET role = ?, member_id = ?, trainer_id = ?, active = 1 WHERE id = ?",
            (role, member_id, trainer_id, username_owner["id"]),
        )
        if existing and existing["id"] != username_owner["id"]:
            execute("DELETE FROM users WHERE id = ?", (existing["id"],))
        if reset_password:
            execute(
                "UPDATE users SET password_hash = ?, must_change_password = 1, reset_token = NULL, reset_token_created_at = NULL WHERE id = ?",
                (generate_password_hash(password), username_owner["id"]),
            )
        return username

    if existing:
        execute(
            "UPDATE users SET username = ?, member_id = ?, trainer_id = ?, active = 1 WHERE id = ?",
            (username, member_id, trainer_id, existing["id"]),
        )
        if reset_password:
            execute(
                "UPDATE users SET password_hash = ?, must_change_password = 1, reset_token = NULL, reset_token_created_at = NULL WHERE id = ?",
                (generate_password_hash(password), existing["id"]),
            )
        return username

    execute(
        "INSERT INTO users (username, password_hash, role, member_id, trainer_id, must_change_password) VALUES (?, ?, ?, ?, ?, 1)",
        (username, generate_password_hash(password), role, member_id, trainer_id),
    )
    return username


def create_member_user(member_id, phone, reset_password=False):
    return create_or_update_mobile_user("member", phone, member_id=member_id, reset_password=reset_password)


def create_trainer_user(trainer_id, phone, reset_password=False):
    return create_or_update_mobile_user("trainer", phone, trainer_id=trainer_id, reset_password=reset_password)


def get_member_login(member_id):
    return query_one(
        "SELECT id, username, active, created_at FROM users WHERE role = 'member' AND member_id = ?",
        (member_id,),
    )


def get_trainer_login(trainer_id):
    return query_one(
        "SELECT id, username, active, created_at FROM users WHERE role = 'trainer' AND trainer_id = ?",
        (trainer_id,),
    )


@app.before_request
def enforce_password_change():
    public_endpoints = {"login", "forgot_password", "reset_password", "static"}
    if request.endpoint in public_endpoints or request.endpoint is None:
        return None
    user = current_user()
    if user and user["must_change_password"] and request.endpoint not in {"change_password", "logout"}:
        return redirect(url_for("change_password"))
    return None


@app.context_processor
def inject_helpers():
    return {
        "wa_link": wa_link,
        "today": date.today,
        "current_user": current_user(),
        "ai_enabled": bool(os.environ.get("OPENAI_API_KEY")),
        "openai_model": OPENAI_MODEL,
    }


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        username_input = request.form["username"].strip()
        normalized_mobile = mobile_login_id(username_input)
        username = normalized_mobile if normalized_mobile and username_input.lower() != "admin" else username_input
        user = query_one(
            "SELECT * FROM users WHERE username = ? AND active = 1",
            (username,),
        )
        if user and check_password_hash(user["password_hash"], request.form["password"]):
            session.clear()
            session["user_id"] = user["id"]
            if user["must_change_password"]:
                return redirect(url_for("change_password"))
            return redirect(url_for("index"))
        error = "Invalid username or password."
    return render_template("login.html", error=error)


@app.route("/change-password", methods=["GET", "POST"])
@login_required
def change_password():
    user = current_user()
    error = None
    if request.method == "POST":
        current_password = request.form.get("current_password", "")
        new_password = request.form.get("new_password", "")
        confirm_password = request.form.get("confirm_password", "")
        if not check_password_hash(user["password_hash"], current_password):
            error = "Current password is incorrect."
        elif len(new_password) < 8:
            error = "New password must be at least 8 characters."
        elif new_password != confirm_password:
            error = "New passwords do not match."
        else:
            execute(
                "UPDATE users SET password_hash = ?, must_change_password = 0, reset_token = NULL, reset_token_created_at = NULL WHERE id = ?",
                (generate_password_hash(new_password), user["id"]),
            )
            return redirect(url_for("index"))
    return render_template("change_password.html", error=error, user=user)


@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    reset_link = None
    error = None
    if request.method == "POST":
        username = mobile_login_id(request.form.get("username", "")) or request.form.get("username", "").strip()
        user = query_one("SELECT * FROM users WHERE username = ? AND active = 1", (username,))
        if user:
            token = secrets.token_urlsafe(24)
            execute(
                "UPDATE users SET reset_token = ?, reset_token_created_at = ? WHERE id = ?",
                (token, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), user["id"]),
            )
            reset_link = url_for("reset_password", token=token, _external=True)
        else:
            error = "No active account found for that login ID."
    return render_template("forgot_password.html", reset_link=reset_link, error=error)


@app.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    user = query_one("SELECT * FROM users WHERE reset_token = ? AND active = 1", (token,))
    error = None
    if not user:
        return render_template("reset_password.html", error="Invalid or expired reset link.", token=token)
    if request.method == "POST":
        new_password = request.form.get("new_password", "")
        confirm_password = request.form.get("confirm_password", "")
        if len(new_password) < 8:
            error = "New password must be at least 8 characters."
        elif new_password != confirm_password:
            error = "New passwords do not match."
        else:
            execute(
                "UPDATE users SET password_hash = ?, must_change_password = 0, reset_token = NULL, reset_token_created_at = NULL WHERE id = ?",
                (generate_password_hash(new_password), user["id"]),
            )
            return redirect(url_for("login"))
    return render_template("reset_password.html", error=error, token=token, user=user)


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/")
@login_required
def index():
    user = current_user()
    if user["role"] == "member":
        return redirect(url_for("member_detail", member_id=user["member_id"]))
    if user["role"] == "owner":
        return redirect(url_for("owner_dashboard"))
    if user["role"] == "accountant":
        return redirect(url_for("accountant_dashboard"))

    member_filter = ""
    params = ()
    if user["role"] == "trainer":
        member_filter = "WHERE members.trainer_id = ? OR members.trainer_id IS NULL"
        params = (user["trainer_id"],)

    members = query_all(
        f"""
        SELECT members.*, trainers.name AS trainer_name
        FROM members LEFT JOIN trainers ON trainers.id = members.trainer_id
        {member_filter}
        ORDER BY members.created_at DESC
        """,
        params,
    )
    payments = query_all(
        """
        SELECT payments.*, members.name AS member_name
        FROM payments JOIN members ON members.id = payments.member_id
        ORDER BY payments.id DESC LIMIT 6
        """
    )
    equipment = query_all("SELECT * FROM equipment ORDER BY maintenance_due ASC")
    announcements = query_all("SELECT * FROM announcements ORDER BY id DESC LIMIT 4")
    return render_template(
        "dashboard.html",
        stats=dashboard_stats(),
        members=members,
        payments=payments,
        equipment=equipment,
        announcements=announcements,
    )


@app.route("/owner")
@role_required("admin", "owner")
def owner_dashboard():
    member_rows = query_all(
        """
        SELECT members.*, trainers.name AS trainer_name
        FROM members LEFT JOIN trainers ON trainers.id = members.trainer_id
        ORDER BY members.created_at DESC LIMIT 8
        """
    )
    equipment_watch = query_all(
        "SELECT * FROM equipment WHERE condition_status != 'Good' OR date(maintenance_due) <= date('now', '+14 day') ORDER BY maintenance_due ASC LIMIT 8"
    )
    renewals = query_all(
        "SELECT name, phone, subscription_end, payment_status FROM members WHERE subscription_end IS NOT NULL ORDER BY subscription_end ASC LIMIT 8"
    )
    attendance_by_day = query_all(
        """
        SELECT date(check_in) AS day, COUNT(*) AS visits
        FROM attendance
        GROUP BY date(check_in)
        ORDER BY day DESC LIMIT 7
        """
    )
    return render_template(
        "owner_dashboard.html",
        stats=dashboard_stats(),
        finance=finance_stats(),
        members=member_rows,
        equipment_watch=equipment_watch,
        renewals=renewals,
        attendance_by_day=attendance_by_day,
    )


@app.route("/accountant")
@role_required("admin", "owner", "accountant")
def accountant_dashboard():
    payments_due = query_all(
        """
        SELECT payments.*, members.name AS member_name, members.phone
        FROM payments JOIN members ON members.id = payments.member_id
        WHERE payments.status = 'Due'
        ORDER BY payments.due_on ASC LIMIT 12
        """
    )
    recent_payments = query_all(
        """
        SELECT payments.*, members.name AS member_name, members.phone
        FROM payments JOIN members ON members.id = payments.member_id
        ORDER BY payments.id DESC LIMIT 12
        """
    )
    renewal_queue = query_all(
        """
        SELECT notifications.*, members.name AS member_name, members.phone
        FROM notifications JOIN members ON members.id = notifications.member_id
        WHERE notifications.event_key LIKE 'renewal:%'
           OR notifications.event_key LIKE 'payment:%'
        ORDER BY notifications.id DESC LIMIT 12
        """
    )
    return render_template(
        "accountant_dashboard.html",
        finance=finance_stats(),
        payments_due=payments_due,
        recent_payments=recent_payments,
        renewal_queue=renewal_queue,
    )


@app.route("/members")
@role_required("admin", "owner", "trainer")
def members():
    user = current_user()
    member_filter = ""
    params = ()
    if user["role"] == "trainer":
        member_filter = "WHERE members.trainer_id = ? OR members.trainer_id IS NULL"
        params = (user["trainer_id"],)
    member_rows = query_all(
        f"""
        SELECT members.*, trainers.name AS trainer_name
        FROM members LEFT JOIN trainers ON trainers.id = members.trainer_id
        {member_filter}
        ORDER BY members.name
        """,
        params,
    )
    trainers = query_all("SELECT * FROM trainers WHERE active = 1 ORDER BY name")
    return render_template("members.html", members=member_rows, trainers=trainers)


@app.route("/members/add", methods=["POST"])
@role_required("admin")
def add_member():
    subscription_start = request.form.get("subscription_start") or str(date.today())
    subscription_end = request.form.get("subscription_end") or str(date.today() + timedelta(days=30))
    premium = 1 if request.form.get("premium") else 0
    cursor = db().execute(
        """
        INSERT INTO members
        (name, phone, email, address, emergency_contact, age, gender, height_cm, weight_kg,
         goal, fitness_level, food_preference, medical_notes, injury_notes,
         plan_name, premium, trainer_id, subscription_start, subscription_end, payment_status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            request.form["name"],
            request.form["phone"],
            request.form.get("email"),
            request.form.get("address"),
            request.form.get("emergency_contact"),
            request.form.get("age"),
            request.form.get("gender"),
            request.form.get("height_cm"),
            request.form.get("weight_kg"),
            request.form.get("goal"),
            request.form.get("fitness_level"),
            request.form.get("food_preference"),
            request.form.get("medical_notes"),
            request.form.get("injury_notes"),
            request.form.get("plan_name", "Monthly"),
            premium,
            request.form.get("trainer_id") or None,
            subscription_start,
            subscription_end,
            "Due",
        ),
    )
    db().commit()
    member = query_one("SELECT * FROM members WHERE id = ?", (cursor.lastrowid,))
    workout_plan, diet_plan = generate_plans(member, prefer_ai=True)
    execute(
        "UPDATE members SET workout_plan = ?, diet_plan = ? WHERE id = ?",
        (workout_plan, diet_plan, member["id"]),
    )
    log_notification(
        member["id"],
        f"Welcome {member['name']}! Your gym profile is ready. Your workout and diet plan has been generated.",
        "diet-plan.pdf",
    )
    create_member_user(member["id"], member["phone"])
    return redirect(url_for("member_detail", member_id=member["id"]))


@app.route("/members/<int:member_id>")
@login_required
def member_detail(member_id):
    member = query_one(
        """
        SELECT members.*, trainers.name AS trainer_name
        FROM members LEFT JOIN trainers ON trainers.id = members.trainer_id
        WHERE members.id = ?
        """,
        (member_id,),
    )
    if not can_view_member(current_user(), member):
        return redirect(url_for("index"))
    payments = query_all("SELECT * FROM payments WHERE member_id = ? ORDER BY id DESC", (member_id,))
    attendance = query_all(
        "SELECT * FROM attendance WHERE member_id = ? ORDER BY check_in DESC LIMIT 10", (member_id,)
    )
    notifications = query_all(
        "SELECT * FROM notifications WHERE member_id = ? ORDER BY id DESC LIMIT 8", (member_id,)
    )
    progress_entries = query_all(
        "SELECT * FROM progress_entries WHERE member_id = ? ORDER BY entry_date DESC, id DESC LIMIT 12",
        (member_id,),
    )
    checkin = today_checkin(member_id)
    workout_history = query_all(
        """
        SELECT workout_checkins.*, users.username AS created_by_name
        FROM workout_checkins LEFT JOIN users ON users.id = workout_checkins.created_by
        WHERE workout_checkins.member_id = ?
        ORDER BY workout_checkins.checkin_date DESC, workout_checkins.id DESC LIMIT 10
        """,
        (member_id,),
    )
    return render_template(
        "member_detail.html",
        member=member,
        payments=payments,
        attendance=attendance,
        notifications=notifications,
        progress_entries=progress_entries,
        progress_summary=progress_summary(progress_entries),
        workout_templates=PREBUILT_WORKOUT_PLANS,
        today_plan=personalized_today_plan(member),
        today_checkin=checkin,
        today_completed_items=unpack_choices(checkin["completed_items"]) if checkin else [],
        workout_history=workout_history,
        profile_options=MEMBER_PROFILE_OPTIONS,
        selected_food_exclusions=unpack_choices(member["food_exclusions"]),
        selected_medical_conditions=unpack_choices(member["medical_conditions"]),
        selected_supplements=unpack_choices(member["supplements"]),
        bmi=bmi(member["height_cm"], member["weight_kg"]),
    )


@app.route("/members/<int:member_id>/workout-checkin", methods=["POST"])
@login_required
def save_workout_checkin(member_id):
    member = query_one("SELECT * FROM members WHERE id = ?", (member_id,))
    user = current_user()
    if not can_view_member(user, member):
        return redirect(url_for("index"))

    today_plan = personalized_today_plan(member)
    completed_items = request.form.getlist("completed_items")
    total_items = len(today_plan["workout_items"]) or 1
    completion_percent = round((len(completed_items) / total_items) * 100)
    existing = today_checkin(member_id)
    payload = (
        today_plan["focus"],
        pack_choices(completed_items),
        completion_percent,
        request.form.get("notes"),
        user["id"],
    )
    if existing:
        execute(
            """
            UPDATE workout_checkins
            SET focus = ?, completed_items = ?, completion_percent = ?, notes = ?, created_by = ?
            WHERE id = ?
            """,
            payload + (existing["id"],),
        )
    else:
        execute(
            """
            INSERT INTO workout_checkins
            (member_id, checkin_date, focus, completed_items, completion_percent, notes, created_by)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (member_id, date.today().isoformat()) + payload,
        )

    if user["role"] in {"admin", "trainer"} and request.form.get("send_workout_update"):
        log_notification(
            member_id,
            f"Workout update for {member['name']}: {completion_percent}% completed for {today_plan['focus']}.",
        )
    return redirect(url_for("member_detail", member_id=member_id))


@app.route("/members/<int:member_id>/profile-questionnaire", methods=["POST"])
@role_required("admin", "trainer")
def update_profile_questionnaire(member_id):
    member = query_one("SELECT * FROM members WHERE id = ?", (member_id,))
    if not can_view_member(current_user(), member):
        return redirect(url_for("index"))

    execute(
        """
        UPDATE members
        SET name = ?, age = ?, weight_kg = ?, height_cm = ?, primary_location = ?,
            primary_fitness_goal = ?, goal = ?, activity_level = ?, dietary_style = ?,
            food_exclusions = ?, other_foods_avoided = ?, meals_per_day = ?,
            cooking_preference = ?, medical_conditions = ?, supplements = ?
        WHERE id = ?
        """,
        (
            request.form["name"],
            request.form.get("age"),
            request.form.get("weight_kg"),
            request.form.get("height_cm"),
            request.form.get("primary_location"),
            request.form.get("primary_fitness_goal"),
            request.form.get("primary_fitness_goal"),
            request.form.get("activity_level"),
            request.form.get("dietary_style"),
            pack_choices(request.form.getlist("food_exclusions")),
            request.form.get("other_foods_avoided"),
            request.form.get("meals_per_day"),
            request.form.get("cooking_preference"),
            pack_choices(request.form.getlist("medical_conditions")),
            pack_choices(request.form.getlist("supplements")),
            member_id,
        ),
    )
    return redirect(url_for("member_detail", member_id=member_id))


@app.route("/members/<int:member_id>/progress", methods=["POST"])
@role_required("admin", "trainer")
def add_progress(member_id):
    member = query_one("SELECT * FROM members WHERE id = ?", (member_id,))
    if not can_view_member(current_user(), member):
        return redirect(url_for("index"))

    execute(
        """
        INSERT INTO progress_entries
        (member_id, entry_date, weight_kg, body_fat_percent, chest_cm, waist_cm, hips_cm,
         workout_completion, energy_level, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            member_id,
            request.form.get("entry_date") or str(date.today()),
            request.form.get("weight_kg") or None,
            request.form.get("body_fat_percent") or None,
            request.form.get("chest_cm") or None,
            request.form.get("waist_cm") or None,
            request.form.get("hips_cm") or None,
            request.form.get("workout_completion") or 0,
            request.form.get("energy_level") or None,
            request.form.get("notes"),
        ),
    )

    if request.form.get("send_progress_update"):
        summary = (
            f"Hi {member['name']}, your progress has been updated. "
            f"Weight: {request.form.get('weight_kg') or 'not recorded'} kg, "
            f"workout completion: {request.form.get('workout_completion') or 0}%."
        )
        log_notification(member_id, summary)
    return redirect(url_for("member_detail", member_id=member_id))


@app.route("/members/<int:member_id>/plans", methods=["POST"])
@login_required
def update_member_plans(member_id):
    member = query_one("SELECT * FROM members WHERE id = ?", (member_id,))
    user = current_user()
    if not can_view_member(user, member) or user["role"] not in {"admin", "member"}:
        return redirect(url_for("index"))

    workout_plan = request.form.get("workout_plan", "").strip()
    diet_plan = request.form.get("diet_plan", "").strip()
    execute(
        "UPDATE members SET workout_plan = ?, diet_plan = ? WHERE id = ?",
        (workout_plan, diet_plan, member_id),
    )

    if user["role"] == "member":
        log_notification(
            member_id,
            f"{member['name']} updated their workout or diet plan from the member dashboard.",
        )
    return redirect(url_for("member_detail", member_id=member_id))


@app.route("/members/<int:member_id>/plans/apply-template", methods=["POST"])
@login_required
def apply_workout_template(member_id):
    member = query_one("SELECT * FROM members WHERE id = ?", (member_id,))
    user = current_user()
    if not can_view_member(user, member) or user["role"] not in {"admin", "member"}:
        return redirect(url_for("index"))

    template_key = request.form.get("template_key")
    template = PREBUILT_WORKOUT_PLANS.get(template_key)
    if not template:
        return redirect(url_for("member_detail", member_id=member_id))

    execute(
        "UPDATE members SET workout_plan = ? WHERE id = ?",
        (template["plan"], member_id),
    )
    log_notification(
        member_id,
        f"{template['name']} was applied to {member['name']}'s workout plan.",
    )
    return redirect(url_for("member_detail", member_id=member_id))


@app.route("/members/<int:member_id>/progress/<int:progress_id>/delete", methods=["POST"])
@role_required("admin", "trainer")
def delete_progress(member_id, progress_id):
    member = query_one("SELECT * FROM members WHERE id = ?", (member_id,))
    if not can_view_member(current_user(), member):
        return redirect(url_for("index"))
    execute("DELETE FROM progress_entries WHERE id = ? AND member_id = ?", (progress_id, member_id))
    return redirect(url_for("member_detail", member_id=member_id))


@app.route("/members/<int:member_id>/edit", methods=["GET", "POST"])
@role_required("admin")
def edit_member(member_id):
    member = query_one("SELECT * FROM members WHERE id = ?", (member_id,))
    trainers = query_all("SELECT * FROM trainers WHERE active = 1 ORDER BY name")
    member_login = get_member_login(member_id)
    if request.method == "POST":
        premium = 1 if request.form.get("premium") else 0
        execute(
            """
            UPDATE members
            SET name = ?, phone = ?, email = ?, address = ?, emergency_contact = ?,
                age = ?, gender = ?, height_cm = ?, weight_kg = ?,
                goal = ?, fitness_level = ?, food_preference = ?, medical_notes = ?, injury_notes = ?,
                plan_name = ?, premium = ?, trainer_id = ?,
                subscription_start = ?, subscription_end = ?, payment_status = ?,
                workout_plan = ?, diet_plan = ?
            WHERE id = ?
            """,
            (
                request.form["name"],
                request.form["phone"],
                request.form.get("email"),
                request.form.get("address"),
                request.form.get("emergency_contact"),
                request.form.get("age"),
                request.form.get("gender"),
                request.form.get("height_cm"),
                request.form.get("weight_kg"),
                request.form.get("goal"),
                request.form.get("fitness_level"),
                request.form.get("food_preference"),
                request.form.get("medical_notes"),
                request.form.get("injury_notes"),
                request.form.get("plan_name", "Monthly"),
                premium,
                request.form.get("trainer_id") or None,
                request.form.get("subscription_start"),
                request.form.get("subscription_end"),
                request.form.get("payment_status", "Due"),
                request.form.get("workout_plan"),
                request.form.get("diet_plan"),
                member_id,
            ),
        )
        member = query_one("SELECT * FROM members WHERE id = ?", (member_id,))
        if request.form.get("regenerate_plans"):
            workout_plan, diet_plan = generate_plans(member, prefer_ai=True)
            execute(
                "UPDATE members SET workout_plan = ?, diet_plan = ? WHERE id = ?",
                (workout_plan, diet_plan, member_id),
            )
        username = create_member_user(member_id, member["phone"])
        new_password = request.form.get("new_password", "").strip()
        if new_password:
            execute(
                "UPDATE users SET password_hash = ?, must_change_password = 1, reset_token = NULL, reset_token_created_at = NULL WHERE role = 'member' AND member_id = ?",
                (generate_password_hash(new_password), member_id),
            )
            log_notification(member_id, f"Hi {member['name']}, your member portal password was updated.")
        if request.form.get("send_profile_update"):
            log_notification(
                member_id,
                f"Hi {member['name']}, your gym profile has been updated. Login username: {username or 'ask reception'}.",
            )
        return redirect(url_for("member_detail", member_id=member_id))
    return render_template(
        "member_edit.html",
        member=member,
        trainers=trainers,
        member_login=member_login,
        default_password=default_mobile_password(member["phone"]),
    )


@app.route("/members/<int:member_id>/regenerate", methods=["POST"])
@role_required("admin", "trainer")
def regenerate(member_id):
    member = query_one("SELECT * FROM members WHERE id = ?", (member_id,))
    if not can_view_member(current_user(), member):
        return redirect(url_for("index"))
    workout_plan, diet_plan = generate_plans(member, prefer_ai=True)
    execute(
        "UPDATE members SET workout_plan = ?, diet_plan = ? WHERE id = ?",
        (workout_plan, diet_plan, member_id),
    )
    log_notification(member_id, f"Hi {member['name']}, your updated workout and diet plan is ready.", "diet-plan.pdf")
    return redirect(url_for("member_detail", member_id=member_id))


@app.route("/members/<int:member_id>/delete", methods=["POST"])
@role_required("admin")
def delete_member(member_id):
    execute("DELETE FROM members WHERE id = ?", (member_id,))
    return redirect(url_for("members"))


@app.route("/attendance", methods=["GET", "POST"])
@role_required("admin", "owner", "trainer")
def attendance():
    if request.method == "POST":
        member_id = request.form["member_id"]
        member = query_one("SELECT * FROM members WHERE id = ?", (member_id,))
        if current_user()["role"] == "trainer" and not can_view_member(current_user(), member):
            return redirect(url_for("attendance"))
        action = request.form["action"]
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if action == "in":
            execute("INSERT INTO attendance (member_id, check_in) VALUES (?, ?)", (member_id, now))
        else:
            open_row = query_one(
                "SELECT * FROM attendance WHERE member_id = ? AND check_out IS NULL ORDER BY id DESC LIMIT 1",
                (member_id,),
            )
            if open_row:
                execute("UPDATE attendance SET check_out = ? WHERE id = ?", (now, open_row["id"]))
        return redirect(url_for("attendance"))

    row_filter = ""
    params = ()
    if current_user()["role"] == "trainer":
        row_filter = "WHERE members.trainer_id = ? OR members.trainer_id IS NULL"
        params = (current_user()["trainer_id"],)
    rows = query_all(
        f"""
        SELECT attendance.*, members.name AS member_name
        FROM attendance JOIN members ON members.id = attendance.member_id
        {row_filter}
        ORDER BY attendance.check_in DESC LIMIT 50
        """,
        params,
    )
    if current_user()["role"] == "trainer":
        member_rows = query_all(
            "SELECT id, name FROM members WHERE trainer_id = ? OR trainer_id IS NULL ORDER BY name",
            (current_user()["trainer_id"],),
        )
    else:
        member_rows = query_all("SELECT id, name FROM members ORDER BY name")
    return render_template("attendance.html", attendance=rows, members=member_rows)


@app.route("/payments", methods=["GET", "POST"])
@role_required("admin", "owner", "accountant")
def payments():
    if request.method == "POST":
        status = request.form["status"]
        paid_on = str(date.today()) if status == "Received" else None
        amount = money_value(request.form["amount"])
        discount_amount = money_value(request.form.get("discount_amount"))
        net_amount = max(amount - discount_amount, 0)
        invoice_number = next_invoice_number()
        cursor = db().execute(
            """
            INSERT INTO payments
            (member_id, invoice_number, amount, discount_amount, net_amount, status, payment_method,
             upi_transaction_id, paid_on, due_on, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                request.form["member_id"],
                invoice_number,
                amount,
                discount_amount,
                net_amount,
                status,
                request.form.get("payment_method"),
                request.form.get("upi_transaction_id"),
                paid_on,
                request.form.get("due_on"),
                request.form.get("notes"),
            ),
        )
        db().commit()
        payment_id = cursor.lastrowid
        execute("UPDATE members SET payment_status = ? WHERE id = ?", ("Paid" if status == "Received" else "Due", request.form["member_id"]))
        member = query_one("SELECT * FROM members WHERE id = ?", (request.form["member_id"],))
        if status == "Received":
            method = request.form.get("payment_method") or "Not specified"
            renewal_start = request.form.get("renewal_start")
            renewal_end = request.form.get("renewal_end")
            if renewal_start or renewal_end:
                execute(
                    "UPDATE members SET subscription_start = COALESCE(?, subscription_start), subscription_end = COALESCE(?, subscription_end), plan_name = ? WHERE id = ?",
                    (renewal_start or None, renewal_end or None, request.form.get("plan_name") or member["plan_name"], member["id"]),
                )
                execute(
                    """
                    INSERT INTO renewal_history
                    (member_id, payment_id, plan_name, renewal_start, renewal_end, amount, discount_amount, payment_method)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        member["id"],
                        payment_id,
                        request.form.get("plan_name") or member["plan_name"],
                        renewal_start,
                        renewal_end,
                        net_amount,
                        discount_amount,
                        method,
                    ),
                )
            message = f"Payment received. Thank you {member['name']}! Invoice {invoice_number}, amount Rs {net_amount}. Method: {method}."
        else:
            message = f"Payment reminder for {member['name']}: Rs {net_amount} due on {request.form.get('due_on')}. Invoice {invoice_number}."
        log_notification(member["id"], message)
        return redirect(url_for("payments"))

    rows = query_all(
        """
        SELECT payments.*, members.name AS member_name, members.phone
        FROM payments JOIN members ON members.id = payments.member_id
        ORDER BY payments.id DESC
        """
    )
    member_rows = query_all("SELECT id, name FROM members ORDER BY name")
    renewal_rows = query_all(
        """
        SELECT renewal_history.*, members.name AS member_name
        FROM renewal_history JOIN members ON members.id = renewal_history.member_id
        ORDER BY renewal_history.id DESC LIMIT 12
        """
    )
    reminder_notifications = query_all(
        """
        SELECT notifications.*, members.name AS member_name, members.phone
        FROM notifications JOIN members ON members.id = notifications.member_id
        WHERE notifications.event_key LIKE 'payment:%'
           OR notifications.event_key LIKE 'subscription:%'
           OR notifications.event_key LIKE 'renewal:%'
        ORDER BY notifications.id DESC LIMIT 20
        """
    )
    due_count = query_one(
        """
        SELECT COUNT(*) AS count
        FROM payments
        WHERE status = 'Due'
          AND due_on IS NOT NULL
          AND date(due_on) <= date('now', ?)
        """,
        (f"+{PAYMENT_REMINDER_DAYS} day",),
    )["count"]
    return render_template(
        "payments.html",
        payments=rows,
        members=member_rows,
        reminder_notifications=reminder_notifications,
        due_count=due_count,
        reminder_days=PAYMENT_REMINDER_DAYS,
        renewals=renewal_rows,
        finance=finance_stats(),
        charts=finance_chart_data(),
    )


@app.route("/payments/run-reminders", methods=["POST"])
@role_required("admin", "owner", "accountant")
def run_payment_reminders():
    result = queue_payment_due_reminders()
    return redirect(url_for("payments", created=result["created"], scanned=result["scanned"]))


@app.route("/payments/batch-action", methods=["POST"])
@role_required("admin", "owner", "accountant")
def payment_batch_action():
    action = request.form.get("action")
    payment_ids = request.form.getlist("payment_ids")
    notification_ids = request.form.getlist("notification_ids")
    changed = 0

    if action == "queue_reminders":
        for payment_id in payment_ids:
            payment = query_one(
                """
                SELECT payments.*, members.name AS member_name
                FROM payments JOIN members ON members.id = payments.member_id
                WHERE payments.id = ?
                """,
                (payment_id,),
            )
            if payment:
                days_left = days_until(payment["due_on"])
                message = payment_due_message(
                    payment["member_name"],
                    payment["net_amount"] or payment["amount"],
                    payment["due_on"],
                    days_left,
                )
                event_key = f"manual-payment:{payment['id']}:{date.today().isoformat()}"
                if log_notification(payment["member_id"], message, event_key=event_key):
                    changed += 1
        for notification_id in notification_ids:
            execute("UPDATE notifications SET status = 'Queued' WHERE id = ?", (notification_id,))
            changed += 1

    if action == "mark_paid":
        for payment_id in payment_ids:
            payment = query_one("SELECT * FROM payments WHERE id = ?", (payment_id,))
            if payment and payment["status"] != "Received":
                execute(
                    "UPDATE payments SET status = 'Received', paid_on = COALESCE(paid_on, ?), payment_method = COALESCE(payment_method, 'Cash') WHERE id = ?",
                    (date.today().isoformat(), payment_id),
                )
                execute("UPDATE members SET payment_status = 'Paid' WHERE id = ?", (payment["member_id"],))
                changed += 1

    return redirect(url_for("payments", batch=changed, action=action or "none"))


@app.route("/payments/<int:payment_id>/receipt.pdf")
@role_required("admin", "owner", "accountant")
def payment_receipt_pdf(payment_id):
    payment = query_one(
        """
        SELECT payments.*, members.name AS member_name, members.phone, members.plan_name
        FROM payments JOIN members ON members.id = payments.member_id
        WHERE payments.id = ?
        """,
        (payment_id,),
    )
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    y = height - 56
    pdf.setFont("Helvetica-Bold", 20)
    pdf.drawString(52, y, "StrengthLab Payment Receipt")
    y -= 34
    pdf.setFont("Helvetica", 11)
    rows = [
        ("Invoice", payment["invoice_number"] or f"SL-{payment['id']}"),
        ("Member", payment["member_name"]),
        ("Phone", payment["phone"] or "-"),
        ("Plan", payment["plan_name"] or "-"),
        ("Status", payment["status"]),
        ("Payment method", payment["payment_method"] or "-"),
        ("UPI transaction ID", payment["upi_transaction_id"] or "-"),
        ("Amount", f"Rs {payment['amount'] or 0}"),
        ("Discount", f"Rs {payment['discount_amount'] or 0}"),
        ("Net paid/due", f"Rs {payment['net_amount'] or payment['amount'] or 0}"),
        ("Paid on / Due on", payment["paid_on"] or payment["due_on"] or "-"),
        ("Notes", payment["notes"] or "-"),
    ]
    for label, value in rows:
        pdf.setFont("Helvetica-Bold", 10)
        pdf.drawString(52, y, f"{label}:")
        pdf.setFont("Helvetica", 10)
        pdf.drawString(180, y, str(value))
        y -= 22
    pdf.setFont("Helvetica", 9)
    pdf.drawString(52, 52, "Generated by StrengthLab Local")
    pdf.save()
    buffer.seek(0)
    filename = f"{payment['invoice_number'] or 'receipt'}_receipt.pdf"
    return send_file(buffer, as_attachment=True, download_name=filename, mimetype="application/pdf")


@app.route("/payments/export.xlsx")
@role_required("admin", "owner", "accountant")
def export_payments_excel():
    rows = query_all(
        """
        SELECT payments.*, members.name AS member_name, members.phone
        FROM payments JOIN members ON members.id = payments.member_id
        ORDER BY payments.id DESC
        """
    )
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Payments"
    headers = [
        "Invoice",
        "Member",
        "Phone",
        "Amount",
        "Discount",
        "Net Amount",
        "Status",
        "Method",
        "UPI Transaction ID",
        "Paid On",
        "Due On",
        "Notes",
    ]
    sheet.append(headers)
    for row in rows:
        sheet.append(
            [
                row["invoice_number"],
                row["member_name"],
                row["phone"],
                row["amount"],
                row["discount_amount"],
                row["net_amount"] or row["amount"],
                row["status"],
                row["payment_method"],
                row["upi_transaction_id"],
                row["paid_on"],
                row["due_on"],
                row["notes"],
            ]
        )
    buffer = BytesIO()
    workbook.save(buffer)
    buffer.seek(0)
    return send_file(
        buffer,
        as_attachment=True,
        download_name=f"strengthlab_payments_{date.today().isoformat()}.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@app.route("/trainers", methods=["GET", "POST"])
@role_required("admin", "owner")
def trainers():
    if request.method == "POST":
        cursor = db().execute(
            "INSERT INTO trainers (name, specialty, phone) VALUES (?, ?, ?)",
            (request.form["name"], request.form.get("specialty"), request.form.get("phone")),
        )
        db().commit()
        create_trainer_user(cursor.lastrowid, request.form.get("phone"))
        return redirect(url_for("trainers"))
    rows = query_all(
        """
        SELECT trainers.*, users.username AS login_id
        FROM trainers LEFT JOIN users ON users.trainer_id = trainers.id AND users.role = 'trainer'
        ORDER BY trainers.name
        """
    )
    return render_template("trainers.html", trainers=rows)


@app.route("/trainers/<int:trainer_id>/edit", methods=["GET", "POST"])
@role_required("admin", "owner")
def edit_trainer(trainer_id):
    trainer = query_one("SELECT * FROM trainers WHERE id = ?", (trainer_id,))
    if request.method == "POST":
        execute(
            "UPDATE trainers SET name = ?, specialty = ?, phone = ?, active = ? WHERE id = ?",
            (
                request.form["name"],
                request.form.get("specialty"),
                request.form.get("phone"),
                1 if request.form.get("active") else 0,
                trainer_id,
            ),
        )
        create_trainer_user(
            trainer_id,
            request.form.get("phone"),
            reset_password=bool(request.form.get("reset_password")),
        )
        return redirect(url_for("trainers"))
    trainer_login = get_trainer_login(trainer_id)
    assigned_members = query_all(
        "SELECT id, name FROM members WHERE trainer_id = ? ORDER BY name",
        (trainer_id,),
    )
    return render_template(
        "trainer_edit.html",
        trainer=trainer,
        trainer_login=trainer_login,
        assigned_members=assigned_members,
        default_password=default_mobile_password(trainer["phone"]),
    )


@app.route("/trainers/<int:trainer_id>/delete", methods=["POST"])
@role_required("admin", "owner")
def delete_trainer(trainer_id):
    execute("UPDATE members SET trainer_id = NULL WHERE trainer_id = ?", (trainer_id,))
    execute("DELETE FROM users WHERE role = 'trainer' AND trainer_id = ?", (trainer_id,))
    execute("DELETE FROM trainers WHERE id = ?", (trainer_id,))
    return redirect(url_for("trainers"))


@app.route("/equipment", methods=["GET", "POST"])
@role_required("admin", "owner")
def equipment():
    if request.method == "POST":
        execute(
            "INSERT INTO equipment (name, category, quantity, condition_status, maintenance_due) VALUES (?, ?, ?, ?, ?)",
            (
                request.form["name"],
                request.form.get("category"),
                request.form.get("quantity", 1),
                request.form.get("condition_status", "Good"),
                request.form.get("maintenance_due"),
            ),
        )
        return redirect(url_for("equipment"))
    rows = query_all("SELECT * FROM equipment ORDER BY maintenance_due")
    return render_template("equipment.html", equipment=rows)


@app.route("/equipment/guide")
@login_required
def equipment_guide():
    return render_template(
        "equipment_guide.html",
        guide=BEGINNER_EQUIPMENT_GUIDE,
        source_url=EQUIPMENT_GUIDE_SOURCE,
    )


@app.route("/equipment/seed-prebuilt", methods=["POST"])
@role_required("admin", "owner")
def seed_equipment_route():
    created = seed_prebuilt_equipment()
    return redirect(url_for("equipment", created=created))


@app.route("/equipment/<int:equipment_id>/edit", methods=["GET", "POST"])
@role_required("admin", "owner")
def edit_equipment(equipment_id):
    item = query_one("SELECT * FROM equipment WHERE id = ?", (equipment_id,))
    if request.method == "POST":
        execute(
            """
            UPDATE equipment
            SET name = ?, category = ?, quantity = ?, condition_status = ?, maintenance_due = ?
            WHERE id = ?
            """,
            (
                request.form["name"],
                request.form.get("category"),
                request.form.get("quantity", 1),
                request.form.get("condition_status", "Good"),
                request.form.get("maintenance_due"),
                equipment_id,
            ),
        )
        return redirect(url_for("equipment"))
    return render_template("equipment_edit.html", item=item)


@app.route("/equipment/<int:equipment_id>/delete", methods=["POST"])
@role_required("admin", "owner")
def delete_equipment(equipment_id):
    execute("DELETE FROM equipment WHERE id = ?", (equipment_id,))
    return redirect(url_for("equipment"))


@app.route("/announcements", methods=["GET", "POST"])
@role_required("admin", "owner")
def announcements():
    if request.method == "POST":
        title = request.form["title"]
        message = request.form["message"]
        execute("INSERT INTO announcements (title, message) VALUES (?, ?)", (title, message))
        members = query_all("SELECT id FROM members")
        for member in members:
            log_notification(member["id"], f"{title}: {message}")
        return redirect(url_for("announcements"))
    rows = query_all("SELECT * FROM announcements ORDER BY id DESC")
    notifications = query_all(
        """
        SELECT notifications.*, members.name AS member_name, members.phone
        FROM notifications LEFT JOIN members ON members.id = notifications.member_id
        ORDER BY notifications.id DESC LIMIT 100
        """
    )
    return render_template("announcements.html", announcements=rows, notifications=notifications)


@app.route("/reports")
@role_required("admin", "owner", "accountant")
def reports():
    monthly_revenue = query_one(
        "SELECT COALESCE(SUM(amount), 0) AS total FROM payments WHERE status = 'Received' AND strftime('%Y-%m', paid_on) = strftime('%Y-%m', 'now')"
    )["total"]
    due_total = query_one(
        "SELECT COALESCE(SUM(amount), 0) AS total FROM payments WHERE status = 'Due'"
    )["total"]
    active_members = query_all(
        "SELECT name, subscription_end, payment_status FROM members ORDER BY subscription_end ASC"
    )
    attendance_by_day = query_all(
        """
        SELECT date(check_in) AS day, COUNT(*) AS visits
        FROM attendance
        GROUP BY date(check_in)
        ORDER BY day DESC LIMIT 14
        """
    )
    return render_template(
        "reports.html",
        monthly_revenue=monthly_revenue,
        due_total=due_total,
        active_members=active_members,
        attendance_by_day=attendance_by_day,
    )


@app.route("/members/<int:member_id>/diet.pdf")
@login_required
def diet_pdf(member_id):
    member = query_one("SELECT * FROM members WHERE id = ?", (member_id,))
    if not can_view_member(current_user(), member):
        return redirect(url_for("index"))
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    y = height - 52
    pdf.setFont("Helvetica-Bold", 18)
    pdf.drawString(52, y, f"Diet Plan - {member['name']}")
    y -= 30
    pdf.setFont("Helvetica", 10)
    pdf.drawString(52, y, f"Goal: {member['goal'] or 'General fitness'} | Plan: {member['plan_name']}")
    y -= 28
    pdf.setFont("Helvetica", 11)
    for paragraph in (member["diet_plan"] or "No diet plan generated yet.").splitlines():
        for line in textwrap.wrap(paragraph, width=88):
            if y < 60:
                pdf.showPage()
                y = height - 52
                pdf.setFont("Helvetica", 11)
            pdf.drawString(52, y, line)
            y -= 18
    pdf.save()
    buffer.seek(0)
    return send_file(buffer, as_attachment=True, download_name=f"{member['name'].replace(' ', '_')}_diet_plan.pdf", mimetype="application/pdf")


if __name__ == "__main__":
    init_db()
    start_payment_automation()
    debug = os.environ.get("FLASK_DEBUG", "").lower() in {"1", "true", "yes"}
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=debug)
