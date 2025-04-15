"""
Test PostgreSQL connection and diagnose any connection issues
"""
import os
import sys
import socket
import logging
import psycopg2
from dotenv import load_dotenv

# Load environment variables at the start of the script
# before any other code runs to ensure they're available
load_dotenv()

from utils.logger import configure_logger

def test_tcp_connection(host, port):
    """Test TCP connection to host:port"""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(5)
    try:
        s.connect((host, int(port)))
        s.close()
        return True, "TCP connection successful"
    except socket.timeout:
        return False, "Connection timed out"
    except socket.gaierror:
        return False, "Could not resolve hostname"
    except ConnectionRefusedError:
        return False, "Connection refused"
    except Exception as e:
        return False, f"TCP connection failed: {str(e)}"
    finally:
        s.close()

def test_psycopg2_connection(host, port, dbname, user, password):
    """Test PostgreSQL connection using psycopg2"""
    try:
        print(f"Attempting connection to: host={host}, port={port}, dbname={dbname}, user={user}")
        conn_string = f"host={host} port={port} dbname={dbname} user={user} password={password}"
        conn = psycopg2.connect(conn_string)
        cursor = conn.cursor()
        cursor.execute("SELECT version();")
        version = cursor.fetchone()
        cursor.close()
        conn.close()
        return True, f"PostgreSQL connection successful: {version[0]}"
    except psycopg2.OperationalError as e:
        return False, f"PostgreSQL connection failed: {str(e)}"
    except Exception as e:
        return False, f"PostgreSQL connection failed: {str(e)}"

def test_environment_variables():
    """Test if environment variables are set correctly"""
    required_vars = {
        'POSTGRESQL_HOST': os.getenv('POSTGRESQL_HOST'),
        'POSTGRESQL_PORT': os.getenv('POSTGRESQL_PORT', '5432'),
        'POSTGRESQL_DB': os.getenv('POSTGRESQL_DB', 'ecommiq-scanner'),
        'POSTGRESQL_USER': os.getenv('POSTGRESQL_USER'),
        'POSTGRESQL_PASSWORD': os.getenv('POSTGRESQL_PASSWORD'),
    }
    
    missing = [var for var, value in required_vars.items() if not value]
    
    if missing:
        return False, f"Missing environment variables: {', '.join(missing)}"
    
    return True, "All required environment variables are set"

def main():
    # Configure logging
    logger = configure_logger("postgres_test", logging.INFO)
    
    # Already loaded environment variables at the top of the script,
    # but print them to verify their values
    logger.info("Environment variables loaded from .env:")
    logger.info(f"POSTGRESQL_HOST={os.getenv('POSTGRESQL_HOST')}")
    logger.info(f"POSTGRESQL_PORT={os.getenv('POSTGRESQL_PORT', '5432')}")
    logger.info(f"POSTGRESQL_DB={os.getenv('POSTGRESQL_DB', 'ecommiq-scanner')}")
    logger.info(f"POSTGRESQL_USER={os.getenv('POSTGRESQL_USER')}")
    logger.info("POSTGRESQL_PASSWORD=********")
    
    logger.info("Testing PostgreSQL connection...")
    
    # Test environment variables
    env_success, env_message = test_environment_variables()
    logger.info(f"Environment variables: {'✓' if env_success else '✗'} {env_message}")
    
    if not env_success:
        logger.error("Please set all required environment variables in your .env file")
        sys.exit(1)
    
    # Get connection parameters directly from environment
    host = os.getenv('POSTGRESQL_HOST')
    port = os.getenv('POSTGRESQL_PORT', '5432')
    dbname = os.getenv('POSTGRESQL_DB', 'ecommiq-scanner')
    user = os.getenv('POSTGRESQL_USER')
    password = os.getenv('POSTGRESQL_PASSWORD')
    
    # Test TCP connection
    logger.info(f"Testing TCP connection to {host}:{port}...")
    tcp_success, tcp_message = test_tcp_connection(host, port)
    logger.info(f"TCP connection: {'✓' if tcp_success else '✗'} {tcp_message}")
    
    if not tcp_success:
        logger.error("TCP connection failed. Please check:")
        logger.error("1. The hostname/IP address is correct")
        logger.error("2. The port is open (typically 5432 for PostgreSQL)")
        logger.error("3. Any firewalls or security groups allow the connection")
        logger.error("4. The database instance is running")
        sys.exit(1)
    
    # Test PostgreSQL connection
    logger.info(f"Testing PostgreSQL connection to {dbname} as {user}...")
    pg_success, pg_message = test_psycopg2_connection(host, port, dbname, user, password)
    logger.info(f"PostgreSQL connection: {'✓' if pg_success else '✗'} {pg_message}")
    
    if not pg_success:
        logger.error("PostgreSQL connection failed. Please check:")
        logger.error("1. The database exists")
        logger.error("2. The username and password are correct")
        logger.error("3. The user has permission to connect to the database")
        
        # Try connecting to 'postgres' database which should always exist
        logger.info("Attempting connection to default 'postgres' database...")
        pg_success_default, pg_message_default = test_psycopg2_connection(host, port, "postgres", user, password)
        if pg_success_default:
            logger.info("✓ Successfully connected to default 'postgres' database")
            logger.info(f"The database '{dbname}' does not exist. Do you need to create it first?")
            logger.info("You can create the database by connecting to postgres database and running:")
            logger.info(f"CREATE DATABASE \"{dbname}\";")
        else:
            logger.info(f"✗ Connection to default 'postgres' database also failed: {pg_message_default}")
        
        sys.exit(1)
    
    logger.info("✓ All tests passed! PostgreSQL connection is working correctly.")
    sys.exit(0)

if __name__ == "__main__":
    main() 