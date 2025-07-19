import boto3
import os
import json
import datetime
import pg8000.native
import decimal
from decimal import Decimal
from typing import Dict, List, Tuple, Optional
from botocore.exceptions import ClientError

def lambda_handler(event, context):
    """
    Lambda function that calculates 10x10 kitchen costs for each competitor
    when an ECS task completes. It queries the latest non-Google Shopping
    price observations and calculates total kitchen costs using kit quantities.
    """
    # Parse the ECS task event
    print("Received event:", json.dumps(event))
    
    try:
        # Get detail type to check if this is a task state change event
        detail_type = event.get('detail-type')
        if detail_type != 'ECS Task State Change':
            print(f"Ignoring non-ECS task state change event: {detail_type}")
            return
            
        task_arn = event['detail']['taskArn']
        last_status = event['detail']['lastStatus']
        
        # Only process when task reaches STOPPED state
        if last_status != 'STOPPED':
            print(f"Task not yet completed, current status: {last_status}")
            return
            
        # Extract task ID from ARN for logging
        task_id = task_arn.split('/')[-1]
        print(f"Processing kitchen cost calculation for completed task: {task_id}")
        
        # Get database connection parameters from environment variables
        db_params = {
            'host': os.environ['POSTGRESQL_HOST'],
            'database': os.environ.get('POSTGRESQL_DB', 'ecommiq-scanner'),
            'user': os.environ['POSTGRESQL_USER'],
            'password': os.environ['POSTGRESQL_PASSWORD'],
            'port': int(os.environ.get('POSTGRESQL_PORT', 5432))
        }
        
        # Load kit quantity mapping
        kit_quantities = load_kit_quantity_mapping()
        print(f"Loaded kit quantities for {len(kit_quantities)} products")
        
        # Calculate kitchen costs
        kitchen_costs = calculate_kitchen_costs(db_params, kit_quantities)
        
        # Prepare and send notification
        send_kitchen_cost_notification(kitchen_costs, task_id)
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'Kitchen cost calculation completed successfully',
                'competitors_processed': len(kitchen_costs),
                'task_id': task_id
            })
        }
        
    except Exception as e:
        print(f"Error processing kitchen cost calculation: {str(e)}")
        # Send error notification
        try:
            sns_client = boto3.client('sns')
            sns_client.publish(
                TopicArn=os.environ['SNS_TOPIC_ARN'],
                Subject=f"Error in Kitchen Cost Calculator",
                Message=f"An error occurred while calculating kitchen costs: {str(e)}\n\nEvent: {json.dumps(event)}"
            )
        except Exception as sns_error:
            print(f"Failed to send error notification: {str(sns_error)}")
        raise

def load_kit_quantity_mapping() -> Dict[str, Dict[str, int]]:
    """
    Load the hardcoded kit quantity mapping, organized by competitor.
    Returns a dictionary mapping competitor names to their product quantities.
    """
    # Hardcoded kit quantity mapping based on rta_kit_quantity_map.csv
    kit_quantities = {
        'The RTA Store': {
            'SW-TKC': 4,
            'SW-COV': 4,
            'SW-B24': 1,
            'SW-SB36': 1,
            'SW-B18': 1,
            'SW-3DB24': 1,
            'SW-BT9': 1,
            'SW-B30S': 1,
            'SW-W2436': 1,
            'SW-W3036': 2,
            'SW-W361824': 1,
            'SW-LSB36': 1,
            'SW-DWR3': 1
        },
        'Lily Ann Cabinets': {
            'WSH-TK8': 4,
            'WSH-ACM8': 4,
            'WSH-B24': 1,
            'WSH-SB36': 1,
            'WSH-B18': 1,
            'WSH-DB24-3': 1,
            'WSH-B9FHD': 1,
            'WSH-B30': 1,
            'WSH-W2436': 1,
            'WSH-W3036': 2,
            'WSH-W361824': 1,
            'WSH-LS36': 1,
            'LST36 (WSH-LS36)': 1,
            'WSH-DWR3': 1
        },
        'Cabinet Set': {
            'M6-OW-TKC': 4,
            'M6-OW-COV': 4,
            'M6-OW-B24': 1,
            'M6-OW-SB36': 1,
            'M6-OW-B18': 1,
            'M6-OW-DB24': 1,
            'M6-OW-BT9': 1,
            'M6-OW-B30S': 1,
            'M6-OW-W2436': 1,
            'M6-OW-W3036': 2,
            'M6-OW-W361824': 1,
            'M6-OW-LSB36': 1,
            'M6-OW-DWR3': 1
        },
        'RTA Cabinet Store': {
            'Toe Kick 8': 4,
            'Large Crown 8': 4,
            'B24': 1,
            'SB36': 1,
            'B18': 1,
            'DB24': 1,
            'B09-FH': 1,
            'B30': 1,
            'W2436': 1,
            'W3036': 2,
            'W361824': 1,
            'LS36': 1,
            'DWR3': 1
        }
    }
    
    total_products = sum(len(products) for products in kit_quantities.values())
    print(f"Loaded {total_products} kit quantity mappings for {len(kit_quantities)} competitors")
    return kit_quantities

