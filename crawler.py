import asyncio
from playwright.async_api import async_playwright
import csv
import xml.etree.ElementTree as ET
from datetime import datetime
import os
import re
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

BASE_URL = "https://joyandco.com"
PRODUCT_LIST_URL = f"{BASE_URL}/product/"

async def save_page_screenshot(page, filename):
    """Save a screenshot for debugging"""
    os.makedirs('debug', exist_ok=True)
    await page.screenshot(path=f'debug/{filename}.png', full_page=True)

async def main():
    logging.info("Starting crawler for JoyAndCo products")
    
    async with async_playwright() as p:
        # Launch browser with more verbose options
        browser = await p.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-dev-shm-usage']
        )
        
        context = await browser.new_context(
            viewport={'width': 1280, 'height': 800},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        )
        
        page = await context.new_page()
        page.set_default_timeout(30000)  # 30 seconds timeout
        
        # Navigate to products page with robust error handling
        try:
            logging.info(f"Navigating to product list: {PRODUCT_LIST_URL}")
            response = await page.goto(PRODUCT_LIST_URL, wait_until="networkidle")
            
            if not response.ok:
                logging.error(f"Failed to load page: {response.status} {response.status_text}")
                await save_page_screenshot(page, "error_page_load")
            else:
                logging.info(f"Successfully loaded product list page")
                await save_page_screenshot(page, "product_list_initial")
        except Exception as e:
            logging.error(f"Error loading product page: {e}")
            await save_page_screenshot(page, "exception_page_load")
            # Continue anyway to see if we can recover
        
        # Get the page HTML for debugging
        page_content = await page.content()
        logging.info(f"Page content length: {len(page_content)} characters")
        if len(page_content) < 1000:
            logging.warning("Page content seems too short, might indicate a problem")
            logging.info(f"Page content: {page_content[:500]}...")
        
        # Click "view more" until all products are loaded
        view_more_clicks = 0
        max_clicks = 10  # Prevent infinite loops
        
        while view_more_clicks < max_clicks:
            try:
                # Wait a moment for any dynamic content to load
                await page.wait_for_timeout(2000)
                
                # Try multiple selector patterns for the view more button
                view_more_button = await page.query_selector(
                    "button.view-more, a.view-more, .load-more, #load-more, button:has-text('View More'), a:has-text('View More'), button:has-text('Load More')"
                )
                
                if not view_more_button:
                    logging.info(f"No more 'view more' buttons found after {view_more_clicks} clicks")
                    break
                
                # Check if the button is visible
                is_visible = await view_more_button.is_visible()
                if not is_visible:
                    logging.info("View more button exists but is not visible")
                    break
                
                logging.info(f"Clicking 'view more' button (click #{view_more_clicks + 1})")
                await view_more_button.click()
                view_more_clicks += 1
                
                # Wait for new products to load
                await page.wait_for_timeout(3000)
                await save_page_screenshot(page, f"after_view_more_click_{view_more_clicks}")
                
            except Exception as e:
                logging.error(f"Error clicking 'view more' button: {e}")
                await save_page_screenshot(page, f"view_more_error_{view_more_clicks}")
                break
        
        # Extract all product links with enhanced selectors
        logging.info("Extracting product links")
        product_links = await page.evaluate('''
            () => {
                // Try multiple selector patterns to find product links
                let links = [];
                
                // Pattern 1: Common product card pattern
                const productCardLinks = Array.from(document.querySelectorAll('.product-card a, .product-item a, .product a, .product-box a, .item a'));
                if (productCardLinks.length > 0) {
                    links = [...links, ...productCardLinks];
                }
                
                // Pattern 2: Generic product links
                const allLinks = Array.from(document.querySelectorAll('a[href*="/product/"]'));
                if (allLinks.length > 0) {
                    links = [...links, ...allLinks];
                }
                
                // Pattern 3: Image links inside product containers
                const imageLinks = Array.from(document.querySelectorAll('.product img, .product-item img')).map(img => img.closest('a'));
                if (imageLinks.length > 0) {
                    links = [...links, ...imageLinks.filter(link => link !== null)];
                }
                
                // Log what we found to console for debugging
                console.log('Found product links with these patterns:', {
                    'product-card links': productCardLinks.length,
                    'href-contains-product links': allLinks.length,
                    'image links': imageLinks.filter(link => link !== null).length
                });
                
                // Filter and deduplicate
                return [...new Set(links.filter(link => link && link.href && link.href.includes('/product/')).map(link => link.href))];
            }
        ''')
        
        # Remove duplicates
        product_links = list(set(product_links))
        logging.info(f"Found {len(product_links)} unique product links")
        
        # If no product links found, try a different approach
        if not product_links:
            logging.warning("No product links found with primary selectors, trying fallback approach")
            # Get all links on the page and filter for likely product links
            all_links = await page.evaluate('''
                () => {
                    return Array.from(document.querySelectorAll('a[href]'))
                        .map(a => a.href)
                        .filter(href => 
                            href.includes('/product/') || 
                            href.includes('/item/') || 
                            href.includes('/p/') ||
                            href.match(/\/[a-z0-9-]+\.html$/) ||
                            href.match(/\/[a-z0-9-]+\/$/)
                        );
                }
            ''')
            product_links = list(set(all_links))
            logging.info(f"Fallback approach found {len(product_links)} potential product links")
        
        # Save product links for debugging
        os.makedirs('debug', exist_ok=True)
        with open('debug/product_links.txt', 'w') as f:
            for link in product_links:
                f.write(f"{link}\n")
        
        products = []
        
        # Visit each product page and extract details
        for index, link in enumerate(product_links):
            try:
                logging.info(f"Processing product {index+1}/{len(product_links)}: {link}")
                
                # Navigate to the product page
                await page.goto(link, wait_until="networkidle")
                await save_page_screenshot(page, f"product_{index}_page")
                
                # Try different selectors for product details
                product_data = await page.evaluate('''
                    () => {
                        // Helper function to get text content safely
                        const getText = (selector) => {
                            const el = document.querySelector(selector);
                            return el ? el.innerText.trim() : '';
                        };
                        
                        // Try different selectors to find product info
                        const titleSelectors = [
                            'h1.product-title', '.product-details h1', '.product-name', 
                            '.product-title', '.product h1', 'h1', '.title'
                        ];
                        
                        const priceSelectors = [
                            '.product-price', '.price', '.product-info .price', 
                            '[itemprop="price"]', '.amount', '.current-price'
                        ];
                        
                        const descriptionSelectors = [
                            '.product-description', '.description', '[itemprop="description"]',
                            '.product-short-description', '.details', '.product-details'
                        ];
                        
                        const imageSelectors = [
                            '.product-image img', '.product-gallery img', 
                            '.product-photo img', '[itemprop="image"]',
                            '.gallery img', '.carousel img', '.product img'
                        ];
                        
                        // Find the first matching selector
                        const findText = (selectors) => {
                            for (const selector of selectors) {
                                const text = getText(selector);
                                if (text) return text;
                            }
                            return '';
                        };
                        
                        // Find the first matching image
                        const findImage = (selectors) => {
                            for (const selector of selectors) {
                                const img = document.querySelector(selector);
                                if (img && img.src) return img.src;
                            }
                            return '';
                        };
                        
                        // Get product details
                        const title = findText(titleSelectors);
                        const priceText = findText(priceSelectors);
                        const description = findText(descriptionSelectors);
                        const imageUrl = findImage(imageSelectors);
                        
                        // Clean price text
                        const price = priceText.replace(/[^0-9.]/g, '');
                        
                        // Generate a unique ID
                        const id = document.querySelector('[data-product-id]')?.getAttribute('data-product-id') || 
                                window.location.pathname.split('/').pop().replace(/\.[^/.]+$/, "");  // Remove file extension
                        
                        // Check stock status
                        const stockTexts = ['in stock', 'out of stock', 'available', 'unavailable', 'sold out'];
                        let stockStatus = '';
                        
                        for (const text of stockTexts) {
                            const regex = new RegExp(text, 'i');
                            if (document.body.innerText.match(regex)) {
                                stockStatus = text.toLowerCase();
                                break;
                            }
                        }
                        
                        // Default to in stock if no status found
                        const availability = stockStatus.includes('out') || 
                                          stockStatus.includes('unavailable') || 
                                          stockStatus.includes('sold') 
                                          ? 'out of stock' : 'in stock';
                        
                        // Extract brand info
                        const brandSelectors = ['.brand', '[itemprop="brand"]', '.manufacturer'];
                        const brand = findText(brandSelectors) || 'Joy and Co';
                        
                        // For debugging
                        const debugInfo = {
                            foundTitle: !!title,
                            foundPrice: !!price,
                            foundDescription: !!description,
                            foundImage: !!imageUrl,
                            titleSelector: titleSelectors.find(s => document.querySelector(s)),
                            priceSelector: priceSelectors.find(s => document.querySelector(s)),
                            descSelector: descriptionSelectors.find(s => document.querySelector(s)),
                            imageSelector: imageSelectors.find(s => document.querySelector(s))
                        };
                        
                        console.log('Product data debug:', debugInfo);
                        
                        return {
                            id: id,
                            title: title,
                            description: description,
                            price: price,
                            currency: 'AED', // Dubai currency
                            image_link: imageUrl ? (imageUrl.startsWith('http') ? imageUrl : window.location.origin + imageUrl) : '',
                            availability: availability,
                            condition: 'new',
                            link: window.location.href,
                            brand: brand,
                            debug: debugInfo
                        };
                    }
                ''')
                
                # Log the debug info
                if 'debug' in product_data:
                    debug_info = product_data.pop('debug')
                    logging.info(f"Product debug info: {debug_info}")
                
                # Only add products with valid data
                if product_data['title'] and product_data['price']:
                    products.append(product_data)
                    logging.info(f"Extracted data for: {product_data['title']}")
                else:
                    logging.warning(f"Skipping product at {link} due to missing critical data")
                    logging.info(f"Partial data: {product_data}")
            except Exception as e:
                logging.error(f"Error processing {link}: {e}")
                await save_page_screenshot(page, f"product_{index}_error")
        
        await browser.close()
        
        # Generate feeds
        if products:
            generate_csv_feed(products)
            generate_xml_feed(products)
            logging.info(f"Successfully generated product feeds for {len(products)} products")
        else:
            logging.warning("No products found to generate feeds")

def generate_csv_feed(products):
    # Ensure output directory exists
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
    # Ensure output directory exists
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

if __name__ == "__main__":
    asyncio.run(main())
