import requests
from bs4 import BeautifulSoup
import csv
import xml.etree.ElementTree as ET
import os
import re
import logging
import time
import random
import pandas as pd
import json
from urllib.parse import urljoin

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

BASE_URL = "https://joyandco.com"

# Headers to mimic a browser
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.5',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1',
}

def get_page_content(url, max_retries=3, delay=2):
    """Get page content with retries and random delay to avoid rate limiting"""
    retries = 0
    while retries < max_retries:
        try:
            # Random delay between requests
            if retries > 0:
                sleep_time = delay + random.random() * 2
                logging.info(f"Retry {retries}/{max_retries}, waiting {sleep_time:.2f} seconds...")
                time.sleep(sleep_time)
            
            response = requests.get(url, headers=HEADERS, timeout=30)
            response.raise_for_status()  # Raise exception for 4XX/5XX responses
            
            return response.text
        except requests.exceptions.RequestException as e:
            logging.error(f"Error fetching {url}: {e}")
            retries += 1
    
    logging.error(f"Failed to fetch {url} after {max_retries} retries")
    return None

def save_debug_html(html_content, filename):
    """Save HTML content for debugging"""
    os.makedirs('debug', exist_ok=True)
    with open(f'debug/{filename}.html', 'w', encoding='utf-8') as f:
        f.write(html_content)
    logging.info(f"Saved debug HTML to debug/{filename}.html")

def save_debug_info_to_feeds(content, filename):
    """Save debug information to the feeds/debug directory so it gets committed"""
    os.makedirs('feeds/debug', exist_ok=True)
    with open(f'feeds/debug/{filename}', 'w', encoding='utf-8') as f:
        f.write(content)
    logging.info(f"Saved debug info to feeds/debug/{filename}")

def read_product_urls_from_excel(excel_file_path):
    """Read product URLs from an Excel file"""
    try:
        # Read the Excel file
        df = pd.read_excel(excel_file_path)
        
        # Check if 'product_url' column exists
        if 'product_url' in df.columns:
            # Get the list of product URLs
            product_urls = df['product_url'].tolist()
            logging.info(f"Read {len(product_urls)} product URLs from Excel file")
            return product_urls
        else:
            logging.error(f"Column 'product_url' not found in Excel file. Available columns: {df.columns.tolist()}")
            return []
    except Exception as e:
        logging.error(f"Error reading Excel file: {e}")
        return []

def validate_and_fix_image_url(image_url):
    """
    Basic image URL validation and HTTPS conversion (without PIL)
    Returns: (is_valid, corrected_url, error_message)
    """
    if not image_url:
        return False, None, "No image URL provided"
    
    original_url = image_url
    
    # Ensure HTTPS
    if image_url.startswith('http://'):
        image_url = image_url.replace('http://', 'https://', 1)
        logging.info(f"Converted HTTP to HTTPS: {image_url}")
    elif image_url.startswith('//'):
        image_url = 'https:' + image_url
        logging.info(f"Added HTTPS protocol: {image_url}")
    elif not image_url.startswith('https://'):
        if image_url.startswith('/'):
            image_url = BASE_URL + image_url
        else:
            return False, image_url, "Image URL must use HTTPS protocol"
    
    # Basic accessibility check (HEAD request only)
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'image/webp,image/apng,image/*,*/*;q=0.8'
        }
        
        response = requests.head(image_url, headers=headers, timeout=10, allow_redirects=True)
        
        if response.status_code != 200:
            return False, image_url, f"HTTP {response.status_code} error accessing image"
        
        # Check content type
        content_type = response.headers.get('content-type', '').lower()
        if not content_type.startswith('image/'):
            return False, image_url, f"URL doesn't point to an image (content-type: {content_type})"
        
        logging.info(f"Image validated: {image_url}")
        return True, image_url, None
            
    except requests.exceptions.RequestException as e:
        # If HEAD request fails, still return the HTTPS-corrected URL
        # Meta might still accept it even if our validation fails
        logging.warning(f"Could not validate image accessibility: {str(e)}")
        return True, image_url, None
    except Exception as e:
        return False, image_url, f"Image validation error: {str(e)}"

