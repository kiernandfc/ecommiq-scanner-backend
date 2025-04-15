import os
import logging
import boto3
from sqlalchemy import create_engine, Column, String, Float, Boolean, DateTime, ForeignKey, Text, MetaData
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime
from typing import List, Optional, Dict, Any
import uuid
import time
from botocore.exceptions import ClientError

from .models import CompetitorBrand, CatalogProduct, PriceHistory
from utils.helpers import utc_now
from utils.logger import configure_logger

Base = declarative_base()

class CompetitorBrandDB(Base):
    __tablename__ = 'competitors'
    
    id = Column(String, primary_key=True)
    reference_brand = Column(String, nullable=False)
    reference_product = Column(String, nullable=False)
    competitor_brand = Column(String, nullable=False)
    search_query = Column(String, nullable=False)
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    catalog_products = relationship("CatalogProductDB", back_populates="competitor_brand")

class CatalogProductDB(Base):
    __tablename__ = 'catalog'
    
    id = Column(String, primary_key=True)
    competitor_brand_id = Column(String, ForeignKey('competitors.id'), nullable=False)
    google_shopping_id = Column(String, index=True)
    title = Column(String)
    link = Column(String)
    image_link = Column(String)
    price = Column(Float)
    currency = Column(String)
    is_available = Column(Boolean, default=True)
    last_checked = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    description = Column(Text)
    
    competitor_brand = relationship("CompetitorBrandDB", back_populates="catalog_products")
    price_history = relationship("PriceHistoryDB", back_populates="catalog_product")

class PriceHistoryDB(Base):
    __tablename__ = 'prices'
    
    id = Column(String, primary_key=True)
    catalog_id = Column(String, ForeignKey('catalog.id'), nullable=False)
    price = Column(Float, nullable=False)
    currency = Column(String, nullable=False)
    merchant = Column(String)
    is_available = Column(Boolean, default=True)
    date_checked = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    catalog_product = relationship("CatalogProductDB", back_populates="price_history")

