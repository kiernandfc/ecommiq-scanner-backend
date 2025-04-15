import os
from dotenv import load_dotenv

def get_database():
    """
    Factory function to get the appropriate database implementation
    based on configuration.
    """
    # Load environment variables
    load_dotenv()
    
    # Get database type from environment
    db_type = os.getenv('DATABASE_TYPE', 'dynamodb').lower()
    
    if db_type == 'postgresql':
        # Import here to avoid circular imports
        from .postgresql import PostgreSQLDatabase
        return PostgreSQLDatabase()
    else:
        # Default to DynamoDB
        from .dynamodb import DynamoDBDatabase
        return DynamoDBDatabase() 