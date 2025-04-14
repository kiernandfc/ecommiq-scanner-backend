import json
from tinydb import TinyDB
import os

def main():
    # Open the database directly
    db_path = "data/db.json"
    if not os.path.exists(db_path):
        print(f"Database file not found at {db_path}")
        return
        
    db = TinyDB(db_path)
    catalog_table = db.table('catalog')
    
    # Get all catalog records
    all_products = catalog_table.all()
    print(f"\n=== Catalog Table Analysis ===")
    print(f"Total catalog products: {len(all_products)}")
    
    if not all_products:
        print("No catalog products found in the database!")
        return
    
    # Analyze the first few records
    print(f"\nSample catalog records:")
    for i, product in enumerate(all_products[:5]):
        print(f"Record {i+1}: {json.dumps(product, indent=2)}")
        
    # Extract IDs - check if they're stored in the document itself
    has_id_field = any('id' in p for p in all_products)
    print(f"\nProducts have 'id' field: {has_id_field}")
    
    # Check for doc_id
    print(f"\nSample doc_ids:")
    for i, product in enumerate(all_products[:5]):
        print(f"Record {i+1} doc_id: {product.doc_id}")
        
    # Test fetching a product by its doc_id
    if all_products:
        test_id = all_products[0].doc_id
        product = catalog_table.get(doc_id=test_id)
        print(f"\nProduct with doc_id {test_id}: {json.dumps(product, indent=2)}")
        
    # Save raw data for inspection
    os.makedirs('exports', exist_ok=True)
    with open('exports/raw_catalog.json', 'w') as f:
        catalog_data = []
        for product in all_products:
            product_dict = dict(product)
            product_dict['doc_id'] = product.doc_id
            catalog_data.append(product_dict)
        json.dump(catalog_data, f, indent=2)
    print(f"\nRaw catalog data saved to exports/raw_catalog.json")

if __name__ == "__main__":
    main() 