import csv
import io

MEDICAL_SENSITIVE_KEYWORDS = [
    'diabetes', 'prediabetes', 'thyroid', 'blood pressure', 'hypertension',
    'fatty liver', 'testosterone', 'hormone', 'fasting', 'fertility', 'pregnancy', 'medication'
]

def clean_value(val):
    return val.strip() if val else ''

def parse_and_import_insights(db_conn, csv_data):
    """
    Parses CSV lines and inserts them into content_insights.
    Returns (imported_count, skipped_count)
    """
    reader = csv.reader(io.StringIO(csv_data))
    
    imported = 0
    skipped = 0
    
    # Read headers if present, else continue
    try:
        first_row = next(reader, None)
    except Exception:
        return 0, 0
        
    if not first_row:
        return 0, 0
    
    # Check if first row is a header
    is_header = any(col.lower() in ['title', 'category', 'views', 'reactions', 'external_video_id'] for col in first_row)
    if is_header:
        rows_to_process = reader
    else:
        # If it wasn't a header, process it
        rows_to_process = [first_row] + list(reader)
        
    for row in rows_to_process:
        if not row or len(row) == 0:
            continue
        # Ensure at least title exists
        if len(row) < 1:
            skipped += 1
            continue
            
        external_id = ''
        title = ''
        category = ''
        views = 0
        reactions = 0
        summary = ''
        topics = ''
        
        if len(row) >= 7:
            external_id = row[0]
            title = row[1]
            category = row[2]
            try:
                views = int(row[3]) if row[3] else 0
            except ValueError:
                views = 0
            try:
                reactions = int(row[4]) if row[4] else 0
            except ValueError:
                reactions = 0
            summary = row[5]
            topics = row[6]
        elif len(row) >= 5:
            title = row[0]
            category = row[1]
            try:
                views = int(row[2]) if row[2] else 0
            except ValueError:
                views = 0
            try:
                reactions = int(row[3]) if row[3] else 0
            except ValueError:
                reactions = 0
            summary = row[4]
            topics = row[5] if len(row) > 5 else ''
        else:
            title = row[0]
            category = row[1] if len(row) > 1 else 'Health, Nutrition & Wellness'
            summary = row[2] if len(row) > 2 else ''
            topics = row[3] if len(row) > 3 else ''
            
        title = clean_value(title)
        category = clean_value(category)
        external_id = clean_value(external_id)
        summary = clean_value(summary)
        topics = clean_value(topics)
        
        if not title:
            skipped += 1
            continue
            
        # Validation: check category matches target
        valid_categories = ['Health, Nutrition & Wellness', 'Productivity & Habits']
        if category not in valid_categories:
            matched_cat = None
            for vc in valid_categories:
                if vc.lower() in category.lower() or category.lower() in vc.lower():
                    matched_cat = vc
                    break
            if matched_cat:
                category = matched_cat
            else:
                skipped += 1
                continue
                
        # Safety classification
        safety_status = 'needs_review'
        evidence_status = 'unverified'
        clinical_risk = 'low'
        
        # Check medical sensitivity
        text_to_check = (title + ' ' + summary + ' ' + topics).lower()
        is_sensitive = False
        for kw in MEDICAL_SENSITIVE_KEYWORDS:
            if kw in text_to_check:
                is_sensitive = True
                break
                
        if is_sensitive:
            safety_status = 'medical_sensitive'
            clinical_risk = 'medium'
        else:
            safety_status = 'needs_review'
            
        cursor = db_conn.cursor()
        cursor.execute(
            """
            INSERT INTO content_insights (external_video_id, title, category, estimated_views, reactions, raw_summary, extracted_topics, safety_status, evidence_status, clinical_risk_level)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (external_id or None, title, category, views, reactions, summary, topics, safety_status, evidence_status, clinical_risk)
        )
        imported += 1
        
    db_conn.commit()
    return imported, skipped