def get_fallback_image_for_meta():
    """Get a reliable fallback image that meets Meta requirements"""
    fallback_options = [
        f"{BASE_URL}/images/default-product-500x500.jpg",
        f"{BASE_URL}/assets/default-product.jpg",
        "https://via.placeholder.com/500x500/CCCCCC/FFFFFF?text=Product+Image"
    ]
    
    for fallback in fallback_options:
        is_valid, validated_url, error = validate_and_fix_image_url(fallback)
        if is_valid:
            return validated_url
    
    # Final fallback
    return "https://via.placeholder.com/500x500/CCCCCC/FFFFFF?text=No+Image"

def extract_product_data(url, html_content):
    """Extract product data from a product page with basic image validation"""
    if not html_content:
        return None
    
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Debugging save
    page_name = url.split('/')[-1].replace('.', '_')
    save_debug_html(str(soup.prettify()), f"product_{page_name}")
    
    # Save a snippet of the HTML to the feeds directory
    html_snippet = html_content[:1000] if len(html_content) > 1000 else html_content
    save_debug_info_to_feeds(html_snippet, f"product_{page_name}_snippet.html")
    
    # Extract the title from the page title
    page_title = soup.title.text.strip() if soup.title else ""
    title = page_title
    
    # Try to find the price
    price = None
    # Look for common price selectors
    price_selectors = [
        '.price', '.product-price', '.productPrice', '#price', 
        '[itemprop="price"]', '.amount', '.current-price', 
        '.total-price', '.product-single__price', '.money',
        '.product-info__price'
    ]
    
    for selector in price_selectors:
        elements = soup.select(selector)
        for element in elements:
            price_text = element.text.strip()
            # Extract numbers only from price
            price_numbers = re.findall(r'\d+\.?\d*', price_text)
            if price_numbers:
                price = price_numbers[0]
                logging.info(f"Found price: {price}")
                break
        if price:
            break
    
    # If no price is found, check for price in the page content
    if not price:
        # Look for common price patterns in the HTML
        price_patterns = [
            r'price[\'":\s]+(\d+\.?\d*)',
            r'amount[\'":\s]+(\d+\.?\d*)',
            r'(?:AED|USD|EUR)\s*(\d+\.?\d*)',
            r'(\d+\.?\d*)\s*(?:AED|USD|EUR)'
        ]
        
        for pattern in price_patterns:
            matches = re.search(pattern, html_content, re.IGNORECASE)
            if matches and matches.group(1):
                price = matches.group(1)
                logging.info(f"Found price via regex: {price}")
                break
    
    # If still no price, use a default price
    if not price:
        price = "99.00"  # Default price as fallback
        logging.warning(f"No price found for {url}, using default price")
    
    # Extract description
    description = ""
    description_selectors = [
        '.product-description', '.description', '[itemprop="description"]', 
        '.product-single__description', '.product-description-container',
        '.product-details', '.details'
    ]
    
    for selector in description_selectors:
        element = soup.select_one(selector)
        if element and element.text.strip():
            description = element.text.strip()
            break
    
    # If no description, use the title as description
    if not description:
        description = title
    
    # ----- ENHANCED IMAGE EXTRACTION WITH BASIC META VALIDATION -----
    image_url = None
    image_candidates = []
    
    # 1. Try to find Open Graph meta tag images (usually high quality)
    og_image = soup.find('meta', property='og:image')
    if og_image and og_image.get('content'):
        image_candidates.append(('og:image', og_image.get('content')))
    
    # 2. If no OG image, try Twitter card image
    twitter_image = soup.find('meta', attrs={'name': 'twitter:image'})
    if twitter_image and twitter_image.get('content'):
        image_candidates.append(('twitter:image', twitter_image.get('content')))
    
    # 3. Look for JSON-LD structured data (common in e-commerce)
    json_ld_scripts = soup.find_all('script', type='application/ld+json')
    for script in json_ld_scripts:
        try:
            json_data = json.loads(script.string)
            # Look for images in Product schema
            if isinstance(json_data, dict):
                if '@type' in json_data and json_data['@type'] == 'Product' and 'image' in json_data:
                    if isinstance(json_data['image'], str):
                        image_candidates.append(('json-ld', json_data['image']))
                    elif isinstance(json_data['image'], list) and len(json_data['image']) > 0:
                        image_candidates.append(('json-ld', json_data['image'][0]))
        except (json.JSONDecodeError, AttributeError) as e:
            logging.warning(f"Error parsing JSON-LD: {e}")
    
    # 4. Try common image selectors
    image_selectors = [
        '.product-featured-img', '.product-single__photo img',
        '.product-image img', '.product-photo img', 
        '.carousel-item.active img', '.slick-active img',
        '.gallery img:first-child', '.product img:first-child',
        '#product-image', '.main-product-image img'
    ]
    
    for selector in image_selectors:
        elements = soup.select(selector)
        for element in elements:
            # Try src attribute first
            src = element.get('src')
            if src and not src.endswith('.svg') and not 'placeholder' in src.lower():
                image_candidates.append((f'selector-{selector}', src))
            
            # Try data-src for lazy-loaded images
            data_src = element.get('data-src')
            if data_src and not data_src.endswith('.svg') and not 'placeholder' in data_src.lower():
                image_candidates.append((f'data-src-{selector}', data_src))
    
    # 5. Try to find any relevant image
    all_images = soup.find_all('img')
    for img in all_images:
        src = img.get('src')
        if src and not src.endswith('.svg') and not 'placeholder' in src.lower() and not 'logo' in src.lower():
            if 'product' in src.lower() or 'item' in src.lower() or '/uploads/' in src.lower():
                image_candidates.append(('general-search', src))
    
    # Validate image candidates for Meta compatibility (basic validation only)
    for source, candidate_url in image_candidates:
        # Convert to absolute URL
        if candidate_url.startswith('/'):
            candidate_url = BASE_URL + candidate_url
        elif not candidate_url.startswith(('http://', 'https://')):
            candidate_url = urljoin(BASE_URL, candidate_url)
        
        # Basic validation and HTTPS conversion
        is_valid, validated_url, error = validate_and_fix_image_url(candidate_url)
        if is_valid:
            image_url = validated_url
            logging.info(f"Found valid image from {source}: {image_url}")
            break
        else:
            logging.warning(f"Image from {source} failed validation: {error}")
    
    # If no valid image found, use fallback
    if not image_url:
        image_url = get_fallback_image_for_meta()
        logging.warning(f"No valid image found for {url}, using fallback: {image_url}")
    
    # ----- IMPROVED AVAILABILITY DETECTION -----
    # Default to in stock unless proven otherwise
    availability = 'in stock'
    
    # 1. Try to find availability in JSON-LD
    for script in json_ld_scripts:
        try:
            json_data = json.loads(script.string)
            if isinstance(json_data, dict):
                if '@type' in json_data and json_data['@type'] == 'Product':
                    # Check for availability in offers
                    if 'offers' in json_data:
                        offers = json_data['offers']
                        if isinstance(offers, dict) and 'availability' in offers:
                            availability_url = offers['availability']
                            if 'OutOfStock' in availability_url:
                                availability = 'out of stock'
                                logging.info(f"Product is out of stock according to JSON-LD")
                                break
                            elif 'InStock' in availability_url:
                                availability = 'in stock'
                                logging.info(f"Product is in stock according to JSON-LD")
                                break
        except (json.JSONDecodeError, AttributeError) as e:
            pass
    
    # 2. Look for common out-of-stock indicators
    out_of_stock_selectors = [
        '.sold-out', '.out-of-stock', '.product-unavailable',
        '.product-out-of-stock', '.product-inventory.out-of-stock'
    ]
    
    for selector in out_of_stock_selectors:
        elements = soup.select(selector)
        if elements:
            availability = 'out of stock'
            logging.info(f"Found out-of-stock indicator with selector '{selector}'")
            break
    
    # 3. Look for text patterns indicating stock status
    stock_phrases = [
        ('out of stock', 'out of stock'),
        ('sold out', 'out of stock'),
        ('unavailable', 'out of stock'),
        ('currently unavailable', 'out of stock'),
        ('back in stock soon', 'out of stock'),
        ('in stock', 'in stock'),
        ('available for purchase', 'in stock'),
        ('ships immediately', 'in stock')
    ]
    
    for phrase, status in stock_phrases:
        # Look for phrase in body text with proximity to product-related elements
        stock_elements = soup.select('.product-single, .product-info, .product-details, .availability, .inventory, .product-form')
        for element in stock_elements:
            if element and phrase.lower() in element.text.lower():
                availability = status
                logging.info(f"Found availability from text: '{phrase}' → {status}")
                break
    
    # Generate ID from URL
    product_id = url.split('/')[-1]
    if not product_id:
        product_id = url.split('/')[-2]
    
    # Clean up the ID (remove file extensions, etc.)
    product_id = re.sub(r'\.[^/.]+$', '', product_id)
    
    # Extract brand
    brand = 'Joy and Co'  # Default brand
    
    # Try to find brand in meta tags or JSON-LD
    brand_meta = soup.find('meta', attrs={'property': 'og:brand'}) or soup.find('meta', attrs={'name': 'brand'})
    if brand_meta and brand_meta.get('content'):
        brand = brand_meta.get('content')
    else:
        # Check JSON-LD for brand
        for script in json_ld_scripts:
            try:
                json_data = json.loads(script.string)
                if isinstance(json_data, dict):
                    if '@type' in json_data and json_data['@type'] == 'Product' and 'brand' in json_data:
                        if isinstance(json_data['brand'], dict) and 'name' in json_data['brand']:
                            brand = json_data['brand']['name']
                            break
                        elif isinstance(json_data['brand'], str):
                            brand = json_data['brand']
                            break
            except (json.JSONDecodeError, AttributeError):
                pass
    
    # Return product data
    product_data = {
        'id': product_id,
        'title': title,
        'description': description,
        'price': price,
        'currency': 'AED',  # Dubai currency
        'image_link': image_url,
        'availability': availability,
        'condition': 'new',
        'link': url,
        'brand': brand
    }
    
    # Save product data for debugging
    product_data_str = "\n".join([f"{k}: {v}" for k, v in product_data.items()])
    save_debug_info_to_feeds(product_data_str, f"product_data_{product_id}.txt")
    
    return product_data

