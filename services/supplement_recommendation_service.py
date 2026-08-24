def calculate_need_score(member, health_profile, nutrient):
    score = 0
    
    # Retrieve base member values
    diet_style = (member.get('dietary_style') or '').lower()
    food_excl = (member.get('food_exclusions') or '').lower()
    med_cond = (member.get('medical_conditions') or '').lower()
    goal = (member.get('goal') or member.get('primary_fitness_goal') or '').lower()
    notes = (member.get('medical_notes') or '').lower()
    
    # Retrieve health profile values
    meds = (health_profile.get('medications') or '').lower()
    is_veg = int(health_profile.get('vegetarian_vegan') or 0)
    sleep_qual = (health_profile.get('sleep_quality') or '').lower()
    stress_lvl = (health_profile.get('stress_level') or '').lower()
    sun_exp = (health_profile.get('sunlight_exposure') or '').lower()
    
    # 1. Vitamin B12
    if nutrient == "b12":
        if 'vegan' in diet_style or is_veg == 1:
            score += 3
        elif 'vegetarian' in diet_style or 'pure vegetarian' in diet_style:
            score += 2
        elif 'ovo-vegetarian' in diet_style or 'lacto-vegetarian' in diet_style:
            score += 1
            
        # Check low animal food or meat avoidance
        if 'meat' in food_excl or 'no seafood' in food_excl:
            score += 1
            
        # Metformin or PPI use
        if any(kw in meds for kw in ['metformin', 'ppi', 'omeprazole', 'pantoprazole', 'esomeprazole', 'antacid']):
            score += 2
            
        # Fatigue/low energy
        if any(kw in notes or kw in med_cond for kw in ['fatigue', 'tired', 'low energy']):
            score += 1

    # 2. Vitamin D
    elif nutrient == "vitamin_d":
        if sun_exp == "low":
            score += 3
        elif sun_exp == "moderate":
            score += 1
            
        if 'sedentary' in (member.get('activity_level') or '').lower():
            score += 2
            
        if any(kw in notes or kw in med_cond for kw in ['bone pain', 'joint pain', 'depression', 'low mood']):
            score += 1

    # 3. Magnesium
    elif nutrient == "magnesium":
        if sleep_qual == "poor":
            score += 2
        elif sleep_qual == "fair":
            score += 1
            
        if stress_lvl == "high":
            score += 2
        elif stress_lvl == "medium":
            score += 1
            
        if 'nuts' in food_excl:
            score += 1
            
        if 'cramp' in notes or 'spasm' in notes:
            score += 2

    # 4. Zinc
    elif nutrient == "zinc":
        if 'vegan' in diet_style or is_veg == 1 or 'vegetarian' in diet_style:
            score += 1
        if 'very active' in (member.get('activity_level') or '').lower():
            score += 1
        if any(kw in goal or kw in notes for kw in ['muscle', 'strength', 'recovery', 'wound']):
            score += 1

    # 5. Creatine monohydrate
    elif nutrient == "creatine":
        if any(kw in goal for kw in ['muscle', 'strength', 'hypertrophy', 'power']):
            score += 3
        if any(kw in (member.get('activity_level') or '').lower() for kw in ['very active', 'moderately active']):
            score += 1

    # 6. Protein powder
    elif nutrient == "protein":
        if any(kw in goal for kw in ['muscle', 'fat loss', 'strength', 'body composition']):
            score += 2
        if 'vegetarian' in diet_style or 'vegan' in diet_style or is_veg == 1:
            score += 1

    # 7. Iron
    elif nutrient == "iron":
        gender = (member.get('gender') or '').lower()
        age = member.get('age') or 0
        if gender == 'female' and age > 0 and age < 50:
            score += 2
        if 'vegan' in diet_style or is_veg == 1 or 'vegetarian' in diet_style:
            score += 2
        if any(kw in notes or kw in med_cond for kw in ['fatigue', 'tired', 'anemia']):
            score += 2

    # 8. Calcium
    elif nutrient == "calcium":
        if 'vegan' in diet_style or is_veg == 1:
            score += 2
        if 'lactose' in food_excl:
            score += 2
        if (member.get('age') or 0) > 50:
            score += 1

    # 9. Iodine
    elif nutrient == "iodine":
        if 'vegan' in diet_style or is_veg == 1 or 'no seafood' in food_excl:
            score += 2

    # 10. Omega-3
    elif nutrient == "omega-3":
        if 'no seafood' in food_excl or 'vegan' in diet_style or 'vegetarian' in diet_style or is_veg == 1:
            score += 3

    # 11. Electrolytes
    elif nutrient == "electrolytes":
        if 'very active' in (member.get('activity_level') or '').lower():
            score += 2
        if 'cramp' in notes or 'sweat' in notes:
            score += 1

    # 12. Caffeine
    elif nutrient == "caffeine":
        if any(kw in goal for kw in ['strength', 'performance', 'energy']):
            score += 1

    # 13. Fiber / psyllium
    elif nutrient == "fiber":
        if 'digestive issues' in med_cond or 'constipation' in notes:
            score += 3

    return score


