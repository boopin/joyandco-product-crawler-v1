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
PRODUCT_LIST_URL = f"{BASE_URL}/products/"  # This is correct

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
    """Save debug information to the feeds directory so it gets committed"""
    os.makedirs('feeds', exist_ok=True)
    with open(f'feeds/{filename}', 'w', encoding='utf-8') as f:
        f.write(content)
    logging.info(f"Saved debug info to feeds/{filename}")

def extract_product_links(html_content):
    """Extract product links from the product listing page"""
    if not html_content:
        return []
    
    soup = BeautifulSoup(html_content, 'html.parser')
    save_debug_html(str(soup.prettify()), "product_list_page")
    
    # Save a snippet of the HTML to the feeds directory
    html_snippet = html_content[:5000] if len(html_content) > 5000 else html_content
    save_debug_info_to_feeds(html_snippet, "product_page_snippet.html")
    
    # DEBUG: Log all links on the page to see what's available
    all_links = soup.find_all('a')
    logging.info(f"All links on page: {len(all_links)}")
    
    links_debug_text = ""
    for link in all_links:
        href = link.get('href')
        if href:
            links_debug_text += f"{href}\n"
            logging.info(f"Found link: {href}")
    
    # Save all links to the feeds directory
    save_debug_info_to_feeds(links_debug_text, "all_page_links.txt")
    
    # Try different selector patterns to find product links
    product_links = []
    
    # Log page title to make sure we're on the right page
    page_title = soup.title.text if soup.title else "No title found"
    logging.info(f"Page title: {page_title}")
    
    # Save page title to feeds
    save_debug_info_to_feeds(f"Page title: {page_title}\n", "page_info.txt")
    
    # Updated selectors based on common Shopify/WooCommerce patterns
    selectors = [
        '.product-card a', 
        '.product-item a', 
        '.product a', 
        '.product-box a', 
        '.item a', 
        '.product-grid-item a', 
        '.products a', 
        '.collection-item a', 
        'li.product a',
        '.product-link',
        '.category-product a',
        '.image-wrapper a'
    ]
    
    for selector in selectors:
        elements = soup.select(selector)
        logging.info(f"Selector '{selector}' found {len(elements)} elements")
        save_debug_info_to_feeds(f"Selector '{selector}' found {len(elements)} elements\n", "selector_results.txt")
        
        for link in elements:
            href = link.get('href')
            if href:
                product_links.append(urljoin(BASE_URL, href))
                logging.info(f"Found product link: {href}")
    
    # Find all links that might be product links
    href_patterns = ['/products/', '/product/', '/collections/', '/collection/', '/shop/']
    for pattern in href_patterns:
        links = soup.select(f'a[href*="{pattern}"]')
        logging.info(f"Links with '{pattern}' in href: {len(links)}")
        
        for link in links:
            href = link.get('href')
            if href:
                product_links.append(urljoin(BASE_URL, href))
                logging.info(f"Found product link by href pattern '{pattern}': {href}")
    
    # Find product images and get their parent links
    image_selectors = [
        '.product img', 
        '.product-item img', 
        '.product-image img', 
        '.collection-item img', 
        'li.product img',
        '.category-product img',
        '.product-grid-item img'
    ]
    
    for selector in image_selectors:
        images = soup.select(selector)
        logging.info(f"Image selector '{selector}' found {len(images)} elements")
        
        for img in images:
            parent_link = img.find_parent('a')
            if parent_link and parent_link.get('href'):
                href = parent_link.get('href')
                product_links.append(urljoin(BASE_URL, href))
                logging.info(f"Found product link from image: {href}")
    
    # Remove duplicates
    product_links = list(set(product_links))
    logging.info(f"Found {len(product_links)} unique product links")
    
    # Save links for debugging
    links_text = "\n".join(product_links)
    save_debug_info_to_feeds(links_text, "found_product_links.txt")
    
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