def calculate_kitchen_costs(db_params: Dict, kit_quantities: Dict[str, Dict[str, int]]) -> Dict[str, Dict]:
    """
    Calculate kitchen costs for each competitor based on latest price observations with price comparisons.
    """
    print("Fetching price observations from database...")
    
    # Import and connect using pg8000 instead of psycopg2
    import pg8000.native
    
    # Connect to database and fetch price data
    conn = pg8000.native.Connection(**db_params)
    
    try:
        # Execute the RTA data query to get price observations
        # pg8000.native uses .run() method instead of cursor
        rta_query = """
        SELECT 
            p.id as price_id,
            p.catalog_id,
            p.price,
            p.currency,
            p.is_available,
            p.date_checked,
            p.created_at as price_created_at,
            p.merchant,
            p.review_count as price_review_count,
            p.position as price_position,
            c.id as catalog_id,
            c.title,
            c.link,
            c.description as catalog_description,
            com.id as competitor_id,
            com.reference_brand,
            com.reference_product,
            com.competitor_brand,
            com.search_query,
            com.active,
            com.site_id
        FROM prices as p
            LEFT JOIN competitor_catalog_map as ccm ON p.catalog_id = ccm.catalog_id
            LEFT JOIN competitors as com ON ccm.competitor_id = com.id
            LEFT JOIN catalog as c ON p.catalog_id = c.id
        WHERE com.site_id IS NOT NULL
        ORDER BY p.date_checked DESC
        """
        
        # Use pg8000's native .run() method to execute query
        rows = conn.run(rta_query)
        
        # Get column names from the query (pg8000 doesn't provide description like psycopg2)
        columns = [
            'price_id', 'catalog_id', 'price', 'currency', 'is_available', 'date_checked',
            'price_created_at', 'merchant', 'price_review_count', 'price_position',
            'catalog_id', 'title', 'link', 'catalog_description', 'competitor_id',
            'reference_brand', 'reference_product', 'competitor_brand', 'search_query',
            'active', 'site_id'
        ]
        
        price_data = []
        for row in rows:
            row_dict = dict(zip(columns, row))
            price_data.append(row_dict)
        
        print(f"Retrieved {len(price_data)} price observations")
    
    finally:
        conn.close()
    
    # Get latest prices per product
    latest_prices = get_latest_prices_per_product(price_data)
    
    # Get previous prices per product (at least 1 day before latest)
    previous_prices = get_previous_prices_per_product(price_data, latest_prices)
    
    # Calculate kitchen costs for each competitor with price comparisons
    kitchen_costs = calculate_competitor_kitchen_costs(latest_prices, previous_prices, kit_quantities)
    
    return kitchen_costs

def get_latest_prices_per_product(price_data: List[Dict]) -> Dict[Tuple[str, str], Dict]:
    """
    Get the most recent price observation for each product-competitor combination.
    Returns a dictionary keyed by (competitor_brand, product_title) tuples.
    """
    latest_prices = {}
    
    for row in price_data:
        competitor_brand = row.get('competitor_brand')
        product_title = row.get('title')  # This is the catalog product title
        date_checked = row.get('date_checked')
        
        if not all([competitor_brand, product_title, date_checked]):
            continue
            
        key = (competitor_brand, product_title)
        
        # Keep only the most recent price for each product-competitor combination
        if key not in latest_prices or date_checked > latest_prices[key]['date_checked']:
            latest_prices[key] = row
    
    print(f"Found latest prices for {len(latest_prices)} product-competitor combinations")
    return latest_prices

