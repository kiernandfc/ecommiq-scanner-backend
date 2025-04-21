#!/usr/bin/env python
"""
Script to check if reference_product_description values exist in the database
"""
import os
import sys
from dotenv import load_dotenv

# Add project root to sys.path to allow importing db
project_root = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, project_root)

from db.postgresql import PostgreSQLDatabase, CompetitorBrandDB

# Load environment variables from .env file
load_dotenv()

# Connect to PostgreSQL
print("Connecting to PostgreSQL database...")
postgres_db = PostgreSQLDatabase()
session = postgres_db.Session()
print("Connected to database")

# Check for non-empty reference_product_description values
query = session.query(CompetitorBrandDB).filter(
    CompetitorBrandDB.reference_product_description.isnot(None),
    CompetitorBrandDB.reference_product_description != ""
).limit(10)

results = query.all()

print(f"\nFound {len(results)} competitors with non-empty reference_product_description")
if results:
    print("\nSample entries:")
    for comp in results:
        print(f"ID: {comp.id}")
        print(f"Reference Brand: {comp.reference_brand}")
        print(f"Reference Product: {comp.reference_product}")
        print(f"Competitor Brand: {comp.competitor_brand}")
        print(f"Description: {comp.reference_product_description[:100]}...")
        print("-" * 50)

# Check row counts
total_count = session.query(CompetitorBrandDB).count()
with_desc_count = session.query(CompetitorBrandDB).filter(
    CompetitorBrandDB.reference_product_description.isnot(None),
    CompetitorBrandDB.reference_product_description != ""
).count()

print(f"\nTotal competitors in database: {total_count}")
print(f"Competitors with description: {with_desc_count}")
print(f"Percentage with description: {(with_desc_count/total_count)*100 if total_count > 0 else 0:.2f}%")

session.close() 