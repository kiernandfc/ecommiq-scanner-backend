import argparse
import os
import sys
from dotenv import load_dotenv
from db.dynamodb import DynamoDBDatabase
from db.postgresql import PostgreSQLDatabase
from db.factory import get_database

def main():
    """Create or update database tables"""
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Initialize database tables.')
    parser.add_argument('--db-type', help='Database type (dynamodb, postgresql)', choices=['dynamodb', 'postgresql'])
    args = parser.parse_args()
    
    # Load environment variables
    load_dotenv()
    
    # Override environment variable if specified on command line
    if args.db_type:
        os.environ['DATABASE_TYPE'] = args.db_type
    
    # Get database implementation
    db_type = os.getenv('DATABASE_TYPE', 'dynamodb')
    
    print(f"Creating DB tables for {db_type.upper()} database")
    
    # Initialize database
    db = get_database()
    
    # Get tables created/verified
    if isinstance(db, DynamoDBDatabase):
        # For DynamoDB this will create the tables if they don't exist
        db._ensure_tables_exist()
        print(f"Tables created/verified for DynamoDB")
    elif isinstance(db, PostgreSQLDatabase):
        # For PostgreSQL we need to create all tables using the metadata
        from db.postgresql import Base
        # Create the engine
        engine_url = db.engine.url
        print(f"Creating tables in PostgreSQL at {engine_url}")
        # Create all tables defined in the models
        Base.metadata.create_all(db.engine)
        print(f"Tables created/updated in PostgreSQL")
    else:
        print(f"Unknown database type: {db_type}")
        sys.exit(1)

if __name__ == "__main__":
    main() 