def batch_validate_images_for_meta(products):
    """Basic validation of all images in a batch of products for Meta compatibility"""
    validated_products = []
    
    for product in products:
        if product.get('image_link'):
            is_valid, validated_url, error = validate_and_fix_image_url(product['image_link'])
            if is_valid:
                product['image_link'] = validated_url
                validated_products.append(product)
                logging.info(f"Product {product['id']} image validated: {validated_url}")
            else:
                logging.error(f"Product {product['id']} has invalid image: {error}")
                # Replace with fallback
                fallback = get_fallback_image_for_meta()
                product['image_link'] = fallback
                validated_products.append(product)
                logging.warning(f"Product {product['id']} using fallback image: {fallback}")
        else:
            # No image link, use fallback
            fallback = get_fallback_image_for_meta()
            product['image_link'] = fallback
            validated_products.append(product)
            logging.warning(f"Product {product['id']} had no image, using fallback: {fallback}")
    
    return validated_products

def generate_csv_feed(products):
    """Generate CSV feed for Google Shopping"""
    os.makedirs('feeds/google', exist_ok=True)
    
    logging.info(f"Generating CSV feed with {len(products)} products")
    
    try:
        with open('feeds/google/shopping_feed.csv', 'w', newline='', encoding='utf-8') as csvfile:
            fieldnames = ['id', 'title', 'description', 'link', 'image_link', 'price', 'currency', 'availability', 'condition', 'brand']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            
            writer.writeheader()
            for product in products:
                writer.writerow(product)
                
        logging.info(f"CSV feed generated at feeds/google/shopping_feed.csv")
        
        # Also create a copy in the main feeds folder for backward compatibility
        with open('feeds/google_shopping_feed.csv', 'w', newline='', encoding='utf-8') as csvfile:
            fieldnames = ['id', 'title', 'description', 'link', 'image_link', 'price', 'currency', 'availability', 'condition', 'brand']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            
            writer.writeheader()
            for product in products:
                writer.writerow(product)
    except Exception as e:
        logging.error(f"Error generating CSV feed: {e}")