def check_shopify_collections():
    """Check if the site uses Shopify collections structure"""
    collection_urls = [
        f"{BASE_URL}/collections/all",
        f"{BASE_URL}/collections/featured",
        f"{BASE_URL}/collections/new-arrivals",
        f"{BASE_URL}/collections/best-sellers",
        f"{BASE_URL}/collections"
    ]
    
    results = []
    for url in collection_urls:
        logging.info(f"Checking collection URL: {url}")
        html_content = get_page_content(url)
        if html_content:
            logging.info(f"Successfully accessed collection: {url}")
            save_debug_html(html_content, f"collection_{url.split('/')[-1]}")
            
            # Save a snippet to the feeds directory
            html_snippet = html_content[:1000] if len(html_content) > 1000 else html_content
            save_debug_info_to_feeds(
                f"Collection URL: {url}\nHTML Snippet:\n{html_snippet}",
                f"collection_{url.split('/')[-1]}_snippet.txt"
            )
            
            results.append((url, html_content))
    
    if results:
        return results[0]  # Return the first successful URL
    return None, None

def check_common_ecommerce_patterns():
    """Check other common e-commerce URL patterns"""
    patterns = [
        f"{BASE_URL}/shop",
        f"{BASE_URL}/store",
        f"{BASE_URL}/catalog",
        f"{BASE_URL}/category/all",
        f"{BASE_URL}/category",
        f"{BASE_URL}/product-category"
    ]
    
    for url in patterns:
        logging.info(f"Checking URL pattern: {url}")
        html_content = get_page_content(url)
        if html_content:
            logging.info(f"Successfully accessed: {url}")
            # Save a snippet to the feeds directory
            html_snippet = html_content[:1000] if len(html_content) > 1000 else html_content
            save_debug_info_to_feeds(
                f"URL: {url}\nHTML Snippet:\n{html_snippet}",
                f"pattern_{url.split('/')[-1]}_snippet.txt"
            )
            return url, html_content
    
    return None, None

