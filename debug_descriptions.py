#!/usr/bin/env python
"""
Debug script to compare CSV data with database records
"""
import os
import sys
import csv
from dotenv import load_dotenv

# Add project root to sys.path to allow importing db
project_root = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, project_root)

from db.postgresql import PostgreSQLDatabase, CompetitorBrandDB
from sqlalchemy import func

# Load environment variables from .env file
load_dotenv()

# Connect to PostgreSQL
print("Connecting to PostgreSQL database...")
postgres_db = PostgreSQLDatabase()
session = postgres_db.Session()
print("Connected to database")

# Path to the CSV file
csv_file_path = os.path.join(project_root, 'competitor_map.csv')
if not os.path.exists(csv_file_path):
    print(f"CSV file not found at: {csv_file_path}")
    sys.exit(1)

# Read the first few rows of the CSV to see what data we're working with
print("\nFirst 5 rows from CSV file:")
try:
    with open(csv_file_path, mode='r', encoding='cp1252') as file:
        reader = csv.DictReader(file)
        for i, row in enumerate(list(reader)[:5]):
            print(f"Row {i+1}:")
            print(f"  Reference Brand: '{row['Reference Brand']}'")
            print(f"  Reference Product: '{row['Reference Product']}'")
            print(f"  Competitor Brand: '{row['Competitor Brand']}'")
            print(f"  Description: '{row['Reference Product Description'][:50]}...'")
except UnicodeDecodeError:
    try:
        with open(csv_file_path, mode='r', encoding='utf-8') as file:
            reader = csv.DictReader(file)
            for i, row in enumerate(list(reader)[:5]):
                print(f"Row {i+1}:")
                print(f"  Reference Brand: '{row['Reference Brand']}'")
                print(f"  Reference Product: '{row['Reference Product']}'")
                print(f"  Competitor Brand: '{row['Competitor Brand']}'")
                print(f"  Description: '{row['Reference Product Description'][:50]}...'")
    except Exception as e:
        print(f"Error reading CSV: {e}")
        sys.exit(1)

# Now let's try to find matches for the first 5 rows in the database
print("\nSearching for matches in database:")
try:
    with open(csv_file_path, mode='r', encoding='cp1252') as file:
        reader = csv.DictReader(file)
        rows = list(reader)[:5]
except UnicodeDecodeError:
    with open(csv_file_path, mode='r', encoding='utf-8') as file:
        reader = csv.DictReader(file)
        rows = list(reader)[:5]

for i, row in enumerate(rows):
    ref_brand = row['Reference Brand'].strip()
    ref_product = row['Reference Product'].strip()
    comp_brand = row['Competitor Brand'].strip()
    
    print(f"\nSearching for CSV Row {i+1}: '{ref_brand}' | '{ref_product}' | '{comp_brand}'")
    
    # Try exact match first
    exact_matches = session.query(CompetitorBrandDB).filter(
        CompetitorBrandDB.reference_brand == ref_brand,
        CompetitorBrandDB.reference_product == ref_product,
        CompetitorBrandDB.competitor_brand == comp_brand
    ).all()
    
    print(f"  Exact matches found: {len(exact_matches)}")
    
    # Try case-insensitive match
    case_insensitive_matches = session.query(CompetitorBrandDB).filter(
        func.lower(CompetitorBrandDB.reference_brand) == func.lower(ref_brand),
        func.lower(CompetitorBrandDB.reference_product) == func.lower(ref_product),
        func.lower(CompetitorBrandDB.competitor_brand) == func.lower(comp_brand)
    ).all()
    
    print(f"  Case-insensitive matches found: {len(case_insensitive_matches)}")
    
    # Show a sample of what's in the database that's similar
    similar_brand_matches = session.query(CompetitorBrandDB).filter(
        func.lower(CompetitorBrandDB.reference_brand).like(f"%{ref_brand.lower()}%")
    ).limit(3).all()
    
    print(f"  Similar reference brands in database:")
    for match in similar_brand_matches:
        print(f"    '{match.reference_brand}' | '{match.reference_product}' | '{match.competitor_brand}'")
    
    # Try direct UPDATE for a test
    if len(case_insensitive_matches) > 0:
        print("  Attempting manual UPDATE and explicit COMMIT...")
        for match in case_insensitive_matches:
            match.reference_product_description = row['Reference Product Description'].strip()
        session.commit()
        print("  UPDATE committed")

# Check if updates were applied
test_record = None
if len(case_insensitive_matches) > 0:
    test_record = case_insensitive_matches[0]
    refetched_record = session.query(CompetitorBrandDB).filter_by(id=test_record.id).first()
    print(f"\nVerifying update for ID {test_record.id}:")
    print(f"  Description: '{refetched_record.reference_product_description[:50]}...'")

session.close()
print("\nDebug complete") 