import requests
from bs4 import BeautifulSoup
import csv
import xml.etree.ElementTree as ET
import os
import re
import logging
import time
import random
from urllib.parse import urljoin

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

BASE_URL = "https://joyandco.com"
PRODUCT_LIST_URL = f"{BASE_URL}/product/"

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

def extract_product_links(html_content):
    """Extract product links from the product listing page"""
    if not html_content:
        return []
    
    soup = BeautifulSoup(html_content, 'html.parser')
    save_debug_html(str(soup.prettify()), "product_list_page")
    
    # Try different selector patterns to find product links
    product_links = []
    
    # Pattern 1: Common product card patterns
    product_cards = soup.select('.product-card a, .product-item a, .product a, .product-box a, .item a')
    for link in product_cards:
        href = link.get('href')
        if href and '/product/' in href:
            product_links.append(urljoin(BASE_URL, href))
    
    # Pattern 2: Find links with product in URL
    all_links = soup.select('a[href*="/product/"]')
    for link in all_links:
        href = link.get('href')
        if href:
            product_links.append(urljoin(BASE_URL, href))
    
    # Pattern 3: Find product images and get their parent links
    product_images = soup.select('.product img, .product-item img')
    for img in product_images:
        parent_link = img.find_parent('a')
        if parent_link and parent_link.get('href'):
            href = parent_link.get('href')
            product_links.append(urljoin(BASE_URL, href))
    
    # Remove duplicates
    product_links = list(set(product_links))
    logging.info(f"Found {len(product_links)} unique product links")
    
    # Save links for debugging
    os.makedirs('debug', exist_ok=True)
    with open('debug/product_links.txt', 'w') as f:
        for link in product_links:
            f.write(f"{link}\n")
    
    return product_links

def extract_product_data(url, html_content):
    """Extract product data from a product page"""
    if not html_content:
        return None
    
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Debugging save
    page_name = url.split('/')[-1].replace('.', '_')
    save_debug_html(str(soup.prettify()), f"product_{page_name}")
    
    # Try different selectors to find product info
    title = None
    for selector in ['h1.product-title', '.product-details h1', '.product-name', '.product-title', '.product h1', 'h1', '.title']:
        element = soup.select_one(selector)
        if element and element.text.strip():
            title = element.text.strip()
            break
    
    price = None
    for selector in ['.product-price', '.price', '.product-info .price', '[itemprop="price"]', '.amount', '.current-price']:
        element = soup.select_one(selector)
        if element and element.text.strip():
            # Extract numbers only from price
            price_text = element.text.strip()
            price_numbers = re.findall(r'\d+\.?\d*', price_text)
            if price_numbers:
                price = price_numbers[0]
                break
    
    description = None
    for selector in ['.product-description', '.description', '[itemprop="description"]', '.product-short-description', '.details', '.product-details']:
        element = soup.select_one(selector)
        if element and element.text.strip():
            description = element.text.strip()
            break
    
    image_url = None
    for selector in ['.product-image img', '.product-gallery img', '.product-photo img', '[itemprop="image"]', '.gallery img', '.carousel img', '.product img']:
        element = soup.select_one(selector)
        if element and element.get('src'):
            image_src = element.get('src')
            image_url = urljoin(BASE_URL, image_src)
            break
    
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
    brand = None
    for selector in ['.brand', '[itemprop="brand"]', '.manufacturer']:
        element = soup.select_one(selector)
        if element and element.text.strip():
            brand = element.text.strip()
            break
    
    if not brand:
        brand = 'Joy and Co'  # Default brand
    
    # Only return if essential fields are present
    if title and price:
        return {
            'id': product_id,
            'title': title,
            'description': description or '',
            'price': price,
            'currency': 'AED',  # Dubai currency
            'image_link': image_url or '',
            'availability': availability,
            'condition': 'new',
            'link': url,
            'brand': brand
        }
    
    return None

def generate_csv_feed(products):
    """Generate CSV feed for Google Shopping"""
    os.makedirs('feeds', exist_ok=True)
    
    logging.info(f"Generating CSV feed with {len(products)} products")
    
    try:
        with open('feeds/google_shopping_feed.csv', 'w', newline='', encoding='utf-8') as csvfile:
            fieldnames = ['id', 'title', 'description', 'link', 'image_link', 'price', 'currency', 'availability', 'condition', 'brand']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            
            writer.writeheader()
            for product in products:
                writer.writerow(product)
                
        logging.info(f"CSV feed generated at feeds/google_shopping_feed.csv")
    except Exception as e:
        logging.error(f"Error generating CSV feed: {e}")

