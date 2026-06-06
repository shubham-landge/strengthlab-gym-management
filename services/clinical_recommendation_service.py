import sqlite3
from services.supplement_recommendation_service import (
    calculate_need_score,
    safety_gate,
    get_recommendation_level
)

def get_or_create_health_profile(db_conn, member_id):
    cursor = db_conn.cursor()
    cursor.execute("SELECT * FROM member_health_profiles WHERE member_id = ?", (member_id,))
    row = cursor.fetchone()
    if row:
        return dict(row)
    
    cursor.execute(
        """
        INSERT INTO member_health_profiles (
            member_id, sleep_quality, stress_level, medications, allergies, 
            pregnancy_lactation_status, kidney_disease, liver_disease, 
            thyroid_condition, diabetes_prediabetes, blood_pressure, 
            vegetarian_vegan, alcohol_intake, sunlight_exposure, 
            current_supplements, recent_lab_values
        )
        VALUES (?, '', '', '', '', '', 0, 0, 0, 0, '', 0, '', '', '', '')
        """,
        (member_id,)
    )
    db_conn.commit()
    cursor.execute("SELECT * FROM member_health_profiles WHERE member_id = ?", (member_id,))
    return dict(cursor.fetchone())

def update_health_profile(db_conn, member_id, data):
    cursor = db_conn.cursor()
    cursor.execute(
        """
        UPDATE member_health_profiles
        SET sleep_quality = ?, stress_level = ?, medications = ?, allergies = ?, 
            pregnancy_lactation_status = ?, kidney_disease = ?, liver_disease = ?, 
            thyroid_condition = ?, diabetes_prediabetes = ?, blood_pressure = ?, 
            vegetarian_vegan = ?, alcohol_intake = ?, sunlight_exposure = ?, 
            current_supplements = ?, recent_lab_values = ?
        WHERE member_id = ?
        """,
        (
            data.get('sleep_quality', ''),
            data.get('stress_level', ''),
            data.get('medications', ''),
            data.get('allergies', ''),
            data.get('pregnancy_lactation_status', ''),
            int(data.get('kidney_disease', 0)),
            int(data.get('liver_disease', 0)),
            int(data.get('thyroid_condition', 0)),
            int(data.get('diabetes_prediabetes', 0)),
            data.get('blood_pressure', ''),
            int(data.get('vegetarian_vegan', 0)),
            data.get('alcohol_intake', ''),
            data.get('sunlight_exposure', ''),
            data.get('current_supplements', ''),
            data.get('recent_lab_values', ''),
            member_id
        )
    )
    db_conn.commit()

def get_score_key(name):
    n = name.lower()
    if 'b12' in n: return 'b12'
    if 'vitamin d' in n: return 'vitamin_d'
    if 'magnesium' in n: return 'magnesium'
    if 'zinc' in n: return 'zinc'
    if 'iron' in n: return 'iron'
    if 'calcium' in n: return 'calcium'
    if 'iodine' in n: return 'iodine'
    if 'omega-3' in n or 'omega 3' in n: return 'omega-3'
    if 'creatine' in n: return 'creatine'
    if 'protein' in n: return 'protein'
    if 'electrolyte' in n: return 'electrolytes'
    if 'caffeine' in n: return 'caffeine'
    if 'fiber' in n or 'psyllium' in n: return 'fiber'
    return None

