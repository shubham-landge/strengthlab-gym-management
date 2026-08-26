"""Curated local catalogue of movements and foods.

This exists so plan generation is grounded in what this gym actually owns and
what this member can actually eat, before any AI is involved. Two consequences:

1. Quality does not depend on a provider being reachable. The rule engine reads
   the same catalogue the AI prompt is built from.
2. The AI is given a closed list to choose from rather than being asked to
   invent. A model cannot prescribe a hack squat the gym does not have, or
   suggest paneer to a vegan, if neither is in the list it was handed.

Macros are per 100 g and approximate: published values vary by cultivar,
preparation and source. Every row carries where its numbers came from so a
trainer can check rather than trust.
"""

# --- movements --------------------------------------------------------------
# equipment: matched case-insensitively against the gym's equipment table, so a
# movement only ever appears if the machine is actually on the floor.

EXERCISES = [
    # name, pattern, role, primary, secondary, equipment, level, contraindications, regression, progression, cues
    ("Dumbbell Flat Bench Press", "horizontal push", "compound", "chest", "triceps,front delts",
     "Dumbbells", "beginner", "shoulder impingement",
     "Pec Deck Fly", "Olympic Barbell Bench Press",
     "Shoulder blades pinned back|Elbows about 45° from the ribs|Lower to mid-chest, not the neck"),
    ("Olympic Barbell Bench Press", "horizontal push", "compound", "chest", "triceps,front delts",
     "Olympic Barbell", "intermediate", "shoulder impingement",
     "Dumbbell Flat Bench Press", "Decline Bench Olympic Press",
     "Full foot contact with the floor|Bar path to the sternum|Wrists stacked over elbows"),
    ("Dumbbell Decline Bench Press", "horizontal push", "compound", "lower chest", "triceps",
     "Adjustable Olympia Flat to Decline Bench", "intermediate", "",
     "Dumbbell Flat Bench Press", "Decline Bench Olympic",
     "Control the descent|Keep ribs down|Stop short of full lockout to keep tension"),
    ("Pec Deck Fly", "horizontal push", "isolation", "chest", "front delts",
     "Pec Deck Fly", "beginner", "shoulder impingement",
     "", "Cable Crossover",
     "Slight elbow bend, fixed|Squeeze for a beat at the middle|Do not let the plates touch down"),
    ("Cable Crossover", "horizontal push", "isolation", "chest", "front delts",
     "Cable Crossover", "intermediate", "",
     "Pec Deck Fly", "",
     "Step forward to keep tension|Meet the hands slightly below the sternum|Stay tall through the chest"),
    ("Dumbbell Shoulder Press", "vertical push", "compound", "front delts", "triceps",
     "Dumbbells", "beginner", "shoulder impingement,neck pain",
     "Seated Lateral Raise Machine", "Olympic Barbell Overhead Press",
     "Ribs down, no arch|Press slightly forward of the ears|Full lockout without shrugging"),
    ("Seated Lateral Raise Machine", "vertical push", "isolation", "side delts", "",
     "Seated Lateral Raise Machine", "beginner", "",
     "", "Dumbbell Lateral Raise",
     "Lead with the elbows|Stop at shoulder height|No bouncing out of the bottom"),
    ("Parallel Bar Dip", "vertical push", "compound", "lower chest", "triceps",
     "Parallel Bar / Chin-Up / Leg Raise Stand", "intermediate", "shoulder impingement",
     "Parallel Bar Knee Raise", "",
     "Lean the torso forward for chest|Shoulders stay above the elbows|Stop before the shoulder rolls"),
    ("Lat Pulldown", "vertical pull", "compound", "lats", "biceps,rear delts",
     "Lat Pulldown", "beginner", "",
     "", "Chin-Up",
     "Drive the elbows to the ribs|Chest up, slight lean back|Do not pull behind the neck"),
    ("Chin-Up", "vertical pull", "compound", "lats", "biceps",
     "Parallel Bar / Chin-Up / Leg Raise Stand", "advanced", "elbow pain",
     "Lat Pulldown", "",
     "Full hang at the bottom|Chest towards the bar|Control the lowering"),
    ("One-Arm Dumbbell Row", "horizontal pull", "compound", "lats", "rear delts,biceps",
     "Dumbbells", "beginner", "lower back pain",
     "Lat Pulldown", "Barbell Row",
     "Flat back, hips square|Pull to the hip, not the shoulder|Do not rotate the torso"),
    ("Preacher Curl", "elbow flexion", "isolation", "biceps", "forearms",
     "Preacher Curl", "beginner", "elbow pain",
     "", "Dumbbell Curl",
     "Armpits on the pad|Stop just short of lockout|Slow on the way down"),
    ("Leg Press", "squat", "compound", "quads", "glutes,hamstrings",
     "Leg Press", "beginner", "knee pain,lower back pain",
     "", "Barbell Squat",
     "Feet shoulder width, mid-platform|Do not let the lower back round|Knees track over the toes"),
    ("Dumbbell Goblet Squat", "squat", "compound", "quads", "glutes,core",
     "Dumbbells", "beginner", "knee pain",
     "Leg Press", "Barbell Squat",
     "Elbows inside the knees|Chest tall throughout|Sit between the hips"),
    ("Dumbbell Split Squat", "lunge", "compound", "quads", "glutes",
     "Dumbbells", "intermediate", "knee pain",
     "Dumbbell Goblet Squat", "Dumbbell Walking Lunge",
     "Front shin near vertical|Back knee travels straight down|Weight through the front heel"),
    ("Dumbbell Walking Lunge", "lunge", "compound", "quads", "glutes,hamstrings",
     "Dumbbells", "intermediate", "knee pain,balance issues",
     "Dumbbell Split Squat", "",
     "Long enough step to load the glute|Torso upright|Do not let the back knee crash"),
    ("Dumbbell Romanian Deadlift", "hinge", "compound", "hamstrings", "glutes,lower back",
     "Dumbbells", "intermediate", "lower back pain",
     "Seated Leg Curl", "Barbell Romanian Deadlift",
     "Push the hips back, do not squat|Bar close to the legs|Stop when the hamstrings run out"),
    ("Seated Leg Curl", "knee flexion", "isolation", "hamstrings", "",
     "Seated Leg Curl", "beginner", "",
     "", "Dumbbell Romanian Deadlift",
     "Pad above the heels|Full range, controlled|Do not lift the hips off the seat"),
    ("Back Extension", "hinge", "isolation", "lower back", "glutes,hamstrings",
     "Back Extension", "beginner", "lower back pain",
     "", "Weighted Back Extension",
     "Hinge at the hip, not the spine|Stop level with the torso|Squeeze the glutes at the top"),
    ("Standing Calf Raise", "ankle", "isolation", "calves", "",
     "Standing Calf Raise", "beginner", "achilles pain",
     "Seated Calf Raise", "",
     "Full stretch at the bottom|Pause at the top|No bouncing"),
    ("Seated Calf Raise", "ankle", "isolation", "calves", "",
     "Seated Calf Raise", "beginner", "achilles pain",
     "", "Standing Calf Raise",
     "Knees at 90°|Drive through the ball of the foot|Slow negative"),
    ("Hanging Knee Raise", "core", "core", "abs", "hip flexors",
     "Parallel Bar / Chin-Up / Leg Raise Stand", "intermediate", "lower back pain",
     "Parallel Bar Knee Raise", "Hanging Leg Raise",
     "Curl the pelvis, do not just lift the legs|No swinging|Lower under control"),
    ("Parallel Bar Knee Raise", "core", "core", "abs", "hip flexors",
     "Parallel Bar / Chin-Up / Leg Raise Stand", "beginner", "",
     "", "Hanging Knee Raise",
     "Back flat against the pad|Bring the knees to the chest|Control the return"),
    ("Treadmill Incline Walk", "conditioning", "conditioning", "full body", "",
     "Treadmill", "beginner", "",
     "", "Treadmill Intervals",
     "Conversational pace|Do not hold the rails|Incline before speed"),
    ("Cycle", "conditioning", "conditioning", "full body", "",
     "Cycle", "beginner", "",
     "", "Cycle Intervals",
     "Seat height at near-full leg extension|Steady cadence|Nasal breathing if you can"),
]

