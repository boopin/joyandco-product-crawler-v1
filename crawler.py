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

def extract_product_data(url, html_content):
    """Extract product data from a product page"""
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
        logging.info(f"Price selector '{selector}' found {len(elements)} elements")
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
    
    # Extract image URL
    image_url = ""
    image_selectors = [
        '.product-single__photo img', '.product-featured-img', 
        '.product-image img', '.product-photo img', 
        '[itemprop="image"]', '.gallery img', 
        '.carousel img', '.product img',
        '.productView-thumbnail-link img'
    ]
    
    for selector in image_selectors:
        elements = soup.select(selector)
        for element in elements:
            src = element.get('src')
            if src:
                image_url = urljoin(BASE_URL, src)
                break
        if image_url:
            break
    
    # If no image found, look for data-src which is common for lazy-loaded images
    if not image_url:
        images = soup.select('img[data-src]')
        if images:
            data_src = images[0].get('data-src')
            if data_src:
                image_url = urljoin(BASE_URL, data_src)
    
    # If still no image, use a placeholder
    if not image_url:
        image_url = f"{BASE_URL}/placeholder.jpg"
        logging.warning(f"No image found for {url}, using placeholder")
    
    # Generate ID from URL
    product_id = url.split('/')[-1]
    if not product_id:
        product_id = url.split('/')[-2]
    
    # Clean up the ID (remove file extensions, etc.)
    product_id = re.sub(r'\.[^/.]+$', '', product_id)
    
    # Check stock status
    availability = 'in stock'  # Default to in stock
    for stock_text in ['out of stock', 'sold out', 'unavailable']:
        if stock_text in html_content.lower():
            availability = 'out of stock'
            break
    
    # Extract brand
    brand = 'Joy and Co'  # Default brand
    
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
    """Generate XML feed for Meta Catalog"""
    try:
        # Create subdirectory for Meta feeds
        os.makedirs('feeds/meta', exist_ok=True)
        
        # Create XML structure for Meta Catalog
        root = ET.Element('feed')
        
        for product in products:
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
        
        logging.info(f"Meta Shopping XML feed generated at feeds/meta/shopping_feed.xml")
    except Exception as e:
        logging.error(f"Error generating Meta XML feed: {e}")

def main():
    logging.info("Starting crawler for JoyAndCo products")
    
    # Create feed directory structure
    os.makedirs('feeds/google', exist_ok=True)
    os.makedirs('feeds/meta', exist_ok=True)
    os.makedirs('feeds/debug', exist_ok=True)
    
    # Create debug info summary file
    debug_summary = ["JoyAndCo Crawler Debug Summary\n"]
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
        
        # Create compatibility copies
        with open('feeds/google_shopping_feed.csv', 'w', encoding='utf-8') as f:
            f.write("id,title,description,link,image_link,price,currency,availability,condition,brand\n")
            
        with open('feeds/google_shopping_feed.xml', 'w', encoding='utf-8') as f:
            f.write('<?xml version="1.0" encoding="utf-8"?>\n<rss version="2.0" xmlns:g="http://base.google.com/ns/1.0">\n<channel>\n<title>Joy and Co Product Feed</title>\n<link>https://joyandco.com</link>\n<description>Product feed for Google Shopping</description>\n</channel>\n</rss>')
            
        with open('feeds/meta_shopping_feed.xml', 'w', encoding='utf-8') as f:
            f.write('<?xml version="1.0" encoding="utf-8"?>\n<feed>\n</feed>')
        
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
                    logging.info(f"Extracted data for: {product_data['title']}")
                else:
                    product_attempts.append(f"  ✗ Failed to extract product data")
                    logging.warning(f"Skipping product at {link} due to missing critical data")
            else:
                product_attempts.append(f"  ✗ Failed to access")
                logging.error(f"Failed to fetch product page: {link}")
    
    debug_summary.append("\nProduct fetch attempts:")
    debug_summary.extend(product_attempts)
    
    # Generate feeds
    if products:
        generate_csv_feed(products)
        generate_xml_feed(products)
        debug_summary.append(f"\nSUCCESS: Generated product feeds for {len(products)} products")
        debug_summary.append(f"\nFeed files created:")
        debug_summary.append(f"- feeds/google/shopping_feed.csv")
        debug_summary.append(f"- feeds/google/shopping_feed.xml")
        debug_summary.append(f"- feeds/meta/shopping_feed.xml")
        debug_summary.append(f"- feeds/google_shopping_feed.csv (compatibility copy)")
        debug_summary.append(f"- feeds/google_shopping_feed.xml (compatibility copy)")
        debug_summary.append(f"- feeds/meta_shopping_feed.xml (compatibility copy)")
        logging.info(f"Successfully generated product feeds for {len(products)} products")
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
            
        # Create compatibility copies
        with open('feeds/google_shopping_feed.csv', 'w', encoding='utf-8') as f:
            f.write("id,title,description,link,image_link,price,currency,availability,condition,brand\n")
            
        with open('feeds/google_shopping_feed.xml', 'w', encoding='utf-8') as f:
            f.write('<?xml version="1.0" encoding="utf-8"?>\n<rss version="2.0" xmlns:g="http://base.google.com/ns/1.0">\n<channel>\n<title>Joy and Co Product Feed</title>\n<link>https://joyandco.com</link>\n<description>Product feed for Google Shopping</description>\n</channel>\n</rss>')
            
        with open('feeds/meta_shopping_feed.xml', 'w', encoding='utf-8') as f:
            f.write('<?xml version="1.0" encoding="utf-8"?>\n<feed>\n</feed>')
        
        debug_summary.append("Created empty feed files")
        logging.info("Created empty feed files")
    
    # Save final debug summary
    save_debug_info_to_feeds("\n".join(debug_summary), "debug_summary.txt")