def main():
    logging.info("Starting crawler for JoyAndCo products")
    
    # Create debug info summary file
    debug_summary = ["JoyAndCo Crawler Debug Summary\n"]
    debug_summary.append(f"Base URL: {BASE_URL}")
    debug_summary.append(f"Product List URL: {PRODUCT_LIST_URL}")
    debug_summary.append("\nAttempted URLs:")
    
    # First check if we can access the main products page
    debug_summary.append(f"- {PRODUCT_LIST_URL}")
    product_list_html = get_page_content(PRODUCT_LIST_URL)
    
    # Track the URL we're using
    current_url = PRODUCT_LIST_URL
    
    # If main products page succeeds, but might not have products
    if product_list_html:
        debug_summary.append(f"  ✓ Successful access")
        # Get the page title to see what we're looking at
        soup = BeautifulSoup(product_list_html, 'html.parser')
        page_title = soup.title.text if soup.title else "No title found"
        debug_summary.append(f"  Page title: {page_title}")
    else:
        debug_summary.append(f"  ✗ Failed to access")
        logging.error("Failed to fetch product listing page")
        
        # Check Shopify collections
        logging.info("Checking if site uses Shopify collections structure")
        collection_url, collection_html = check_shopify_collections()
        
        if collection_html:
            debug_summary.append(f"- {collection_url}")
            debug_summary.append(f"  ✓ Successful access (using as product listing)")
            
            # Get the page title
            soup = BeautifulSoup(collection_html, 'html.parser')
            page_title = soup.title.text if soup.title else "No title found"
            debug_summary.append(f"  Page title: {page_title}")
            
            logging.info(f"Using collection page: {collection_url}")
            product_list_html = collection_html
            current_url = collection_url
        else:
            debug_summary.append("- No Shopify collections found")
            
            # Check other common e-commerce patterns
            logging.info("Checking other common e-commerce URL patterns")
            pattern_url, pattern_html = check_common_ecommerce_patterns()
            
            if pattern_html:
                debug_summary.append(f"- {pattern_url}")
                debug_summary.append(f"  ✓ Successful access (using as product listing)")
                
                # Get the page title
                soup = BeautifulSoup(pattern_html, 'html.parser')
                page_title = soup.title.text if soup.title else "No title found"
                debug_summary.append(f"  Page title: {page_title}")
                
                logging.info(f"Using pattern page: {pattern_url}")
                product_list_html = pattern_html
                current_url = pattern_url
            else:
                debug_summary.append("- No common e-commerce patterns found")
                debug_summary.append("\nCONCLUSION: Could not find any valid product listing pages")
                save_debug_info_to_feeds("\n".join(debug_summary), "debug_summary.txt")
                logging.error("Could not find any valid product listing pages")
                
                # Create empty feed files to avoid errors
                os.makedirs('feeds', exist_ok=True)
                with open('feeds/google_shopping_feed.csv', 'w', encoding='utf-8') as f:
                    f.write("id,title,description,link,image_link,price,currency,availability,condition,brand\n")
                
                with open('feeds/google_shopping_feed.xml', 'w', encoding='utf-8') as f:
                    f.write('<?xml version="1.0" encoding="utf-8"?>\n<rss version="2.0" xmlns:g="http://base.google.com/ns/1.0">\n<channel>\n<title>Joy and Co Product Feed</title>\n<link>https://joyandco.com</link>\n<description>Product feed for Google Shopping</description>\n</channel>\n</rss>')
                
                with open('feeds/meta_shopping_feed.xml', 'w', encoding='utf-8') as f:
                    f.write('<?xml version="1.0" encoding="utf-8"?>\n<feed>\n</feed>')
                
                logging.info("Created empty feed files")
                return
    
    # Handle pagination if needed
    all_products_html = handle_pagination(product_list_html)
    
    # Extract product links
    product_links = extract_product_links(all_products_html)
    debug_summary.append(f"\nProduct links found: {len(product_links)}")
    
    if not product_links:
        debug_summary.append("No product links found on the page")
        debug_summary.append("Trying direct product URLs for inspection")
        
        # Try some common URL patterns
        direct_product_attempts = []
        direct_product_urls = [
            f"{BASE_URL}/products/example-product",
            f"{BASE_URL}/product/example-product",
            f"{BASE_URL}/collections/all/products/example-product",
            f"{BASE_URL}/shop/example-product"
        ]
        
        for url in direct_product_urls:
            logging.info(f"Trying direct product URL: {url}")
            direct_product_attempts.append(f"- {url}")
            html = get_page_content(url)
            if html:
                direct_product_attempts.append(f"  ✓ Successful access")
                soup = BeautifulSoup(html, 'html.parser')
                page_title = soup.title.text if soup.title else "No title found"
                direct_product_attempts.append(f"  Page title: {page_title}")
                
                # This is just for inspection, not actually using these URLs
                save_debug_html(html, f"direct_product_{url.split('/')[-1]}")
                html_snippet = html[:1000] if len(html) > 1000 else html
                save_debug_info_to_feeds(
                    f"URL: {url}\nHTML Snippet:\n{html_snippet}",
                    f"direct_product_{url.split('/')[-1]}_snippet.txt"
                )
            else:
                direct_product_attempts.append(f"  ✗ Failed to access")
        
        debug_summary.append("\nDirect product URL tests:")
        debug_summary.extend(direct_product_attempts)
        
        # Fallback to a very limited set of product URLs to avoid too many 404s
        fallback_links = []
        # Try just a few patterns to check URL structure
        fallback_links.append(f"{BASE_URL}/products/product-1")
        fallback_links.append(f"{BASE_URL}/collections/all/products/product-1")
        
        product_links = fallback_links
        debug_summary.append("\nFallback to a limited set of product URLs:")
        for link in fallback_links:
            debug_summary.append(f"- {link}")
    else:
        # List a few of the found links in debug
        debug_summary.append("\nSample of found product links:")
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
                product_attempts.append(f"  ✗ Failed to extract product data (missing title or price)")
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