EXERCISE_FIELDS = (
    "name", "movement_pattern", "role", "primary_muscle", "secondary_muscles",
    "equipment", "level", "contraindications", "regression", "progression", "cues",
)


# --- foods ------------------------------------------------------------------
# Macros per 100 g of the stated form (raw/dry unless the name says cooked).

FOODS = [
    # name, category, kcal, protein, carb, fat, veg, vegan, allergens, exchange_group, portion_g, portion_label, source
    ("Paneer", "protein", 265, 18.3, 1.2, 20.8, 1, 0, "dairy", "protein-veg", 100, "100 g", "IFCT 2017 / ICMR-NIN"),
    ("Tofu", "protein", 76, 8.0, 1.9, 4.8, 1, 1, "soy", "protein-veg", 150, "150 g", "USDA FoodData Central"),
    ("Soya chunks (dry)", "protein", 345, 52.0, 33.0, 0.5, 1, 1, "soy", "protein-veg", 40, "40 g dry", "Label / NIN range 47-53 g"),
    ("Curd (dahi)", "protein", 60, 3.1, 4.7, 3.3, 1, 0, "dairy", "protein-veg", 200, "1 bowl 200 g", "IFCT 2017 / ICMR-NIN"),
    ("Greek yoghurt", "protein", 97, 9.0, 3.9, 5.0, 1, 0, "dairy", "protein-veg", 150, "150 g", "USDA FoodData Central"),
    ("Milk (toned)", "protein", 58, 3.1, 4.7, 3.0, 1, 0, "dairy", "protein-veg", 250, "1 glass 250 ml", "IFCT 2017 / ICMR-NIN"),
    ("Whey protein", "protein", 380, 78.0, 8.0, 5.0, 1, 0, "dairy", "protein-veg", 30, "1 scoop 30 g", "Typical label value"),
    ("Egg (whole)", "protein", 143, 12.6, 0.7, 9.5, 0, 0, "egg", "protein-egg", 100, "2 eggs", "USDA FoodData Central"),
    ("Chicken breast", "protein", 165, 31.0, 0.0, 3.6, 0, 0, "", "protein-meat", 150, "150 g", "USDA FoodData Central"),
    ("Fish (rohu)", "protein", 97, 16.6, 0.0, 1.4, 0, 0, "fish", "protein-meat", 150, "150 g", "IFCT 2017 / ICMR-NIN"),
    ("Moong dal (dry)", "protein", 348, 24.0, 59.0, 1.2, 1, 1, "", "protein-veg", 60, "60 g dry", "IFCT 2017 / ICMR-NIN"),
    ("Toor dal (dry)", "protein", 343, 22.3, 57.6, 1.7, 1, 1, "", "protein-veg", 60, "60 g dry", "IFCT 2017 / ICMR-NIN"),
    ("Rajma (dry)", "protein", 346, 24.0, 60.0, 1.0, 1, 1, "", "protein-veg", 60, "60 g dry", "IFCT 2017 / ICMR-NIN"),
    ("Chana / chickpeas (dry)", "protein", 364, 19.0, 61.0, 6.0, 1, 1, "", "protein-veg", 60, "60 g dry", "IFCT 2017 / ICMR-NIN"),
    ("Sprouts (moong)", "protein", 30, 3.0, 6.0, 0.2, 1, 1, "", "protein-veg", 120, "1 bowl 120 g", "IFCT 2017 / ICMR-NIN"),
    ("Sattu", "protein", 406, 20.0, 65.0, 5.0, 1, 1, "", "protein-veg", 40, "40 g", "IFCT 2017 / ICMR-NIN"),

    ("Roti / chapati", "carb", 297, 11.0, 58.0, 3.7, 1, 1, "gluten", "carb-grain", 40, "1 roti 40 g", "IFCT 2017 / ICMR-NIN"),
    ("Rice (raw)", "carb", 345, 6.8, 78.2, 0.5, 1, 1, "", "carb-grain", 60, "60 g dry", "IFCT 2017 / ICMR-NIN"),
    ("Oats", "carb", 389, 12.0, 66.0, 7.0, 1, 1, "gluten", "carb-grain", 60, "60 g", "USDA FoodData Central"),
    ("Poha (flattened rice)", "carb", 346, 6.6, 77.3, 1.2, 1, 1, "", "carb-grain", 80, "80 g dry", "IFCT 2017 / ICMR-NIN"),
    ("Dalia (broken wheat)", "carb", 342, 12.0, 71.0, 1.5, 1, 1, "gluten", "carb-grain", 60, "60 g dry", "IFCT 2017 / ICMR-NIN"),
    ("Quinoa", "carb", 368, 14.1, 64.2, 6.1, 1, 1, "", "carb-grain", 60, "60 g dry", "USDA FoodData Central"),
    ("Potato", "carb", 97, 1.6, 22.6, 0.1, 1, 1, "", "carb-starch", 200, "200 g", "IFCT 2017 / ICMR-NIN"),
    ("Sweet potato", "carb", 86, 1.6, 20.1, 0.1, 1, 1, "", "carb-starch", 200, "200 g", "USDA FoodData Central"),

    ("Banana", "fruit", 89, 1.1, 22.8, 0.3, 1, 1, "", "fruit", 120, "1 medium", "USDA FoodData Central"),
    ("Apple", "fruit", 52, 0.3, 13.8, 0.2, 1, 1, "", "fruit", 180, "1 medium", "USDA FoodData Central"),
    ("Guava", "fruit", 68, 2.6, 14.3, 1.0, 1, 1, "", "fruit", 150, "1 medium", "IFCT 2017 / ICMR-NIN"),
    ("Dates", "fruit", 277, 1.8, 75.0, 0.2, 1, 1, "", "fruit", 24, "3 dates", "USDA FoodData Central"),

    ("Peanuts", "fat", 567, 25.8, 16.1, 49.2, 1, 1, "nuts", "fat-nut", 25, "25 g", "USDA FoodData Central"),
    ("Almonds", "fat", 579, 21.2, 21.6, 49.9, 1, 1, "nuts", "fat-nut", 20, "20 g", "USDA FoodData Central"),
    ("Walnuts", "fat", 654, 15.2, 13.7, 65.2, 1, 1, "nuts", "fat-nut", 20, "20 g", "USDA FoodData Central"),
    ("Pumpkin seeds", "fat", 559, 30.2, 10.7, 49.1, 1, 1, "", "fat-seed", 25, "25 g", "USDA FoodData Central"),
    ("Ghee", "fat", 900, 0.0, 0.0, 100.0, 1, 0, "dairy", "fat-oil", 10, "1 tsp 5 g", "IFCT 2017 / ICMR-NIN"),
    ("Mustard oil", "fat", 884, 0.0, 0.0, 100.0, 1, 1, "", "fat-oil", 10, "2 tsp 10 g", "IFCT 2017 / ICMR-NIN"),

    ("Spinach (palak)", "vegetable", 23, 2.9, 3.6, 0.4, 1, 1, "", "vegetable", 150, "1 bowl", "IFCT 2017 / ICMR-NIN"),
    ("Mixed vegetables", "vegetable", 45, 2.0, 8.0, 0.3, 1, 1, "", "vegetable", 200, "1 bowl", "IFCT 2017 / ICMR-NIN"),
    ("Cucumber salad", "vegetable", 16, 0.7, 3.6, 0.1, 1, 1, "", "vegetable", 150, "1 plate", "USDA FoodData Central"),
]

FOOD_FIELDS = (
    "name", "category", "kcal_100g", "protein_100g", "carb_100g", "fat_100g",
    "vegetarian", "vegan", "allergens", "exchange_group",
    "typical_portion_g", "portion_label", "source",
)
