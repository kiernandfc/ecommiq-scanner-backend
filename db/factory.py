import os
from dotenv import load_dotenv

# Import PostgreSQLDatabase directly
from .postgresql import PostgreSQLDatabase

def get_database():
    """
    Factory function to get the PostgreSQL database implementation.
    """
    # Load environment variables (still useful for connection string)
    load_dotenv()
    
    # Directly return PostgreSQLDatabase instance
    return PostgreSQLDatabase() 