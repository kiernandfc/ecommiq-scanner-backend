import os
from dotenv import load_dotenv
import boto3
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger()

def test_dynamodb_connection():
    # Load environment variables from .env file
    load_dotenv()
    
    # Get configuration from environment variables
    region_name = os.getenv('AWS_REGION', 'us-east-1')
    endpoint_url = os.getenv('DYNAMODB_ENDPOINT_URL')
    aws_access_key = os.getenv('AWS_ACCESS_KEY_ID')
    aws_secret_key = os.getenv('AWS_SECRET_ACCESS_KEY')
    
    # Debug: Check if credentials were loaded
    logger.info(f"AWS Region: {region_name}")
    logger.info(f"Endpoint URL: {endpoint_url if endpoint_url else 'Not set'}")
    logger.info(f"AWS Access Key: {'Found' if aws_access_key else 'Not found'}")
    logger.info(f"AWS Secret Key: {'Found' if aws_secret_key else 'Not found'}")
    
    # Table names
    competitors_table = os.getenv('DYNAMODB_COMPETITORS_TABLE', 'ecommiq_competitors')
    catalog_table = os.getenv('DYNAMODB_CATALOG_TABLE', 'ecommiq_catalog')
    prices_table = os.getenv('DYNAMODB_PRICES_TABLE', 'ecommiq_prices')
    
    logger.info(f"Testing DynamoDB connection to region: {region_name}")
    if endpoint_url:
        logger.info(f"Using custom endpoint URL: {endpoint_url}")
    
    try:
        # Initialize connection parameters
        session_kwargs = {'region_name': region_name}
        if endpoint_url:
            session_kwargs['endpoint_url'] = endpoint_url
        
        # Add credentials explicitly if they exist
        if aws_access_key and aws_secret_key:
            session_kwargs['aws_access_key_id'] = aws_access_key
            session_kwargs['aws_secret_access_key'] = aws_secret_key
        
        # Initialize boto3 resources
        dynamodb = boto3.resource('dynamodb', **session_kwargs)
        client = boto3.client('dynamodb', **session_kwargs)
        
        # List existing tables
        existing_tables = client.list_tables()['TableNames']
        logger.info(f"Successfully connected to DynamoDB!")
        logger.info(f"Existing tables: {', '.join(existing_tables) if existing_tables else 'None'}")
        
        # Check if our specific tables exist
        app_tables = [competitors_table, catalog_table, prices_table]
        for table_name in app_tables:
            if table_name in existing_tables:
                # Get table item count
                table = dynamodb.Table(table_name)
                try:
                    response = table.scan(Select='COUNT')
                    count = response['Count']
                    logger.info(f"Table '{table_name}' exists with {count} items")
                except Exception as e:
                    logger.warning(f"Could not get count for table '{table_name}': {str(e)}")
            else:
                logger.warning(f"Table '{table_name}' does not exist yet - will be created on first app run")
        
        # Check permissions by attempting a dummy scan (will fail if permissions are insufficient)
        if existing_tables:
            test_table = dynamodb.Table(existing_tables[0])
            test_table.scan(Limit=1)
            logger.info("Permission check: Scan operation successful")
        
        return True
        
    except Exception as e:
        logger.error(f"Connection failed: {str(e)}")
        # Provide more specific error guidance
        if "could not be found" in str(e).lower():
            logger.error("AWS region may be incorrect or not specified")
        elif "connect timeout" in str(e).lower() or "connection" in str(e).lower():
            if endpoint_url:
                logger.error("Cannot connect to the specified endpoint URL. If using DynamoDB Local, make sure it's running")
            else:
                logger.error("Cannot connect to AWS. Check your internet connection and AWS_REGION")
        elif "signature" in str(e).lower() or "credential" in str(e).lower() or "auth" in str(e).lower():
            logger.error("Authentication failed. Check your AWS credentials (AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY)")
        elif "access denied" in str(e).lower() or "not authorized" in str(e).lower():
            logger.error("Permission denied. Your AWS credentials don't have sufficient permissions for DynamoDB")
        
        return False

if __name__ == "__main__":
    test_result = test_dynamodb_connection()
    if test_result:
        print("\n✅ DynamoDB connection successful! Your configuration is correct.")
    else:
        print("\n❌ DynamoDB connection failed. See error messages above for troubleshooting.")
        print("Common solutions:")
        print("1. Check AWS_REGION is set correctly in .env")
        print("2. Verify AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY are correct")
        print("3. Ensure your IAM user has DynamoDB permissions")
        print("4. If using DynamoDB Local, make sure it's running and DYNAMODB_ENDPOINT_URL is set correctly") 