def generate_xml_feed(products):
    """Generate XML feed for Google Shopping"""
    os.makedirs('feeds', exist_ok=True)
    
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
        
        # Write to file
        tree = ET.ElementTree(root)
        tree.write('feeds/google_shopping_feed.xml', encoding='utf-8', xml_declaration=True)
        
        logging.info(f"Google Shopping XML feed generated at feeds/google_shopping_feed.xml")
        
        # Create a separate XML feed for Meta shopping ads
        generate_meta_xml_feed(products)
    except Exception as e:
        logging.error(f"Error generating Google XML feed: {e}")

def generate_meta_xml_feed(products):
    """Generate XML feed for Meta Catalog"""
    try:
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
        
        # Write to file
        tree = ET.ElementTree(root)
        tree.write('feeds/meta_shopping_feed.xml', encoding='utf-8', xml_declaration=True)
        
        logging.info(f"Meta Shopping XML feed generated at feeds/meta_shopping_feed.xml")
    except Exception as e:
        logging.error(f"Error generating Meta XML feed: {e}")

def handle_pagination(html_content):
    """This function would handle pagination if the site has it instead of view more button
    For now it returns the original HTML as we're initially focusing on the first page"""
    # This would be implemented if the site uses pagination
    return html_content

def main():
    logging.info("Starting crawler for JoyAndCo products")
    
    # Fetch the product listing page
    product_list_html = get_page_content(PRODUCT_LIST_URL)
    if not product_list_html:
        logging.error("Failed to fetch product listing page")
        return
    
    # Handle pagination if needed
    all_products_html = handle_pagination(product_list_html)
    
    # Extract product links
    product_links = extract_product_links(all_products_html)
    if not product_links:
        logging.warning("No product links found on the page")
        logging.info(f"Trying fallback approach with direct URL fetching")
        
        # Fallback: Try to guess some product URLs
        fallback_links = []
        # Try to generate some product URLs based on common patterns
        for i in range(1, 50):  # Try 50 potential product IDs
            fallback_links.append(f"{BASE_URL}/product/product-{i}")
            fallback_links.append(f"{BASE_URL}/product/{i}")
        
        product_links = fallback_links
    
    # Fetch and extract data for each product
    products = []
    for index, link in enumerate(product_links):
        logging.info(f"Processing product {index+1}/{len(product_links)}: {link}")
        
        # Add a small delay between requests to avoid rate limiting
        if index > 0:
            time.sleep(1 + random.random())
        
        product_html = get_page_content(link)
        if product_html:
            product_data = extract_product_data(link, product_html)
            if product_data:
                products.append(product_data)
                logging.info(f"Extracted data for: {product_data['title']}")
            else:
                logging.warning(f"Skipping product at {link} due to missing critical data")
        else:
            logging.error(f"Failed to fetch product page: {link}")
    
    # Generate feeds
    if products:
        generate_csv_feed(products)
        generate_xml_feed(products)
        logging.info(f"Successfully generated product feeds for {len(products)} products")
    else:
        logging.warning("No products found to generate feeds")
        
        # Create empty feed files to avoid errors
        os.makedirs('feeds', exist_ok=True)
        with open('feeds/google_shopping_feed.csv', 'w', encoding='utf-8') as f:
            f.write("id,title,description,link,image_link,price,currency,availability,condition,brand\n")
        
        with open('feeds/google_shopping_feed.xml', 'w', encoding='utf-8') as f:
            f.write('<?xml version="1.0" encoding="utf-8"?>\n<rss version="2.0" xmlns:g="http://base.google.com/ns/1.0">\n<channel>\n<title>Joy and Co Product Feed</title>\n<link>https://joyandco.com</link>\n<description>Product feed for Google Shopping</description>\n</channel>\n</rss>')
        
        with open('feeds/meta_shopping_feed.xml', 'w', encoding='utf-8') as f:
            f.write('<?xml version="1.0" encoding="utf-8"?>\n<feed>\n</feed>')
        
        logging.info("Created empty feed files")

if __name__ == "__main__":
    main()
