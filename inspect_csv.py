#!/usr/bin/env python
"""
Script to inspect the CSV file and diagnose why rows are being skipped
"""
import os
import sys
import csv

# Find the CSV file
project_root = os.path.abspath(os.path.dirname(__file__))
csv_file_path = os.path.join(project_root, 'competitor_map.csv')

if not os.path.exists(csv_file_path):
    print(f"CSV file not found at: {csv_file_path}")
    sys.exit(1)

try:
    # Try to read the entire file and count rows
    with open(csv_file_path, mode='r', encoding='cp1252') as file:
        reader = csv.reader(file)
        row_count = sum(1 for row in reader)
        print(f"Total rows in CSV file: {row_count}")
    
    # Read and inspect multiple sections of the file
    with open(csv_file_path, mode='r', encoding='cp1252') as file:
        reader = csv.DictReader(file)
        rows = list(reader)
        
        # Inspect beginning (first 5 rows)
        print("\n=== BEGINNING OF FILE (ROWS 1-5) ===")
        for i, row in enumerate(rows[:5]):
            print(f"Row {i+1}:")
            for key, value in row.items():
                print(f"  {key}: '{value}'")
            print()
        
        # Inspect middle (rows 95-105)
        print("\n=== MIDDLE OF FILE (ROWS 95-105) ===")
        for i, row in enumerate(rows[94:105]):
            print(f"Row {i+95}:")
            for key, value in row.items():
                print(f"  {key}: '{value}'")
            print()
        
        # Inspect near the end 
        if len(rows) > 200:
            print("\n=== END OF FILE (LAST 5 ROWS) ===")
            for i, row in enumerate(rows[-5:]):
                print(f"Row {len(rows)-5+i+1}:")
                for key, value in row.items():
                    print(f"  {key}: '{value}'")
                print()
        
        # Count how many rows have all required fields
        required_fields = ['Reference Brand', 'Reference Product', 'Competitor Brand', 'Reference Product Description']
        valid_rows = 0
        invalid_rows = []
        
        for i, row in enumerate(rows):
            if all(row.get(field, '').strip() for field in required_fields):
                valid_rows += 1
            else:
                missing = [field for field in required_fields if not row.get(field, '').strip()]
                invalid_rows.append((i+1, missing))
        
        print(f"\nRows with all required fields: {valid_rows} out of {len(rows)}")
        print(f"Rows missing required fields: {len(invalid_rows)}")
        
        if invalid_rows:
            print("\nSample of rows with missing data:")
            for row_num, missing in invalid_rows[:10]:
                print(f"Row {row_num}: Missing {', '.join(missing)}")
                
except UnicodeDecodeError:
    # Try again with UTF-8 if cp1252 fails
    try:
        with open(csv_file_path, mode='r', encoding='utf-8') as file:
            reader = csv.reader(file)
            row_count = sum(1 for row in reader)
            print(f"Total rows in CSV file (UTF-8): {row_count}")
            
        # Continue with all the same checks...
        print("UTF-8 encoding detected, rerun with encoding parameter changed if needed")
        
    except Exception as e:
        print(f"Error reading CSV: {e}")
        sys.exit(1)
except Exception as e:
    print(f"Error reading CSV: {e}")
    sys.exit(1) 