if __name__ == "__main__":
    main()

if __name__ == "__main__":
    main().0" encoding="utf-8"?>\n<feed>\n</feed>')
        
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
    
    for index, link in enumerate(product_links):
        logging.info(f"Processing product {index+1}/{len(product_links)}: {link}")
        product_attempts.append(f"\nProduct {index+1}: {link}")
        
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
                logging.info(f"Extracted data for: {product_data['title']}")
            else:
                product_attempts.append(f"  ✗ Failed to extract product data")
                logging.warning(f"Skipping product at {link} due to missing critical data")
        else:
            product_attempts.append(f"  ✗ Failed to access")
            logging.error(f"Failed to fetch product page: {link}")
    
    debug_summary.append("\nProduct fetch attempts:")
    debug_summary.extend(product_attempts)
    
    # Generate feeds
    if products:
        generate_csv_feed(products)
        generate_xml_feed(products)
        debug_summary.append(f"\nSUCCESS: Generated product feeds for {len(products)} products")
        logging.info(f"Successfully generated product feeds for {len(products)} products")
    else:
        debug_summary.append("\nERROR: No products found to generate feeds")
        logging.warning("No products found to generate feeds")
        
        # Create empty feed files to avoid errors
        os.makedirs('feeds', exist_ok=True)
        with open('feeds/google_shopping_feed.csv', 'w', encoding='utf-8') as f:
            f.write("id,title,description,link,image_link,price,currency,availability,condition,brand\n")
        
        with open('feeds/google_shopping_feed.xml', 'w', encoding='utf-8') as f:
            f.write('<?xml version="1.0" encoding="utf-8"?>\n<rss version="2.0" xmlns:g="http://base.google.com/ns/1.0">\n<channel>\n<title>Joy and Co Product Feed</title>\n<link>https://joyandco.com</link>\n<description>Product feed for Google Shopping</description>\n</channel>\n</rss>')
        
        with open('feeds/meta_shopping_feed.xml', 'w', encoding='utf-8') as f:
            f.write('<?xml version="1.0" encoding="utf-8"?>\n<feed>\n</feed>')
        
        debug_summary.append("Created empty feed files")
        logging.info("Created empty feed files")
    
    # Save final debug summary
    save_debug_info_to_feeds("\n".join(debug_summary), "debug_summary.txt")

if __name__ == "__main__":
    main()