def get_previous_prices_per_product(price_data: List[Dict], latest_prices: Dict[Tuple[str, str], Dict]) -> Dict[Tuple[str, str], Dict]:
    """
    Get the most recent price observation from the previous calendar day (not just 24 hours prior)
    for each product-competitor combination. Uses Eastern Time for calendar day determination.
    Returns a dictionary keyed by (competitor_brand, product_title) tuples.
    """
    import pytz
    
    # Define Eastern Time zone (handles EST/EDT automatically)
    et_tz = pytz.timezone('US/Eastern')
    
    previous_prices = {}
    
    for row in price_data:
        competitor = row['competitor_brand']
        product_title = row['title']
        key = (competitor, product_title)
        
        # Skip if we don't have a latest price for this product
        if key not in latest_prices:
            continue
            
        latest_date = latest_prices[key]['date_checked']
        current_date = row['date_checked']
        
        # Convert to Eastern Time for calendar day comparison
        if latest_date.tzinfo is None:
            latest_date_utc = pytz.utc.localize(latest_date)
        else:
            latest_date_utc = latest_date
            
        if current_date.tzinfo is None:
            current_date_utc = pytz.utc.localize(current_date)
        else:
            current_date_utc = current_date
            
        latest_date_et = latest_date_utc.astimezone(et_tz)
        current_date_et = current_date_utc.astimezone(et_tz)
        
        # Only consider prices from previous calendar days in ET (not same day)
        if current_date_et.date() < latest_date_et.date():
            # Keep the most recent price that meets our criteria
            # Use timezone-aware datetime for comparison
            if key not in previous_prices or current_date_utc > previous_prices[key]['date_checked_utc']:
                row_copy = row.copy()
                row_copy['date_checked_utc'] = current_date_utc  # Store timezone-aware version
                previous_prices[key] = row_copy
    
    print(f"Found previous prices for {len(previous_prices)} product-competitor combinations")
    return previous_prices

def calculate_competitor_kitchen_costs(latest_prices: Dict[Tuple[str, str], Dict], previous_prices: Dict[Tuple[str, str], Dict], kit_quantities: Dict[str, Dict[str, int]]) -> Dict[str, Dict]:
    """
    Calculate total kitchen cost for each competitor based on kit quantities, including price comparisons.
    """
    competitor_costs = {}
    
    # Group by competitor
    competitors = set(key[0] for key in latest_prices.keys())
    
    for competitor in competitors:
        print(f"Calculating kitchen cost for {competitor}...")
        
        current_total_cost = Decimal('0')
        previous_total_cost = Decimal('0')
        products_found = []
        products_missing = []
        most_recent_date = None
        most_recent_previous_date = None
        
        # Check each product in the kit quantity mapping for this specific competitor
        for product_title, quantity in kit_quantities.get(competitor, {}).items():
            key = (competitor, product_title)
            
            if key in latest_prices:
                current_price_data = latest_prices[key]
                previous_price_data = previous_prices.get(key)
                
                # Skip products with null/None current prices
                if current_price_data['price'] is None:
                    products_missing.append({
                        'product_title': product_title,
                        'quantity': quantity,
                        'reason': 'Current price is null/None in database'
                    })
                    continue
                
                try:
                    current_price = Decimal(str(current_price_data['price']))
                    current_product_cost = current_price * quantity
                    current_total_cost += current_product_cost
                    
                    # Calculate previous price and cost if available
                    previous_price = None
                    previous_product_cost = None
                    price_changed = False
                    
                    if previous_price_data and previous_price_data['price'] is not None:
                        try:
                            previous_price = Decimal(str(previous_price_data['price']))
                            previous_product_cost = previous_price * quantity
                            previous_total_cost += previous_product_cost
                            price_changed = current_price != previous_price
                        except (ValueError, TypeError, decimal.InvalidOperation):
                            previous_price = None
                            previous_product_cost = None
                    
                    # Track the most recent observation date for this competitor
                    current_date = current_price_data['date_checked']
                    if most_recent_date is None or current_date > most_recent_date:
                        most_recent_date = current_date
                    
                    # Track the most recent previous observation date for this competitor
                    if previous_price_data and previous_price_data['date_checked']:
                        previous_date = previous_price_data['date_checked']
                        if most_recent_previous_date is None or previous_date > most_recent_previous_date:
                            most_recent_previous_date = previous_date
                    
                except (ValueError, TypeError, decimal.InvalidOperation) as e:
                    # Handle invalid current price values
                    products_missing.append({
                        'product_title': product_title,
                        'quantity': quantity,
                        'reason': f'Invalid current price value: {current_price_data["price"]} ({str(e)})'
                    })
                    continue
                
                products_found.append({
                    'product_title': product_title,
                    'quantity': quantity,
                    'current_unit_price': float(current_price),
                    'current_total_price': float(current_product_cost),
                    'current_date_checked': current_price_data['date_checked'].isoformat() if current_price_data['date_checked'] else None,
                    'previous_unit_price': float(previous_price) if previous_price is not None else None,
                    'previous_total_price': float(previous_product_cost) if previous_product_cost is not None else None,
                    'previous_date_checked': previous_price_data['date_checked'].isoformat() if previous_price_data and previous_price_data['date_checked'] else None,
                    'price_changed': price_changed,
                    'merchant': current_price_data.get('merchant'),
                    'is_available': current_price_data.get('is_available', True)
                })
            else:
                products_missing.append({
                    'product_title': product_title,
                    'quantity': quantity,
                    'reason': 'No current price data available'
                })
        
        # Calculate coverage based on products expected for this specific competitor
        expected_products = len(kit_quantities.get(competitor, {}))
        coverage_percentage = (len(products_found) / expected_products * 100) if expected_products > 0 else 0
        
        # Determine if total kitchen cost changed
        kitchen_cost_changed = previous_total_cost > 0 and current_total_cost != previous_total_cost
        
        competitor_costs[competitor] = {
            'current_total_kitchen_cost': float(current_total_cost),
            'previous_total_kitchen_cost': float(previous_total_cost) if previous_total_cost > 0 else None,
            'kitchen_cost_changed': kitchen_cost_changed,
            'most_recent_observation_date': most_recent_date.isoformat() if most_recent_date else None,
            'most_recent_previous_observation_date': most_recent_previous_date.isoformat() if most_recent_previous_date else None,
            'products_found': len(products_found),
            'products_missing': len(products_missing),
            'expected_products': expected_products,
            'coverage_percentage': coverage_percentage,
            'product_details': products_found,
            'missing_products': products_missing
        }
        
        print(f"  Current total cost: ${current_total_cost:.2f}")
        if previous_total_cost > 0:
            print(f"  Previous total cost: ${previous_total_cost:.2f}")
            change = current_total_cost - previous_total_cost
            print(f"  Change: ${change:.2f} ({'↑' if change > 0 else '↓' if change < 0 else '→'})")
        print(f"  Products found: {len(products_found)}/{expected_products} ({coverage_percentage:.1f}%)")
    
    return competitor_costs