def safety_gate(member, health_profile, supplement):
    """
    Evaluates key medical contraindications and returns a list of warning messages.
    """
    red_flags = []
    
    preg = (health_profile.get('pregnancy_lactation_status') or '').lower()
    kidney = int(health_profile.get('kidney_disease') or 0)
    liver = int(health_profile.get('liver_disease') or 0)
    meds = (health_profile.get('medications') or '').lower()
    
    if preg in ['yes', 'y', 'pregnant', 'lactating', 'breastfeeding']:
        red_flags.append("Pregnancy/lactation status. All supplement options require formal clinician clearance.")
        
    if kidney == 1:
        if supplement in ['Magnesium', 'Creatine monohydrate', 'Electrolytes', 'Calcium', 'Iron']:
            red_flags.append("Active kidney disease reported. Contraindicated due to renal clearance limitations.")
            
    if liver == 1:
        if supplement in ['Caffeine', 'Creatine monohydrate', 'Iron']:
            red_flags.append("Liver condition reported. Supplement review required to prevent hepatotoxicity.")
            
    if meds:
        red_flags.append("Currently taking active medications. Check for potential interactions before starting supplementation.")
        
    return red_flags


def plan_safety_gate(member, health_profile):
    """
    Reuses the supplement safety_gate contract to evaluate whether a workout
    or diet plan should be blocked due to health contraindications.

    Calls safety_gate with a representative supplement (Creatine monohydrate)
    because it triggers both kidney and liver branches, and the medication
    branch is supplement-agnostic.  Returns a list of plan-centric blocking
    reasons; an empty list means the plan may proceed to review.
    """
    # Creatine monohydrate triggers pregnancy, kidney, liver, and medication gates
    warnings = safety_gate(member, health_profile, "Creatine monohydrate")
    reasons = []
    for w in warnings:
        if "Pregnancy/lactation" in w:
            reasons.append("Pregnancy/lactation status. All exercise and nutrition plans require formal clinician clearance.")
        elif "kidney disease" in w.lower():
            reasons.append("Active kidney disease reported. Plan review required due to renal clearance and protein load considerations.")
        elif "liver condition" in w.lower():
            reasons.append("Liver condition reported. Plan review required to prevent hepatotoxicity and metabolic stress.")
        elif "medication" in w.lower():
            reasons.append("Currently taking active medications. Exercise and nutrition plans require clinician review for potential interactions.")
        else:
            reasons.append(w)
    return reasons


def get_recommendation_level(score, safety_warnings, is_contraindicated=False):
    """
    Determines recommendation level based on need score and safety warning flags.
    """
    if is_contraindicated:
        return 'do_not_recommend'
        
    if any("Pregnancy" in w or "kidney disease" in w.lower() or "liver condition" in w.lower() for w in safety_warnings):
        return 'clinician_review_required'
        
    if score >= 4:
        return 'lab_suggested'
    elif score == 3:
        return 'supplement_candidate'
    elif score == 2:
        return 'food_first'
    else:
        return 'education_only'
