import os
import logging
import boto3
from sqlalchemy import create_engine, Column, String, Float, Boolean, DateTime, ForeignKey, Text, MetaData, Integer, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime
from typing import List, Optional, Dict, Any
import uuid
import time
from botocore.exceptions import ClientError
import psycopg2

from .models import CompetitorBrand, CatalogProduct, PriceHistory, Site
from utils.helpers import utc_now
from utils.logger import configure_logger

Base = declarative_base()

class SiteDB(Base):
    __tablename__ = 'sites'
    
    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    base_url = Column(String, nullable=False)
    oxylabs_parse_code = Column(String, nullable=False)
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    competitors = relationship("CompetitorBrandDB", back_populates="site")

class CompetitorBrandDB(Base):
    __tablename__ = 'competitors'
    
    id = Column(String, primary_key=True)
    reference_brand = Column(String, nullable=False)
    reference_product = Column(String, nullable=False)
    competitor_brand = Column(String, nullable=False)
    search_query = Column(String, nullable=False)
    reference_product_description = Column(Text, nullable=True)
    min_price = Column(Float, nullable=True)
    max_price = Column(Float, nullable=True)
    site_id = Column(String, ForeignKey('sites.id'), nullable=True)
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    catalog_products = relationship("CatalogProductDB", secondary="competitor_catalog_map", back_populates="competitors")
    site = relationship("SiteDB", back_populates="competitors")

class CompetitorCatalogMapDB(Base):
    __tablename__ = 'competitor_catalog_map'
    
    id = Column(String, primary_key=True)
    competitor_id = Column(String, ForeignKey('competitors.id'), nullable=False)
    catalog_id = Column(String, ForeignKey('catalog.id'), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
class CatalogProductDB(Base):
    __tablename__ = 'catalog'
    
    id = Column(String, primary_key=True)
    google_shopping_id = Column(String, index=True, nullable=True)
    title = Column(String)
    link = Column(String)
    image_link = Column(String)
    price = Column(Float)
    currency = Column(String)
    is_available = Column(Boolean, default=True)
    review_count = Column(Integer, nullable=True)
    position = Column(Integer, nullable=True)
    last_checked = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    description = Column(Text)
    sku = Column(String, nullable=True)
    brand = Column(String, nullable=True)
    source_type = Column(String, default='google_shopping')
    
    competitors = relationship("CompetitorBrandDB", secondary="competitor_catalog_map", back_populates="catalog_products")
    price_history = relationship("PriceHistoryDB", back_populates="catalog_product")

class PriceHistoryDB(Base):
    __tablename__ = 'prices'
    
    id = Column(String, primary_key=True)
    catalog_id = Column(String, ForeignKey('catalog.id'), nullable=False)
    price = Column(Float, nullable=False)
    list_price = Column(Float, nullable=True)
    currency = Column(String, nullable=False)
    merchant = Column(String)
    is_available = Column(Boolean, default=True)
    date_checked = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)
    review_count = Column(Integer, nullable=True)
    position = Column(Integer, nullable=True)
    description = Column(Text, nullable=True)
    
    catalog_product = relationship("CatalogProductDB", back_populates="price_history")