def generate_xml_feed(products):
    """Generate XML feed for Google Shopping"""
    os.makedirs('feeds/google', exist_ok=True)
    
    logging.info(f"Generating XML feed with {len(products)} products")
    
    try:
        # Create XML structure for Google Shopping
        root = ET.Element('rss')
        root.set('version', '2.0')
        root.set('xmlns:g', 'http://base.google.com/ns/1.0')
        
        channel = ET.SubElement(root, 'channel')
        ET.SubElement(channel, 'title').text = 'Joy and Co Product Feed'
        ET.SubElement(channel, 'link').text = BASE_URL
        ET.SubElement(channel, 'description').text = 'Product feed for Google Shopping'
        
        for product in products:
            item = ET.SubElement(channel, 'item')
            
            ET.SubElement(item, 'g:id').text = str(product['id'])
            ET.SubElement(item, 'title').text = product['title']
            ET.SubElement(item, 'description').text = product['description']
            ET.SubElement(item, 'link').text = product['link']
            ET.SubElement(item, 'g:image_link').text = product['image_link']
            ET.SubElement(item, 'g:price').text = f"{product['price']} {product['currency']}"
            ET.SubElement(item, 'g:availability').text = product['availability']
            ET.SubElement(item, 'g:condition').text = product['condition']
            ET.SubElement(item, 'g:brand').text = product['brand']
        
        # Write to the new organized location
        tree = ET.ElementTree(root)
        tree.write('feeds/google/shopping_feed.xml', encoding='utf-8', xml_declaration=True)
        
        # Also write to the original location for backward compatibility
        tree.write('feeds/google_shopping_feed.xml', encoding='utf-8', xml_declaration=True)
        
        logging.info(f"Google Shopping XML feed generated at feeds/google/shopping_feed.xml")
        
        # Create a separate XML feed for Meta shopping ads
        generate_meta_xml_feed(products)
    except Exception as e:
        logging.error(f"Error generating Google XML feed: {e}")

