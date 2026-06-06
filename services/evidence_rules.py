# NIH ODS evidence guidelines and reference thresholds for StrengthLab decision support

EVIDENCE_GRADES = {
    'A': 'Strong scientific evidence with consistent positive clinical outcomes.',
    'B': 'Good scientific evidence with supportive clinical findings.',
    'C': 'Mixed or limited scientific evidence; further study required.',
    'D': 'Insufficient or negative evidence.'
}

NUTRIENT_NIH_GUIDELINES = {
    'b12': {
        'rda': '2.4 mcg/day for adults.',
        'ul': 'No tolerable upper limit established (high safety profile).',
        'notes': 'Found naturally in animal products. Vegan/vegetarian diets require supplementation or fortified foods.',
        'source_url': 'https://ods.od.nih.gov/factsheets/VitaminB12-HealthProfessional/'
    },
    'vitamin_d': {
        'rda': '600-800 IU/day for adults.',
        'ul': '4,000 IU/day (avoid exceeding without clinical supervision).',
        'notes': 'Synthesized through sunlight exposure. Avoid high-dose loading without confirming a deficiency.',
        'source_url': 'https://ods.od.nih.gov/factsheets/VitaminD-HealthProfessional/'
    },
    'magnesium': {
        'rda': '400-420 mg/day for men, 310-320 mg/day for women.',
        'ul': '350 mg/day supplemental upper limit (applies to supplements/meds, not food).',
        'notes': 'Contraindicated in severe kidney disease due to clearance limits.',
        'source_url': 'https://ods.od.nih.gov/factsheets/Magnesium-HealthProfessional/'
    },
    'zinc': {
        'rda': '11 mg/day for men, 8 mg/day for women.',
        'ul': '40 mg/day tolerable upper limit.',
        'notes': 'Excess zinc (>40 mg/day) can interfere with copper absorption and cause anemia.',
        'source_url': 'https://ods.od.nih.gov/factsheets/Zinc-HealthProfessional/'
    },
    'creatine': {
        'rda': '3-5 g/day for maintenance.',
        'ul': 'No formal upper limit established, but higher doses are not useful after loading.',
        'notes': 'Highly researched sports supplement for muscle ATP production. Contraindicated in kidney disease.',
        'source_url': 'https://ods.od.nih.gov/factsheets/ExerciseAndAthleticPerformance-HealthProfessional/'
    },
    'protein': {
        'rda': '0.8 g/kg body weight (general), 1.2-2.2 g/kg (athletes).',
        'ul': 'Keep overall intake within safe athlete limits.',
        'notes': 'Necessary for muscle repair and protein synthesis.',
        'source_url': 'https://ods.od.nih.gov/factsheets/ExerciseAndAthleticPerformance-HealthProfessional/'
    }
}