class PostgreSQLDatabase:
    """Database implementation using PostgreSQL"""
    
    def __init__(self):
        # Configure logger
        self.logger = configure_logger(f"{__name__}.PostgreSQLDatabase", logging.DEBUG)
        self.logger.debug("Initializing PostgreSQL connection")
        
        # Get configuration from environment variables
        db_host = os.getenv('POSTGRESQL_HOST')
        db_port = os.getenv('POSTGRESQL_PORT', '5432')
        db_name = os.getenv('POSTGRESQL_DB', 'ecommiq-scanner')
        db_user = os.getenv('POSTGRESQL_USER')
        db_password = os.getenv('POSTGRESQL_PASSWORD')
        use_iam_auth = os.getenv('USE_IAM_AUTH', 'false').lower() == 'true'
        
        # Validate required connection parameters
        connection_errors = []
        if not db_host:
            connection_errors.append("POSTGRESQL_HOST environment variable is not set")
        if not db_user:
            connection_errors.append("POSTGRESQL_USER environment variable is not set")
        if not db_password and not use_iam_auth:
            connection_errors.append("POSTGRESQL_PASSWORD environment variable is not set (required when IAM auth is disabled)")
        
        if connection_errors:
            for error in connection_errors:
                self.logger.error(f"Configuration error: {error}")
            self.logger.error("Please check your .env file and make sure all required PostgreSQL connection parameters are set")
            raise ValueError(f"PostgreSQL connection configuration error: {', '.join(connection_errors)}")
        
        self.logger.info(f"Connecting to PostgreSQL at {db_host}:{db_port}/{db_name} as {db_user}")
        
        # Connection parameters
        connect_args = {}
        
        # Use IAM token authentication if specified
        if use_iam_auth:
            self.logger.info("Using IAM authentication for PostgreSQL")
            token = self._get_iam_auth_token(db_host, db_port, db_user)
            db_password = token
            connect_args['connect_timeout'] = 10
        
        # Create SQLAlchemy engine with connection pooling optimized for Serverless
        self.db_url = f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"
        try:
            self.engine = create_engine(
                self.db_url,
                pool_pre_ping=True,  # Verify connections before using from pool
                pool_recycle=3600,   # Recycle connections after 1 hour
                pool_size=5,         # Smaller pool size for serverless
                max_overflow=10,     # Allow up to 10 connections beyond pool_size
                connect_args=connect_args
            )
            
            # Test connection
            with self.engine.connect() as conn:
                self.logger.info("Successfully connected to PostgreSQL database")
                
            # Create session factory
            self.Session = sessionmaker(bind=self.engine)
            
            # Create tables if they don't exist
            self._ensure_tables_exist()
        except Exception as e:
            self.logger.error(f"Failed to connect to PostgreSQL: {e}")
            self.logger.error(f"Connection URL (without password): postgresql://{db_user}:***@{db_host}:{db_port}/{db_name}")
            raise
    
    def _get_iam_auth_token(self, host, port, user):
        """Get IAM authentication token for Aurora Serverless"""
        try:
            rds_client = boto3.client('rds')
            token = rds_client.generate_db_auth_token(
                DBHostname=host,
                Port=port,
                DBUsername=user,
                Region=os.getenv('AWS_REGION', 'us-east-1')
            )
            return token
        except ClientError as e:
            self.logger.error(f"Error getting IAM auth token: {e}")
            raise
    
    def _execute_with_retry(self, func, *args, max_retries=5, **kwargs):
        """Execute database operation with retry for Aurora Serverless wake-up"""
        retry = 0
        resume_timeout = int(os.getenv('AURORA_RESUME_TIMEOUT', '30'))
        backoff_factor = 1.5
        
        while retry < max_retries:
            try:
                return func(*args, **kwargs)
            except Exception as e:
                # Check if this could be an Aurora Serverless cold start issue
                if "timeout expired" in str(e).lower() or "connection" in str(e).lower():
                    wait_time = (backoff_factor ** retry) * 2
                    self.logger.warning(f"Database connection issue, possibly cold start. Retrying in {wait_time}s. ({retry+1}/{max_retries})")
                    time.sleep(wait_time)
                    retry += 1
                    
                    # If using IAM auth, refresh the token
                    if os.getenv('USE_IAM_AUTH', 'false').lower() == 'true':
                        db_host = os.getenv('POSTGRESQL_HOST')
                        db_port = os.getenv('POSTGRESQL_PORT', '5432')
                        db_user = os.getenv('POSTGRESQL_USER')
                        token = self._get_iam_auth_token(db_host, db_port, db_user)
                        
                        # Recreate engine with new token
                        db_name = os.getenv('POSTGRESQL_DB', 'ecommiq-scanner')
                        self.db_url = f"postgresql://{db_user}:{token}@{db_host}:{db_port}/{db_name}"
                        self.engine = create_engine(
                            self.db_url,
                            pool_pre_ping=True,
                            pool_recycle=3600,
                            pool_size=5,
                            max_overflow=10,
                            connect_args={'connect_timeout': 10}
                        )
                        self.Session = sessionmaker(bind=self.engine)
                else:
                    # Non-connection related exception, re-raise
                    raise
        
        # If we get here, all retries failed
        raise Exception(f"Failed to execute database operation after {max_retries} retries")
    
    def _ensure_tables_exist(self):
        """Create tables if they don't exist"""
        Base.metadata.create_all(self.engine)
        self.logger.debug("All PostgreSQL tables verified")
    
    def _generate_id(self, prefix=""):
        """Generate a unique ID"""
        return f"{prefix}{uuid.uuid4().hex}"
    
    def clear_tables(self, tables=None):
        """Clear specified tables or all tables if none specified"""
        session = self.Session()
        try:
            if tables is None:
                tables = ['competitors', 'catalog', 'prices']
                
            for table_name in tables:
                if table_name == 'prices':
                    session.query(PriceHistoryDB).delete()
                if table_name == 'catalog':
                    session.query(CatalogProductDB).delete()
                if table_name == 'competitors':
                    session.query(CompetitorBrandDB).delete()
            
            session.commit()
            self.logger.info(f"Tables {', '.join(tables)} cleared")
        except Exception as e:
            session.rollback()
            self.logger.error(f"Error clearing tables: {e}")
        finally:
            session.close()
    
    def add_reference(self, competitor: CompetitorBrand) -> str:
        """Add a new competitor reference to the database"""
        session = self.Session()
        try:
            # Convert model to database object
            competitor_id = competitor.id or self._generate_id("comp_")
            
            # Check if a record with this ID already exists
            existing = session.query(CompetitorBrandDB).filter(CompetitorBrandDB.id == competitor_id).first()
            if existing:
                # Generate a new unique ID
                competitor_id = self._generate_id("comp_")
            
            competitor_db = CompetitorBrandDB(
                id=competitor_id,
                reference_brand=competitor.reference_brand,
                reference_product=competitor.reference_product,
                competitor_brand=competitor.competitor_brand,
                search_query=competitor.search_query,
                active=competitor.active,
                created_at=competitor.created_at,
                updated_at=competitor.updated_at
            )
            
            session.add(competitor_db)
            session.commit()
            
            # Update the model with the ID
            competitor.id = competitor_id
            return competitor_id
        except Exception as e:
            session.rollback()
            self.logger.error(f"Error adding competitor: {e}")
            raise
        finally:
            session.close()
    
    def get_all_competitors(self) -> List[CompetitorBrand]:
        """Get all competitors from the database"""
        return self._execute_with_retry(self._get_all_competitors)
    
    def _get_all_competitors(self) -> List[CompetitorBrand]:
        """Internal implementation to get all competitors"""
        session = self.Session()
        try:
            competitors = []
            competitor_dbs = session.query(CompetitorBrandDB).all()
            
            for competitor_db in competitor_dbs:
                competitor = CompetitorBrand(
                    id=competitor_db.id,
                    reference_brand=competitor_db.reference_brand,
                    reference_product=competitor_db.reference_product,
                    competitor_brand=competitor_db.competitor_brand,
                    search_query=competitor_db.search_query,
                    active=competitor_db.active,
                    created_at=competitor_db.created_at,
                    updated_at=competitor_db.updated_at
                )
                competitors.append(competitor)
                
            return competitors
        finally:
            session.close()
    
    def get_active_competitors(self) -> List[CompetitorBrand]:
        """Get all active competitors from the database"""
        session = self.Session()
        try:
            competitors = []
            competitor_dbs = session.query(CompetitorBrandDB).filter(CompetitorBrandDB.active == True).all()
            
            for competitor_db in competitor_dbs:
                competitor = CompetitorBrand(
                    id=competitor_db.id,
                    reference_brand=competitor_db.reference_brand,
                    reference_product=competitor_db.reference_product,
                    competitor_brand=competitor_db.competitor_brand,
                    search_query=competitor_db.search_query,
                    active=competitor_db.active,
                    created_at=competitor_db.created_at,
                    updated_at=competitor_db.updated_at
                )
                competitors.append(competitor)
                
            return competitors
        finally:
            session.close()
    
    def update_competitor(self, competitor: CompetitorBrand) -> str:
        """Update an existing competitor reference"""
        if not competitor.id:
            raise ValueError("Competitor must have an ID to be updated")
            
        session = self.Session()
        try:
            competitor_db = session.query(CompetitorBrandDB).filter(CompetitorBrandDB.id == competitor.id).first()
            
            if not competitor_db:
                raise ValueError(f"Competitor with ID {competitor.id} not found")
            
            competitor_db.reference_brand = competitor.reference_brand
            competitor_db.reference_product = competitor.reference_product
            competitor_db.competitor_brand = competitor.competitor_brand
            competitor_db.search_query = competitor.search_query
            competitor_db.active = competitor.active
            competitor_db.updated_at = utc_now()
            
            session.commit()
            return competitor.id
        except Exception as e:
            session.rollback()
            self.logger.error(f"Error updating competitor: {e}")
            raise
        finally:
            session.close()

    def configure_serverless_capacity(self, min_capacity=None, max_capacity=None):
        """
        Configure Aurora Serverless capacity units
        
        Args:
            min_capacity: Minimum ACUs (Aurora Capacity Units)
            max_capacity: Maximum ACUs (Aurora Capacity Units)
        """
        if not (min_capacity or max_capacity):
            min_capacity = int(os.getenv('AURORA_MIN_CAPACITY', '1'))
            max_capacity = int(os.getenv('AURORA_MAX_CAPACITY', '4'))
        
        try:
            # Extract cluster identifier from host
            db_host = os.getenv('POSTGRESQL_HOST', '')
            # Aurora endpoints typically have format: cluster-name.xxxx.region.rds.amazonaws.com
            if not db_host or '.' not in db_host:
                self.logger.error(f"Invalid or missing database host: {db_host}")
                return
                
            cluster_parts = db_host.split('.')
            if len(cluster_parts) < 2:
                self.logger.error(f"Could not extract cluster identifier from host: {db_host}")
                return
                
            cluster_identifier = cluster_parts[0]
            
            # Configure capacity
            rds_client = boto3.client('rds')
            response = rds_client.modify_current_db_cluster_capacity(
                DBClusterIdentifier=cluster_identifier,
                Capacity=min_capacity,
                SecondsBeforeTimeout=300,
                TimeoutAction='RollbackCapacityChange'
            )
            
            # Update scaling configuration
            response = rds_client.modify_db_cluster(
                DBClusterIdentifier=cluster_identifier,
                ServerlessV2ScalingConfiguration={
                    'MinCapacity': min_capacity,
                    'MaxCapacity': max_capacity
                }
            )
            
            self.logger.info(f"Aurora Serverless capacity configured: Min={min_capacity}, Max={max_capacity}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to configure serverless capacity: {e}")
            return False

    def add_or_update_catalog_product_with_status(self, product: CatalogProduct) -> tuple[str, bool]:
        """Add or update a catalog product and return status"""
        session = self.Session()
        try:
            # Check if product already exists by google_shopping_id and competitor_brand_id
            existing = session.query(CatalogProductDB).filter(
                CatalogProductDB.google_shopping_id == product.google_shopping_id,
                CatalogProductDB.competitor_brand_id == product.competitor_brand_id
            ).first()
            
            if existing:
                # Update existing product
                existing.title = product.title if hasattr(product, 'title') else product.name
                existing.link = product.link if hasattr(product, 'link') else product.url
                existing.image_link = product.image_link if hasattr(product, 'image_link') else None
                existing.price = float(product.price) if hasattr(product, 'price') else None
                existing.currency = product.currency if hasattr(product, 'currency') else None
                existing.is_available = product.is_available if hasattr(product, 'is_available') else True
                existing.last_checked = product.last_checked
                existing.updated_at = utc_now()
                existing.description = product.description if hasattr(product, 'description') else None
                
                session.commit()
                return existing.id, False
            else:
                # Create new product
                product_id = product.id or self._generate_id("prod_")
                
                # Check if a record with this ID already exists (to handle migration duplicates)
                id_exists = session.query(CatalogProductDB).filter(
                    CatalogProductDB.id == product_id
                ).first() is not None
                
                if id_exists:
                    # Generate a new unique ID
                    product_id = self._generate_id("prod_")
                
                catalog_db = CatalogProductDB(
                    id=product_id,
                    competitor_brand_id=product.competitor_brand_id,
                    google_shopping_id=product.google_shopping_id,
                    title=product.title if hasattr(product, 'title') else product.name,
                    link=product.link if hasattr(product, 'link') else product.url,
                    image_link=product.image_link if hasattr(product, 'image_link') else None,
                    price=float(product.price) if hasattr(product, 'price') else None,
                    currency=product.currency if hasattr(product, 'currency') else None,
                    is_available=product.is_available if hasattr(product, 'is_available') else True,
                    last_checked=product.last_checked,
                    created_at=product.created_at,
                    updated_at=product.updated_at,
                    description=product.description if hasattr(product, 'description') else None
                )
                
                session.add(catalog_db)
                session.commit()
                
                # Update the model with the ID
                product.id = product_id
                return product_id, True
        except Exception as e:
            session.rollback()
            self.logger.error(f"Error adding or updating catalog product: {e}")
            raise
        finally:
            session.close()
    
    def add_or_update_catalog_product(self, product: CatalogProduct) -> str:
        """Add or update a catalog product"""
        product_id, _ = self.add_or_update_catalog_product_with_status(product)
        return product_id
    
    def get_catalog_product(self, product_id: str) -> Optional[CatalogProduct]:
        """Get a catalog product by ID"""
        session = self.Session()
        try:
            product_db = session.query(CatalogProductDB).filter(CatalogProductDB.id == product_id).first()
            
            if not product_db:
                return None
                
            # Convert database object to model
            catalog_product = CatalogProduct(
                id=product_db.id,
                competitor_brand_id=product_db.competitor_brand_id,
                google_shopping_id=product_db.google_shopping_id,
                name=product_db.title,
                url=product_db.link,
                last_checked=product_db.last_checked,
                created_at=product_db.created_at,
                updated_at=product_db.updated_at
            )
            
            return catalog_product
        finally:
            session.close()
    
    def get_catalog_by_reference(self, reference_id: str) -> List[CatalogProduct]:
        """Get catalog products by reference ID"""
        session = self.Session()
        try:
            product_dbs = session.query(CatalogProductDB).filter(
                CatalogProductDB.competitor_brand_id == reference_id
            ).all()
            
            products = []
            for product_db in product_dbs:
                catalog_product = CatalogProduct(
                    id=product_db.id,
                    competitor_brand_id=product_db.competitor_brand_id,
                    google_shopping_id=product_db.google_shopping_id,
                    name=product_db.title,
                    url=product_db.link,
                    last_checked=product_db.last_checked,
                    created_at=product_db.created_at,
                    updated_at=product_db.updated_at
                )
                products.append(catalog_product)
                
            return products
        finally:
            session.close()
    
    def add_price(self, price: PriceHistory) -> str:
        """Add a price history record"""
        session = self.Session()
        try:
            # Generate a unique ID if not provided
            price_id = price.id or self._generate_id("price_")
            
            # Check if a record with this ID already exists (to handle migration duplicates)
            id_exists = session.query(PriceHistoryDB).filter(
                PriceHistoryDB.id == price_id
            ).first() is not None
            
            if id_exists:
                # Generate a new unique ID
                price_id = self._generate_id("price_")
            
            price_db = PriceHistoryDB(
                id=price_id,
                catalog_id=price.catalog_id,
                price=float(price.price),
                currency=price.currency,
                merchant=price.merchant,
                is_available=price.in_stock,
                date_checked=price.timestamp,
                created_at=utc_now()
            )
            
            session.add(price_db)
            session.commit()
            
            # Update the model with the ID
            price.id = price_id
            return price_id
        except Exception as e:
            session.rollback()
            self.logger.error(f"Error adding price history: {e}")
            raise
        finally:
            session.close()
    
    def get_price_history(self, catalog_id: str) -> List[PriceHistory]:
        """Get price history for a catalog product"""
        session = self.Session()
        try:
            price_dbs = session.query(PriceHistoryDB).filter(
                PriceHistoryDB.catalog_id == catalog_id
            ).order_by(PriceHistoryDB.date_checked.desc()).all()
            
            prices = []
            for price_db in price_dbs:
                price_history = PriceHistory(
                    id=price_db.id,
                    catalog_id=price_db.catalog_id,
                    merchant=price_db.merchant,
                    price=price_db.price,
                    currency=price_db.currency,
                    in_stock=price_db.is_available,
                    timestamp=price_db.date_checked
                )
                prices.append(price_history)
                
            return prices
        finally:
            session.close()
    
    def get_products_to_update(self, hours_threshold: int = 24) -> List[CatalogProduct]:
        """Get products that haven't been checked in the specified hours"""
        from datetime import timedelta
        
        session = self.Session()
        try:
            cutoff = utc_now() - timedelta(hours=hours_threshold)
            
            product_dbs = session.query(CatalogProductDB).filter(
                CatalogProductDB.last_checked < cutoff
            ).all()
            
            products = []
            for product_db in product_dbs:
                catalog_product = CatalogProduct(
                    id=product_db.id,
                    competitor_brand_id=product_db.competitor_brand_id,
                    google_shopping_id=product_db.google_shopping_id,
                    name=product_db.title,
                    url=product_db.link,
                    last_checked=product_db.last_checked,
                    created_at=product_db.created_at,
                    updated_at=product_db.updated_at
                )
                products.append(catalog_product)
                
            return products
        finally:
            session.close()
    
    def get_latest_price(self, catalog_id: str) -> Optional[PriceHistory]:
        """Get the most recent price for a catalog product"""
        session = self.Session()
        try:
            price_db = session.query(PriceHistoryDB).filter(
                PriceHistoryDB.catalog_id == catalog_id
            ).order_by(PriceHistoryDB.date_checked.desc()).first()
            
            if not price_db:
                return None
                
            price_history = PriceHistory(
                id=price_db.id,
                catalog_id=price_db.catalog_id,
                merchant=price_db.merchant,
                price=price_db.price,
                currency=price_db.currency,
                in_stock=price_db.is_available,
                timestamp=price_db.date_checked
            )
            
            return price_history
        finally:
            session.close()

    # Implement other methods similar to DynamoDB class but using SQLAlchemy ORM
    # For example: add_or_update_catalog_product, get_price_history, etc. 