def generate_meta_xml_feed(products):
    """Generate XML feed for Meta Catalog with enhanced image validation"""
    try:
        # Create subdirectory for Meta feeds
        os.makedirs('feeds/meta', exist_ok=True)
        
        # Validate all images for Meta before generating feed
        validated_products = batch_validate_images_for_meta(products.copy())
        
        # Create XML structure for Meta Catalog
        root = ET.Element('feed')
        
        for product in validated_products:
            item = ET.SubElement(root, 'item')
            
            ET.SubElement(item, 'id').text = str(product['id'])
            ET.SubElement(item, 'title').text = product['title']
            ET.SubElement(item, 'description').text = product['description']
            ET.SubElement(item, 'link').text = product['link']
            ET.SubElement(item, 'image_link').text = product['image_link']
            ET.SubElement(item, 'price').text = f"{product['price']} {product['currency']}"
            ET.SubElement(item, 'availability').text = product['availability']
            ET.SubElement(item, 'condition').text = product['condition']
            ET.SubElement(item, 'brand').text = product['brand']
        
        # Write to the new organized location
        tree = ET.ElementTree(root)
        tree.write('feeds/meta/shopping_feed.xml', encoding='utf-8', xml_declaration=True)
        
        # Also write to the original location for backward compatibility
        tree.write('feeds/meta_shopping_feed.xml', encoding='utf-8', xml_declaration=True)
        
        logging.info(f"Meta Shopping XML feed generated at feeds/meta/shopping_feed.xml with {len(validated_products)} validated products")
        
        # Generate CSV feed for Meta as well
        generate_meta_csv_feed(validated_products)
    except Exception as e:
        logging.error(f"Error generating Meta XML feed: {e}")
        