def send_kitchen_cost_notification(kitchen_costs: Dict[str, Dict], task_id: str):
    """
    Send SNS notification with kitchen cost calculation results including price comparisons.
    """
    print("Preparing kitchen cost notification with price comparisons...")
    
    # Sort competitors by current total cost
    sorted_competitors = sorted(
        kitchen_costs.items(), 
        key=lambda x: x[1]['current_total_kitchen_cost']
    )
    
    # Prepare email content with enhanced table format
    subject = f"10x10 Kitchen Cost Analysis with Price Comparison - Task {task_id}"
    
    message_parts = [
        "🏠 10x10 Kitchen Cost Analysis with Price Comparison",
        "=" * 60,
        f"Analysis completed for {len(kitchen_costs)} competitors",
        f"Task ID: {task_id}",
        f"Timestamp: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "📊 COMPETITOR SUMMARY TABLE",
        "-" * 60
    ]
    
    # Create competitor summary table
    for i, (competitor, data) in enumerate(sorted_competitors, 1):
        current_cost = data['current_total_kitchen_cost']
        previous_cost = data.get('previous_total_kitchen_cost')
        cost_changed = data.get('kitchen_cost_changed', False)
        most_recent_date = data.get('most_recent_observation_date', 'N/A')
        most_recent_previous_date = data.get('most_recent_previous_observation_date', 'N/A')
        
        # Color coding: 🔴 for changes, 🟢 for no changes
        status_icon = "🔴" if cost_changed else "🟢"
        
        message_parts.append(f"{i}. {status_icon} {competitor}")
        message_parts.append(f"   Current Kitchen Cost: ${current_cost:,.2f}")
        
        if previous_cost is not None:
            change = current_cost - previous_cost
            change_pct = (change / previous_cost * 100) if previous_cost > 0 else 0
            change_arrow = "📈" if change > 0 else "📉" if change < 0 else "➡️"
            message_parts.append(f"   Previous Kitchen Cost: ${previous_cost:,.2f}")
            message_parts.append(f"   Change: {change_arrow} ${change:+,.2f} ({change_pct:+.1f}%)")
        else:
            message_parts.append(f"   Previous Kitchen Cost: No data available")
            
        message_parts.extend([
            f"   Most Recent Observation: {most_recent_date[:10] if most_recent_date != 'N/A' else 'N/A'}",
            f"   Most Recent Previous Observation: {most_recent_previous_date[:10] if most_recent_previous_date != 'N/A' else 'N/A'}",
            f"   Product Coverage: {data['products_found']}/{data['expected_products']} ({data['coverage_percentage']:.1f}%)",
            ""
        ])
    
    # Add detailed product breakdown for each competitor
    message_parts.extend([
        "",
        "📋 DETAILED PRODUCT BREAKDOWN",
        "=" * 60
    ])
    
    for competitor, data in sorted_competitors:
        current_cost = data['current_total_kitchen_cost']
        previous_cost = data.get('previous_total_kitchen_cost')
        cost_changed = data.get('kitchen_cost_changed', False)
        
        # Color coding for competitor header
        status_icon = "🔴" if cost_changed else "🟢"
        
        most_recent_date = data.get('most_recent_observation_date', 'N/A')
        most_recent_previous_date = data.get('most_recent_previous_observation_date', 'N/A')
        
        # Format previous cost properly
        previous_cost_str = f"${previous_cost:,.2f}" if previous_cost is not None else "$0.00"
        
        message_parts.extend([
            f"\n{status_icon} {competitor.upper()}",
            f"Current Total: ${current_cost:,.2f} | Previous Total: {previous_cost_str} | Coverage: {data['coverage_percentage']:.1f}%",
            f"Latest Observation: {most_recent_date[:10] if most_recent_date != 'N/A' else 'N/A'} | Latest Previous: {most_recent_previous_date[:10] if most_recent_previous_date != 'N/A' else 'N/A'}",
            "-" * 50
        ])
        
        # Create lookup dictionaries for found and missing products
        found_products = {p['product_title']: p for p in data['product_details']}
        missing_products = {p['product_title']: p for p in data['missing_products']}
        
        # Get all expected products for this competitor
        all_expected_products = set()
        for product in data['product_details']:
            all_expected_products.add(product['product_title'])
        for product in data['missing_products']:
            all_expected_products.add(product['product_title'])
        
        # Sort products alphabetically for consistent display
        for product_title in sorted(all_expected_products):
            if product_title in found_products:
                product = found_products[product_title]
                
                # Determine if this product's price changed
                price_changed = product.get('price_changed', False)
                product_icon = "🔴" if price_changed else "🟢"
                
                current_price = product['current_unit_price']
                previous_price = product.get('previous_unit_price')
                current_date = product.get('current_date_checked', 'N/A')[:10] if product.get('current_date_checked') else 'N/A'
                previous_date = product.get('previous_date_checked', 'N/A')[:10] if product.get('previous_date_checked') else 'N/A'
                
                message_parts.append(
                    f"  {product_icon} {product['product_title']} (qty: {product['quantity']})"
                )
                # Format previous price properly
                previous_price_str = f"${previous_price:.2f}" if previous_price is not None else "$0.00"
                previous_date_str = previous_date if previous_price else 'N/A'
                
                message_parts.append(
                    f"      Current: ${current_price:.2f} ({current_date}) | "
                    f"Previous: {previous_price_str} ({previous_date_str})"
                )
                
                if price_changed and previous_price:
                    change = current_price - previous_price
                    change_pct = (change / previous_price * 100) if previous_price > 0 else 0
                    change_arrow = "📈" if change > 0 else "📉" if change < 0 else "➡️"
                    message_parts.append(
                        f"      Change: {change_arrow} ${change:+.2f} ({change_pct:+.1f}%)"
                    )
                
                if product.get('merchant'):
                    message_parts.append(f"      Merchant: {product['merchant']}")
                    
            elif product_title in missing_products:
                product = missing_products[product_title]
                reason = product.get('reason', 'No price data available')
                message_parts.append(
                    f"  ✗ ❌ MISSING: {product['product_title']} (qty: {product['quantity']}) - {reason}"
                )
        
        message_parts.append("-" * 50)
    
    message = "\n".join(message_parts)
    
    # Send notification
    sns_client = boto3.client('sns')
    sns_client.publish(
        TopicArn=os.environ['SNS_TOPIC_ARN'],
        Subject=subject,
        Message=message
    )
    
    print("Kitchen cost notification sent successfully")
