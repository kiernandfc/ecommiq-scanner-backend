import argparse
import os
import sys
from dotenv import load_dotenv
from db.postgresql import PostgreSQLDatabase, Base
from db.factory import get_database

def main():
    """Create or update database tables for PostgreSQL"""
    # Remove db-type argument parsing
    # parser = argparse.ArgumentParser(description='Initialize database tables.')
    # parser.add_argument('--db-type', help='Database type (dynamodb, postgresql)', choices=['dynamodb', 'postgresql'])
    # args = parser.parse_args()
    
    # Load environment variables
    load_dotenv()
    
    # Remove environment variable logic
    # if args.db_type:
    #     os.environ['DATABASE_TYPE'] = args.db_type
    # db_type = os.getenv('DATABASE_TYPE', 'dynamodb')
    
    print(f"Creating DB tables for POSTGRESQL database")
    
    # Initialize database (will always be PostgreSQL now)
    db = get_database()
    
    # Check if db is PostgreSQL instance (should always be true now)
    if isinstance(db, PostgreSQLDatabase):
        # Create the engine
        engine_url = db.engine.url
        print(f"Creating tables in PostgreSQL at {engine_url}")
        # Create all tables defined in the models
        Base.metadata.create_all(db.engine)
        print(f"Tables created/updated in PostgreSQL")
    else:
        # This case should theoretically not be reachable anymore
        print(f"Error: Expected PostgreSQLDatabase instance, but got {type(db)}")
        sys.exit(1)

if __name__ == "__main__":
    main() 