def generate_meta_csv_feed(products):
    """Generate CSV feed for Meta Catalog with pre-validated images"""
    os.makedirs('feeds/meta', exist_ok=True)
    
    logging.info(f"Generating CSV feed for Meta with {len(products)} products")
    
    try:
        with open('feeds/meta/shopping_feed.csv', 'w', newline='', encoding='utf-8') as csvfile:
            # Meta uses similar fields to Google but with some differences
            fieldnames = ['id', 'title', 'description', 'link', 'image_link', 'price', 'availability', 'condition', 'brand']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            
            writer.writeheader()
            for product in products:
                # Format the product data for Meta
                meta_product = product.copy()
                meta_product['price'] = f"{product['price']} {product['currency']}"
                
                # Remove currency field as it's now part of price
                if 'currency' in meta_product:
                    del meta_product['currency']
                
                writer.writerow(meta_product)
                
        logging.info(f"CSV feed for Meta generated at feeds/meta/shopping_feed.csv")
        
        # Also create compatibility copy
        with open('feeds/meta_shopping_feed.csv', 'w', newline='', encoding='utf-8') as csvfile:
            fieldnames = ['id', 'title', 'description', 'link', 'image_link', 'price', 'availability', 'condition', 'brand']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            
            writer.writeheader()
            for product in products:
                meta_product = product.copy()
                meta_product['price'] = f"{product['price']} {product['currency']}"
                if 'currency' in meta_product:
                    del meta_product['currency']
                writer.writerow(meta_product)
                
    except Exception as e:
        logging.error(f"Error generating CSV feed for Meta: {e}")