class PostgreSQLDatabase:
    """Database implementation using PostgreSQL"""
    
    def __init__(self):
        # Configure logger - level is inherited from root config set in main.py
        self.logger = configure_logger(f"{__name__}.PostgreSQLDatabase")
        # self.logger.debug("Initializing PostgreSQL connection") # Filtered if root is INFO
        
        # Get configuration from environment variables
        db_host = os.getenv('POSTGRESQL_HOST')
        db_port = os.getenv('POSTGRESQL_PORT', '5432')
        db_name = os.getenv('POSTGRESQL_DB', 'ecommiq-scanner')
        db_user = os.getenv('POSTGRESQL_USER')
        db_password = os.getenv('POSTGRESQL_PASSWORD')
        use_iam_auth = os.getenv('USE_IAM_AUTH', 'false').lower() == 'true'
        
        # Store connection parameters for later use in get_connection method
        self.db_host = db_host
        self.db_port = db_port
        self.db_name = db_name
        self.db_user = db_user
        self.db_password = db_password
        self.use_iam_auth = use_iam_auth
        
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
        self.logger.debug(f"Adding competitor reference: {competitor.reference_brand} vs {competitor.competitor_brand}")
        session = self.Session()
        try:
            # Generate ID if not provided
            competitor_id = competitor.id or self._generate_id("comp_")
            
            competitor_db = CompetitorBrandDB(
                id=competitor_id,
                reference_brand=competitor.reference_brand,
                reference_product=competitor.reference_product,
                competitor_brand=competitor.competitor_brand,
                search_query=competitor.search_query,
                reference_product_description=competitor.reference_product_description,
                min_price=float(competitor.min_price) if competitor.min_price else None,
                max_price=float(competitor.max_price) if competitor.max_price else None,
                site_id=competitor.site_id,
                active=competitor.active,
                created_at=competitor.created_at,
                updated_at=competitor.updated_at
            )
            
            # Add to session and commit
            session.add(competitor_db)
            session.commit()
            
            self.logger.info(f"Added competitor reference with ID: {competitor_id}")
            return competitor_id
        except Exception as e:
            session.rollback()
            self.logger.error(f"Error adding competitor reference: {e}")
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
                    reference_product_description=competitor_db.reference_product_description,
                    min_price=competitor_db.min_price,
                    max_price=competitor_db.max_price,
                    site_id=competitor_db.site_id,
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
                    reference_product_description=competitor_db.reference_product_description,
                    min_price=competitor_db.min_price,
                    max_price=competitor_db.max_price,
                    site_id=competitor_db.site_id,
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
            
        self.logger.debug(f"Updating competitor: {competitor.id}")
        session = self.Session()
        try:
            # Find existing competitor
            existing = session.query(CompetitorBrandDB).filter(CompetitorBrandDB.id == competitor.id).first()
            if not existing:
                self.logger.error(f"Competitor with ID {competitor.id} not found")
                return False
                
            # Update fields
            existing.reference_brand = competitor.reference_brand
            existing.reference_product = competitor.reference_product
            existing.competitor_brand = competitor.competitor_brand
            existing.search_query = competitor.search_query
            existing.reference_product_description = competitor.reference_product_description
            existing.min_price = float(competitor.min_price) if competitor.min_price else None
            existing.max_price = float(competitor.max_price) if competitor.max_price else None
            existing.site_id = competitor.site_id
            existing.active = competitor.active
            existing.updated_at = utc_now()
            
            session.commit()
            self.logger.info(f"Updated competitor with ID: {competitor.id}")
            return True
        except Exception as e:
            session.rollback()
            self.logger.error(f"Error updating competitor: {e}")
            return False
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

    def add_or_update_catalog_product_with_status(self, product: CatalogProduct, competitor_ids: List[str] = None) -> tuple[str, bool]:
        """Add or update a catalog product and return status (id, is_new)"""
        session = self.Session()
        try:
            # Check if the product already exists
            if product.google_shopping_id:
                existing = session.query(CatalogProductDB).filter(
                    CatalogProductDB.google_shopping_id == product.google_shopping_id
                ).first()
            else:
                existing = None
            
            if existing:
                # Update existing product
                existing.google_shopping_id = product.google_shopping_id
                existing.title = product.title if hasattr(product, 'title') else product.name
                existing.link = product.link if hasattr(product, 'link') else product.url
                existing.image_link = product.image_link if hasattr(product, 'image_link') else None
                existing.currency = product.currency if hasattr(product, 'currency') else None
                existing.is_available = product.is_available if hasattr(product, 'is_available') else True
                
                # Log review_count before update
                self.logger.debug(f"Updating product ID {existing.id}. Incoming review_count: {product.review_count}, position: {product.position}. Existing value: {existing.review_count}, {existing.position}")
                
                existing.review_count = product.review_count
                existing.position = product.position
                existing.last_checked = product.last_checked
                existing.updated_at = product.updated_at
                existing.description = product.description if hasattr(product, 'description') else None
                
                session.commit()
                
                # Update the model with the ID
                product.id = existing.id
                
                # If competitor_ids is provided, update competitor mappings
                if competitor_ids:
                    self._update_competitor_mappings(session, existing.id, competitor_ids)
                
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
                    google_shopping_id=product.google_shopping_id,
                    title=product.title if hasattr(product, 'title') else product.name,
                    link=product.link if hasattr(product, 'link') else product.url,
                    image_link=product.image_link if hasattr(product, 'image_link') else None,
                    currency=product.currency if hasattr(product, 'currency') else None,
                    is_available=product.is_available if hasattr(product, 'is_available') else True,
                    
                    # Log review_count before insert
                    review_count=product.review_count,
                    position=product.position,
                    
                    last_checked=product.last_checked,
                    created_at=product.created_at,
                    updated_at=product.updated_at,
                    description=product.description if hasattr(product, 'description') else None
                )
                
                session.add(catalog_db)
                session.commit()
                
                # Update the model with the ID
                product.id = product_id
                
                # If competitor_ids is provided, create mappings
                if competitor_ids:
                    self._update_competitor_mappings(session, product_id, competitor_ids)
                
                return product_id, True
        except Exception as e:
            session.rollback()
            self.logger.error(f"Error adding or updating catalog product: {e}")
            raise
        finally:
            session.close()
    
    def _update_competitor_mappings(self, session, catalog_id: str, competitor_ids: List[str]):
        """Update the mappings between a catalog product and competitors"""
        # Get existing mappings
        existing_mappings = session.query(CompetitorCatalogMapDB).filter(
            CompetitorCatalogMapDB.catalog_id == catalog_id
        ).all()
        
        # Create a set of existing competitor IDs
        existing_competitor_ids = {mapping.competitor_id for mapping in existing_mappings}
        
        # Add new mappings
        for competitor_id in competitor_ids:
            if competitor_id not in existing_competitor_ids:
                mapping_id = self._generate_id("map_")
                mapping = CompetitorCatalogMapDB(
                    id=mapping_id,
                    competitor_id=competitor_id,
                    catalog_id=catalog_id
                )
                session.add(mapping)
        
        session.commit()
    
    def add_competitor_to_catalog(self, competitor_id: str, catalog_id: str) -> str:
        """Add a competitor to a catalog product"""
        session = self.Session()
        try:
            mapping_id = self._generate_id("map_")
            mapping = CompetitorCatalogMapDB(
                id=mapping_id,
                competitor_id=competitor_id,
                catalog_id=catalog_id
            )
            session.add(mapping)
            session.commit()
            return mapping_id
        except Exception as e:
            session.rollback()
            self.logger.error(f"Error adding competitor to catalog: {e}")
            raise
        finally:
            session.close()
    
    def get_catalog_by_competitor(self, competitor_id: str) -> List[CatalogProduct]:
        """Get catalog products by competitor ID"""
        session = self.Session()
        try:
            product_dbs = session.query(CatalogProductDB).join(
                CompetitorCatalogMapDB,
                CatalogProductDB.id == CompetitorCatalogMapDB.catalog_id
            ).filter(
                CompetitorCatalogMapDB.competitor_id == competitor_id
            ).all()
            
            products = []
            for product_db in product_dbs:
                catalog_product = CatalogProduct(
                    id=product_db.id,
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
    
    def get_competitors_by_catalog(self, catalog_id: str) -> List[CompetitorBrand]:
        """Get competitors for a catalog product"""
        session = self.Session()
        try:
            competitor_dbs = session.query(CompetitorBrandDB).join(
                CompetitorCatalogMapDB,
                CompetitorBrandDB.id == CompetitorCatalogMapDB.competitor_id
            ).filter(
                CompetitorCatalogMapDB.catalog_id == catalog_id
            ).all()
            
            competitors = []
            for competitor_db in competitor_dbs:
                competitor = CompetitorBrand(
                    id=competitor_db.id,
                    reference_brand=competitor_db.reference_brand,
                    reference_product=competitor_db.reference_product,
                    competitor_brand=competitor_db.competitor_brand,
                    search_query=competitor_db.search_query,
                    reference_product_description=competitor_db.reference_product_description,
                    min_price=competitor_db.min_price,
                    max_price=competitor_db.max_price,
                    site_id=competitor_db.site_id,
                    active=competitor_db.active,
                    created_at=competitor_db.created_at,
                    updated_at=competitor_db.updated_at
                )
                competitors.append(competitor)
                
            return competitors
        finally:
            session.close()
    
    def add_or_update_catalog_product(self, product: CatalogProduct, competitor_ids: List[str] = None) -> str:
        """Add or update a catalog product"""
        product_id, _ = self.add_or_update_catalog_product_with_status(product, competitor_ids)
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
        """Get catalog products by reference ID (legacy compatibility)"""
        return self.get_catalog_by_competitor(reference_id)
    
    def add_price(self, price: PriceHistory) -> str:
        """Add a price history record"""
        session = self.Session()
        try:
            # Check price against min/max constraints for associated competitors
            try:
                # Get all competitors associated with this catalog product
                competitors_query = session.query(CompetitorBrandDB).join(
                    CompetitorCatalogMapDB,
                    CompetitorBrandDB.id == CompetitorCatalogMapDB.competitor_id
                ).filter(
                    CompetitorCatalogMapDB.catalog_id == price.catalog_id
                )
                
                competitors = competitors_query.all()
                
                if competitors:
                    # Extract min and max prices from competitors
                    min_prices = [c.min_price for c in competitors if c.min_price is not None]
                    max_prices = [c.max_price for c in competitors if c.max_price is not None]
                    
                    # Use the lowest min and highest max to create the widest possible valid range
                    overall_min_price = min(min_prices) if min_prices else None
                    overall_max_price = max(max_prices) if max_prices else None
                    
                    product_price = float(price.price)
                    
                    # Get product name for better error messages
                    product_name = "Unknown"
                    try:
                        product = session.query(CatalogProductDB).filter(CatalogProductDB.id == price.catalog_id).first()
                        if product:
                            product_name = product.name
                    except Exception:
                        # If we can't get the name, just continue with the default
                        pass
                        
                    # Check if the price is outside the valid range
                    price_out_of_range = False
                    if overall_min_price is not None and product_price < overall_min_price:
                        price_out_of_range = True
                        self.logger.warning(
                            f"Price {product_price:.2f} for product '{product_name}' (ID: {price.catalog_id}) "
                            f"is below the minimum price {overall_min_price}. Skipping price recording."
                        )
                    
                    if overall_max_price is not None and product_price > overall_max_price:
                        price_out_of_range = True
                        self.logger.warning(
                            f"Price {product_price:.2f} for product '{product_name}' (ID: {price.catalog_id}) "
                            f"is above the maximum price {overall_max_price}. Skipping price recording."
                        )
                    
                    if price_out_of_range:
                        # Skip adding this price to the database
                        return "OUT_OF_BOUNDS"
            except Exception as e:
                # Log the error but continue with adding the price
                self.logger.error(f"Error during price validation: {e}")
            
            # Generate a unique ID for the price history entry if needed
            price_id = price.id or self._generate_id("price_")

            # Convert the PriceHistory model object to PriceHistoryDB for database interaction
            price_db = PriceHistoryDB(
                id=price_id,
                catalog_id=price.catalog_id,
                price=float(price.price),
                currency=price.currency,
                merchant=price.merchant,
                is_available=price.in_stock,
                review_count=price.review_count,
                position=price.position,
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
                    review_count=price_db.review_count,
                    position=price_db.position,
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
                review_count=price_db.review_count,
                position=price_db.position,
                timestamp=price_db.date_checked
            )
            
            return price_history
        finally:
            session.close()

    def refresh_materialized_views(self):
        """
        Refresh all materialized views in the correct dependency order:
        1. daily_price_summary
        2. interpolated_price_summary_14day
        3. competitor_weighted_price_14day
        4. daily_price_summary_all_dates
        5. interpolated_price_summary_all_dates
        6. competitor_weighted_price_all_dates
        """
        session = self.Session()
        try:
            self.logger.info("Starting to refresh materialized views...")
            
            # Step 1: Refresh daily_price_summary
            self.logger.info("Refreshing daily_price_summary...")
            session.execute(text("REFRESH MATERIALIZED VIEW daily_price_summary"))
            
            # Step 2: Refresh interpolated_price_summary_14day (depends on daily_price_summary)
            self.logger.info("Refreshing interpolated_price_summary_14day...")
            session.execute(text("REFRESH MATERIALIZED VIEW interpolated_price_summary_14day"))
            
            # Step 3: Refresh competitor_weighted_price_14day (depends on interpolated view)
            self.logger.info("Refreshing competitor_weighted_price_14day...")
            session.execute(text("REFRESH MATERIALIZED VIEW competitor_weighted_price_14day"))

            # Step 4: Refresh daily_price_summary_all_dates
            self.logger.info("Refreshing daily_price_summary_all_dates...")
            session.execute(text("REFRESH MATERIALIZED VIEW daily_price_summary_all_dates"))

            # Step 5: Refresh interpolated_price_summary_all_dates (depends on daily_price_summary_all_dates)
            self.logger.info("Refreshing interpolated_price_summary_all_dates...")
            session.execute(text("REFRESH MATERIALIZED VIEW interpolated_price_summary_all_dates"))

            # Step 6: Refresh competitor_weighted_price_all_dates (depends on interpolated_price_summary_all_dates)
            self.logger.info("Refreshing competitor_weighted_price_all_dates...")
            session.execute(text("REFRESH MATERIALIZED VIEW competitor_weighted_price_all_dates"))
            
            # Commit all changes
            session.commit()
            self.logger.info("All materialized views refreshed successfully.")
            return True
        except Exception as e:
            session.rollback()
            self.logger.error(f"Error refreshing materialized views: {e}", exc_info=True)
            return False
        finally:
            session.close()

    def get_total_catalog_count(self) -> int:
        """Get total number of products in the catalog"""
        session = self.Session()
        try:
            return session.query(CatalogProductDB).count()
        finally:
            session.close()
            
    def get_unique_search_query_count(self) -> int:
        """Get total number of unique search queries"""
        session = self.Session()
        try:
            return session.query(CompetitorBrandDB.search_query).distinct().count()
        finally:
            session.close()

    def get_connection(self):
        """
        Return a raw psycopg2 connection for direct SQL operations.
        This is primarily used for the relevancy calculation process.
        
        Returns:
            A psycopg2 connection object.
        """
        try:
            # If IAM authentication is enabled, get a fresh token
            if self.use_iam_auth:
                password = self._get_iam_auth_token(self.db_host, self.db_port, self.db_user)
            else:
                password = self.db_password
                
            # Create and return a new psycopg2 connection
            conn = psycopg2.connect(
                host=self.db_host,
                port=self.db_port,
                dbname=self.db_name,
                user=self.db_user,
                password=password
            )
            return conn
        except Exception as e:
            self.logger.error(f"Error creating psycopg2 connection: {e}")
            raise

    # Site management methods
    def add_site(self, site: Site) -> str:
        """Add a new site to the database
        
        Args:
            site: The site to add
            
        Returns:
            The site ID
        """
        self.logger.debug(f"Adding site: {site.name}")
        session = self.Session()
        try:
            # Generate ID if not provided
            site_id = site.id or self._generate_id("site_")
            
            # Create DB model
            site_db = SiteDB(
                id=site_id,
                name=site.name,
                base_url=site.base_url,
                oxylabs_parse_code=site.oxylabs_parse_code,
                active=site.active,
                created_at=site.created_at,
                updated_at=site.updated_at
            )
            
            session.add(site_db)
            session.commit()
            
            # Update the model with the ID
            site.id = site_id
            
            self.logger.info(f"Added site with ID: {site_id}")
            return site_id
        except Exception as e:
            session.rollback()
            self.logger.error(f"Error adding site: {e}")
            raise
        finally:
            session.close()
            
    def update_site(self, site: Site) -> bool:
        """Update an existing site
        
        Args:
            site: The site to update (must have ID)
            
        Returns:
            True if successful, False otherwise
        """
        if not site.id:
            raise ValueError("Site must have an ID to be updated")
            
        self.logger.debug(f"Updating site: {site.id}")
        session = self.Session()
        try:
            existing = session.query(SiteDB).filter(SiteDB.id == site.id).first()
            if not existing:
                self.logger.warning(f"Site with ID {site.id} not found for update")
                return False
            
            # Update fields
            existing.name = site.name
            existing.base_url = site.base_url
            existing.oxylabs_parse_code = site.oxylabs_parse_code
            existing.active = site.active
            existing.updated_at = utc_now()
            
            session.commit()
            self.logger.info(f"Updated site with ID: {site.id}")
            return True
        except Exception as e:
            session.rollback()
            self.logger.error(f"Error updating site: {e}")
            return False
        finally:
            session.close()
            
    def get_site(self, site_id: str) -> Optional[Site]:
        """Get a site by ID
        
        Args:
            site_id: The ID of the site to retrieve
            
        Returns:
            The site if found, None otherwise
        """
        self.logger.debug(f"Getting site with ID: {site_id}")
        session = self.Session()
        try:
            site_db = session.query(SiteDB).filter(SiteDB.id == site_id).first()
            if not site_db:
                self.logger.debug(f"Site with ID {site_id} not found")
                return None
                
            # Convert to Pydantic model
            site = Site(
                id=site_db.id,
                name=site_db.name,
                base_url=site_db.base_url,
                oxylabs_parse_code=site_db.oxylabs_parse_code,
                active=site_db.active,
                created_at=site_db.created_at,
                updated_at=site_db.updated_at
            )
            return site
        except Exception as e:
            self.logger.error(f"Error getting site: {e}")
            return None
        finally:
            session.close()
            
    def get_all_sites(self) -> List[Site]:
        """Get all sites from the database
        
        Returns:
            List of all sites
        """
        self.logger.debug("Getting all sites")
        session = self.Session()
        try:
            sites_db = session.query(SiteDB).all()
            
            # Convert to Pydantic models
            sites = []
            for site_db in sites_db:
                site = Site(
                    id=site_db.id,
                    name=site_db.name,
                    base_url=site_db.base_url,
                    oxylabs_parse_code=site_db.oxylabs_parse_code,
                    active=site_db.active,
                    created_at=site_db.created_at,
                    updated_at=site_db.updated_at
                )
                sites.append(site)
            return sites
        except Exception as e:
            self.logger.error(f"Error getting all sites: {e}")
            return []
        finally:
            session.close()
            
    def delete_site(self, site_id: str) -> bool:
        """Delete a site by ID
        
        Args:
            site_id: The ID of the site to delete
            
        Returns:
            True if successful, False otherwise
        """
        self.logger.debug(f"Deleting site with ID: {site_id}")
        session = self.Session()
        try:
            # First update any competitors that reference this site
            session.query(CompetitorBrandDB).filter(CompetitorBrandDB.site_id == site_id).update({CompetitorBrandDB.site_id: None})
            
            # Then delete the site
            result = session.query(SiteDB).filter(SiteDB.id == site_id).delete()
            session.commit()
            
            if result > 0:
                self.logger.info(f"Deleted site with ID: {site_id}")
                return True
            else:
                self.logger.warning(f"Site with ID {site_id} not found for deletion")
                return False
        except Exception as e:
            session.rollback()
            self.logger.error(f"Error deleting site: {e}")
            return False
        finally:
            session.close()