#!/usr/bin/env python3
"""
Manually load sample crisis data into database
"""
from models import Session, Crisis
from data_sources import ACLEDConnector

print("Loading sample crisis data...")

session = Session()

# Get sample crises
sample_crises = ACLEDConnector._get_sample_crises()

print(f"Found {len(sample_crises)} sample crises")

# Insert into database
for crisis_data in sample_crises:
    # Check if already exists
    existing = session.query(Crisis).filter(Crisis.id == crisis_data['id']).first()

    if not existing:
        crisis = Crisis(**crisis_data)
        session.add(crisis)
        print(f"  [+] Added: {crisis_data['title']}")
    else:
        print(f"  [*] Skipped (exists): {crisis_data['title']}")

session.commit()
session.close()

print(f"\n[OK] Done! Check API at http://localhost:5000/api/crises")