def main():
    logging.info("Starting crawler for JoyAndCo products with basic Meta image validation (no PIL)")
    
    # Create feed directory structure
    os.makedirs('feeds/google', exist_ok=True)
    os.makedirs('feeds/meta', exist_ok=True)
    os.makedirs('feeds/debug', exist_ok=True)
    
    # Create debug info summary file
    debug_summary = ["JoyAndCo Crawler Debug Summary with Basic Meta Image Validation\n"]
    debug_summary.append(f"Base URL: {BASE_URL}")
    
    # Read product URLs from Excel file
    excel_file_path = 'product_urls.xlsx'
    product_links = read_product_urls_from_excel(excel_file_path)
    
    if not product_links:
        debug_summary.append(f"ERROR: No product URLs found in {excel_file_path}")
        logging.error(f"No product URLs found in {excel_file_path}")
        
        # Create empty feed files to avoid errors
        with open('feeds/google/shopping_feed.csv', 'w', encoding='utf-8') as f:
            f.write("id,title,description,link,image_link,price,currency,availability,condition,brand\n")
        
        with open('feeds/google/shopping_feed.xml', 'w', encoding='utf-8') as f:
            f.write('<?xml version="1.0" encoding="utf-8"?>\n<rss version="2.0" xmlns:g="http://base.google.com/ns/1.0">\n<channel>\n<title>Joy and Co Product Feed</title>\n<link>https://joyandco.com</link>\n<description>Product feed for Google Shopping</description>\n</channel>\n</rss>')
        
        with open('feeds/meta/shopping_feed.xml', 'w', encoding='utf-8') as f:
            f.write('<?xml version="1.0" encoding="utf-8"?>\n<feed>\n</feed>')
            
        with open('feeds/meta/shopping_feed.csv', 'w', encoding='utf-8') as f:
            f.write("id,title,description,link,image_link,price,availability,condition,brand\n")
        
        # Create compatibility copies
        with open('feeds/google_shopping_feed.csv', 'w', encoding='utf-8') as f:
            f.write("id,title,description,link,image_link,price,currency,availability,condition,brand\n")
            
        with open('feeds/google_shopping_feed.xml', 'w', encoding='utf-8') as f:
            f.write('<?xml version="1.0" encoding="utf-8"?>\n<rss version="2.0" xmlns:g="http://base.google.com/ns/1.0">\n<channel>\n<title>Joy and Co Product Feed</title>\n<link>https://joyandco.com</link>\n<description>Product feed for Google Shopping</description>\n</channel>\n</rss>')
            
        with open('feeds/meta_shopping_feed.xml', 'w', encoding='utf-8') as f:
            f.write('<?xml version="1.0" encoding="utf-8"?>\n<feed>\n</feed>')
            
        with open('feeds/meta_shopping_feed.csv', 'w', encoding='utf-8') as f:
            f.write("id,title,description,link,image_link,price,availability,condition,brand\n")
        
        save_debug_info_to_feeds("\n".join(debug_summary), "debug_summary.txt")
        return
    
    debug_summary.append(f"\nFound {len(product_links)} product URLs in {excel_file_path}")
    
    # List a few of the found links in debug
    debug_summary.append("\nSample of product URLs:")
    for link in product_links[:5]:  # Show first 5 links
        debug_summary.append(f"- {link}")
    if len(product_links) > 5:
        debug_summary.append(f"... and {len(product_links) - 5} more")
    
    # Fetch and extract data for each product
    products = []
    product_attempts = []
    image_validation_results = []
    
    # Process a batch of products at a time to avoid overwhelming
    batch_size = 50  # Process in batches for better handling
    
    for batch_start in range(0, len(product_links), batch_size):
        batch_end = min(batch_start + batch_size, len(product_links))
        batch = product_links[batch_start:batch_end]
        
        logging.info(f"Processing batch {batch_start//batch_size + 1} ({batch_start}-{batch_end-1})")
        
        for index, link in enumerate(batch):
            overall_index = batch_start + index
            logging.info(f"Processing product {overall_index+1}/{len(product_links)}: {link}")
            product_attempts.append(f"\nProduct {overall_index+1}: {link}")
            
            # Add a small delay between requests to avoid rate limiting
            if index > 0:
                time.sleep(1 + random.random())
            
            product_html = get_page_content(link)
            if product_html:
                product_attempts.append(f"  ✓ Successful access")
                
                # Get the page title
                soup = BeautifulSoup(product_html, 'html.parser')
                page_title = soup.title.text if soup.title else "No title found"
                product_attempts.append(f"  Page title: {page_title}")
                
                product_data = extract_product_data(link, product_html)
                if product_data:
                    products.append(product_data)
                    product_attempts.append(f"  ✓ Extracted data: {product_data['title']}")
                    product_attempts.append(f"    • Image: {product_data['image_link']}")
                    product_attempts.append(f"    • Price: {product_data['price']} {product_data['currency']}")
                    product_attempts.append(f"    • Availability: {product_data['availability']}")
                    
                    # Basic image validation for Meta
                    is_valid, validated_url, error = validate_and_fix_image_url(product_data['image_link'])
                    if is_valid:
                        image_validation_results.append(f"  ✓ {product_data['title']}: Image valid for Meta")
                    else:
                        image_validation_results.append(f"  ✗ {product_data['title']}: Image issue - {error}")
                    
                    logging.info(f"Extracted data for: {product_data['title']}")
                else:
                    product_attempts.append(f"  ✗ Failed to extract product data")
                    logging.warning(f"Skipping product at {link} due to missing critical data")
            else:
                product_attempts.append(f"  ✗ Failed to access")
                logging.error(f"Failed to fetch product page: {link}")
    
    debug_summary.append("\nProduct fetch attempts:")
    debug_summary.extend(product_attempts)
    
    debug_summary.append(f"\nImage validation results for Meta:")
    debug_summary.extend(image_validation_results)
    
    # Generate feeds
    if products:
        generate_csv_feed(products)
        generate_xml_feed(products)
        debug_summary.append(f"\nSUCCESS: Generated product feeds for {len(products)} products")
        debug_summary.append(f"\nFeed files created:")
        debug_summary.append(f"- feeds/google/shopping_feed.csv")
        debug_summary.append(f"- feeds/google/shopping_feed.xml")
        debug_summary.append(f"- feeds/meta/shopping_feed.xml (with basic image validation)")
        debug_summary.append(f"- feeds/meta/shopping_feed.csv (with basic image validation)")
        debug_summary.append(f"- feeds/google_shopping_feed.csv (compatibility copy)")
        debug_summary.append(f"- feeds/google_shopping_feed.xml (compatibility copy)")
        debug_summary.append(f"- feeds/meta_shopping_feed.xml (compatibility copy)")
        debug_summary.append(f"- feeds/meta_shopping_feed.csv (compatibility copy)")
        
        # Count validation results
        valid_images = len([r for r in image_validation_results if "✓" in r])
        invalid_images = len([r for r in image_validation_results if "✗" in r])
        debug_summary.append(f"\nImage validation summary:")
        debug_summary.append(f"- Valid images for Meta: {valid_images}")
        debug_summary.append(f"- Images requiring fallbacks: {invalid_images}")
        
        logging.info(f"Successfully generated product feeds for {len(products)} products")
        logging.info(f"Meta image validation: {valid_images} valid, {invalid_images} using fallbacks")
    else:
        debug_summary.append("\nERROR: No products found to generate feeds")
        logging.warning("No products found to generate feeds")
        
        # Create empty feed files to avoid errors
        with open('feeds/google/shopping_feed.csv', 'w', encoding='utf-8') as f:
            f.write("id,title,description,link,image_link,price,currency,availability,condition,brand\n")
        
        with open('feeds/google/shopping_feed.xml', 'w', encoding='utf-8') as f:
            f.write('<?xml version="1.0" encoding="utf-8"?>\n<rss version="2.0" xmlns:g="http://base.google.com/ns/1.0">\n<channel>\n<title>Joy and Co Product Feed</title>\n<link>https://joyandco.com</link>\n<description>Product feed for Google Shopping</description>\n</channel>\n</rss>')
        
        with open('feeds/meta/shopping_feed.xml', 'w', encoding='utf-8') as f:
            f.write('<?xml version="1.0" encoding="utf-8"?>\n<feed>\n</feed>')
            
        with open('feeds/meta/shopping_feed.csv', 'w', encoding='utf-8') as f:
            f.write("id,title,description,link,image_link,price,availability,condition,brand\n")
            
        # Create compatibility copies
        with open('feeds/google_shopping_feed.csv', 'w', encoding='utf-8') as f:
            f.write("id,title,description,link,image_link,price,currency,availability,condition,brand\n")
            
        with open('feeds/google_shopping_feed.xml', 'w', encoding='utf-8') as f:
            f.write('<?xml version="1.0" encoding="utf-8"?>\n<rss version="2.0" xmlns:g="http://base.google.com/ns/1.0">\n<channel>\n<title>Joy and Co Product Feed</title>\n<link>https://joyandco.com</link>\n<description>Product feed for Google Shopping</description>\n</channel>\n</rss>')
            
        with open('feeds/meta_shopping_feed.xml', 'w', encoding='utf-8') as f:
            f.write('<?xml version="1.0" encoding="utf-8"?>\n<feed>\n</feed>')
            
        with open('feeds/meta_shopping_feed.csv', 'w', encoding='utf-8') as f:
            f.write("id,title,description,link,image_link,price,availability,condition,brand\n")
        
        debug_summary.append("Created empty feed files")
        logging.info("Created empty feed files")
    
    # Save final debug summary
    save_debug_info_to_feeds("\n".join(debug_summary), "debug_summary.txt")
    
    # Create a separate detailed image validation report
    image_report = ["Basic Image Validation Report for Meta Ads\n"]
    image_report.append("="*50)
    image_report.append(f"Total products processed: {len(products)}")
    
    if products:
        image_report.append("\nImage validation details:")
        for product in products:
            image_report.append(f"\nProduct: {product['title']}")
            image_report.append(f"Image URL: {product['image_link']}")
            
            # Re-validate to get detailed info
            is_valid, validated_url, error = validate_and_fix_image_url(product['image_link'])
            if is_valid:
                image_report.append("Status: ✓ VALID for Meta ads")
                if validated_url != product['image_link']:
                    image_report.append(f"Corrected URL: {validated_url}")
            else:
                image_report.append(f"Status: ✗ INVALID - {error}")
                image_report.append("Action: Will use fallback image in Meta feed")
        
        image_report.append(f"\nRecommendations:")
        image_report.append("1. Ensure all product images are HTTPS")
        image_report.append("2. Verify images are accessible")
        image_report.append("3. Consider uploading a default product image that meets Meta specs")
        image_report.append("4. Note: Advanced validation (image dimensions) requires PIL library")
        
    save_debug_info_to_feeds("\n".join(image_report), "meta_image_validation_report.txt")
    
    logging.info("Crawler completed with basic Meta image validation (no PIL)")

if __name__ == "__main__":
    main()