def generate_recommendation_drafts(db_conn, member_id):
    """
    Deletes existing pending_review drafts and generates fresh recommendations
    for a member based on their biometrics and health profile questionnaire.
    """
    cursor = db_conn.cursor()
    
    # 1. Fetch Member and Health Profile
    cursor.execute("SELECT * FROM members WHERE id = ?", (member_id,))
    member_row = cursor.fetchone()
    if not member_row:
        return
    member = dict(member_row)
    
    health_profile = get_or_create_health_profile(db_conn, member_id)
    
    # 2. Delete existing pending_review recommendations
    cursor.execute(
        "DELETE FROM member_recommendations WHERE member_id = ? AND status = 'pending_review'",
        (member_id,)
    )
    db_conn.commit()
    
    # 3. Fetch active supplements library
    cursor.execute("SELECT * FROM supplement_library WHERE active = 1")
    supplements = [dict(row) for row in cursor.fetchall()]
    
    # 4. Generate Supplement Recommendations
    for supp in supplements:
        score_key = get_score_key(supp['name'])
        if not score_key:
            continue
            
        score = calculate_need_score(member, health_profile, score_key)
        
        # Check if contraindicated by active disease
        is_contraindicated = False
        kidney = int(health_profile.get('kidney_disease') or 0)
        liver = int(health_profile.get('liver_disease') or 0)
        
        if kidney == 1 and supp['name'] in ['Magnesium', 'Creatine monohydrate', 'Electrolytes', 'Calcium', 'Iron']:
            is_contraindicated = True
        if liver == 1 and supp['name'] in ['Caffeine', 'Creatine monohydrate', 'Iron']:
            is_contraindicated = True
            
        # Get warnings from safety gate
        warnings = safety_gate(member, health_profile, supp['name'])
        
        # Map score to level
        level = get_recommendation_level(score, warnings, is_contraindicated)
        
        # We only generate recommendations if need score is substantial (score >= 2) or warnings/contraindications exist
        if score >= 2 or is_contraindicated or level in ['clinician_review_required', 'lab_suggested']:
            # Construct text contents matching requirements
            title = f"{supp['name']} Optimization"
            why_appeared = f"Identified dietary pattern or health flag indicating a potential gap in {supp['name']} intake."
            if score_key == 'b12':
                why_appeared = "User reported a vegetarian/vegan dietary pattern or is on medications that limit absorption."
            elif score_key == 'vitamin_d':
                why_appeared = "User reported low sunlight exposure or spends most time indoors."
            elif score_key == 'magnesium':
                why_appeared = "User reported high stress, poor sleep, or muscle cramping."
            elif score_key == 'creatine':
                why_appeared = "Strength or muscle mass improvement goal combined with active training."
            elif score_key == 'protein':
                why_appeared = "Muscle hypertrophy or fat loss goal requires increased protein density."
                
            confidence_score = 'High' if score >= 4 else ('Medium' if score >= 2 else 'Low')
            
            first_step = f"Increase consumption of food-first sources: {supp['food_first_sources']}."
            supplement_candidate = f"{supp['name']} supplement. Suggested dosage/use: {supp['typical_notes']}."
            
            if is_contraindicated:
                supplement_candidate = "DO NOT SUPPLEMENT. Contraindicated due to reported medical condition."
                first_step = "Focus solely on dietitian-approved food sources."
                level = 'do_not_recommend'
                
            suggested_lab = "Not required for general use."
            if supp['requires_lab'] == 1:
                suggested_lab = f"Suggest check: {supp['name']} serum level."
                
            safety_notes = f"This is not a medical diagnosis. Typical upper limit is {supp['upper_limit_note']}. Contraindications: {supp['contraindications']}."
            if warnings:
                safety_notes = "WARNING: " + " | ".join(warnings) + " " + safety_notes
                
            cursor.execute(
                """
                INSERT INTO member_recommendations (
                    member_id, title, recommendation_type, why_appeared, confidence_score,
                    first_step, supplement_candidate, food_first_alternative, suggested_lab,
                    safety_notes, recommendation_level, status
                )
                VALUES (?, ?, 'supplement', ?, ?, ?, ?, ?, ?, ?, ?, 'pending_review')
                """,
                (
                    member_id, title, why_appeared, confidence_score,
                    first_step, supplement_candidate, supp['food_first_sources'], suggested_lab,
                    safety_notes, level
                )
            )
            
    # 5. Generate Lifestyle Recommendations based on biometrics & topics
    # Sleep
    if health_profile.get('sleep_quality') == 'Poor':
        cursor.execute(
            """
            INSERT INTO member_recommendations (
                member_id, title, recommendation_type, why_appeared, confidence_score,
                first_step, supplement_candidate, food_first_alternative, suggested_lab,
                safety_notes, recommendation_level, status
            )
            VALUES (?, 'Sleep Hygiene Optimization', 'lifestyle', 
                    'Reported poor sleep quality.', 'High', 
                    'Establish a consistent wake-up time and turn off all screens 60 minutes before bed.', 
                    'Review Magnesium or Melatonin support options.', 
                    'Add sleep-supporting whole foods such as bananas, almonds, and warm chamomile tea.', 
                    'None required.', 
                    'Rule out underlying sleep apnea or clinical insomnia if daytime fatigue persists.', 
                    'food_first', 'pending_review')
            """,
            (member_id,)
        )
        
    # Sunlight
    if health_profile.get('sunlight_exposure') == 'Low':
        cursor.execute(
            """
            INSERT INTO member_recommendations (
                member_id, title, recommendation_type, why_appeared, confidence_score,
                first_step, supplement_candidate, food_first_alternative, suggested_lab,
                safety_notes, recommendation_level, status
            )
            VALUES (?, 'Morning sunlight exposure', 'lifestyle', 
                    'Low sunlight exposure reported due to indoor lifestyle.', 'High', 
                    'Get 10-15 minutes of direct morning sunlight before 9 AM.', 
                    'Vitamin D3 (1000-2000 IU daily).', 
                    'Mushrooms exposed to UV, egg yolks, and fortified foods.', 
                    '25-hydroxyvitamin D blood test.', 
                    'Crucial for setting your circadian clock and daily energy.', 
                    'food_first', 'pending_review')
            """,
            (member_id,)
        )
        
    # Stress
    if health_profile.get('stress_level') == 'High':
        cursor.execute(
            """
            INSERT INTO member_recommendations (
                member_id, title, recommendation_type, why_appeared, confidence_score,
                first_step, supplement_candidate, food_first_alternative, suggested_lab,
                safety_notes, recommendation_level, status
            )
            VALUES (?, 'Stress Management Micro-Habits', 'lifestyle', 
                    'User reported high daily stress levels.', 'Medium', 
                    'Incorporate deep breathing techniques or a 5-minute mindfulness session post-workout.', 
                    'Ashwagandha or L-Theanine (optional, consult clinician).', 
                    'Focus on anti-inflammatory diet and regular hydration.', 
                    'None required.', 
                    'Chronic high stress can impact cardiovascular health. Seek medical care if chest tightness is present.', 
                    'education_only', 'pending_review')
            """,
            (member_id,)
        )
        
    # Diabetes / Blood Sugar
    if int(health_profile.get('diabetes_prediabetes') or 0) == 1:
        cursor.execute(
            """
            INSERT INTO member_recommendations (
                member_id, title, recommendation_type, why_appeared, confidence_score,
                first_step, supplement_candidate, food_first_alternative, suggested_lab,
                safety_notes, recommendation_level, status
            )
            VALUES (?, 'Post-meal walking & blood sugar support', 'lifestyle', 
                    'Reported diabetes or pre-diabetes condition.', 'High', 
                    'Walk for 10 minutes immediately after your two main meals.', 
                    'Do not take random fitness supplements. Consult endocrinologist.', 
                    'Emphasize high-fiber vegetables, leafy greens, and lean protein.', 
                    'HbA1c and fasting insulin panel.', 
                    'Fasting beyond normal windows or taking thermogenics is dangerous and contraindicated without doctor review.', 
                    'clinician_review_required', 'pending_review')
            """,
            (member_id,)
        )

    # Thyroid Condition
    if int(health_profile.get('thyroid_condition') or 0) == 1:
        cursor.execute(
            """
            INSERT INTO member_recommendations (
                member_id, title, recommendation_type, why_appeared, confidence_score,
                first_step, supplement_candidate, food_first_alternative, suggested_lab,
                safety_notes, recommendation_level, status
            )
            VALUES (?, 'Thyroid care & medication precautions', 'clinician_review', 
                    'Reported active thyroid condition.', 'High', 
                    'Take thyroid medications on an empty stomach, and wait at least 4 hours before consuming calcium or iron.', 
                    'None. Avoid aggressive hormone or iodine boosters.', 
                    'Selenium and zinc from whole foods like Brazil nuts and seeds.', 
                    'TSH, Free T3, Free T4 panel.', 
                    'Never adjust thyroid medication dosage without direct clinician instruction.', 
                    'clinician_review_required', 'pending_review')
            """,
            (member_id,)
        )
        
    # Kidney Disease
    if kidney == 1:
        cursor.execute(
            """
            INSERT INTO member_recommendations (
                member_id, title, recommendation_type, why_appeared, confidence_score,
                first_step, supplement_candidate, food_first_alternative, suggested_lab,
                safety_notes, recommendation_level, status
            )
            VALUES (?, 'Renal safety alignment', 'clinician_review', 
                    'Active kidney disease reported.', 'High', 
                    'Consult your nephrologist before taking any protein powder, creatine, or electrolytes.', 
                    'DO NOT TAKE protein powder or creatine without nephrologist clearance.', 
                    'Work with a renal dietitian to outline safe protein targets.', 
                    'Serum creatinine, eGFR, and electrolytes.', 
                    'CRITICAL: Kidneys clear mineral wastes. Excess calcium, magnesium, or potassium can build to dangerous levels.', 
                    'clinician_review_required', 'pending_review')
            """,
            (member_id,)
        )
        
    db_conn.commit()
