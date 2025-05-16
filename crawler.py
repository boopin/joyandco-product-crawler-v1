import asyncio
from playwright.async_api import async_playwright
import csv
import xml.etree.ElementTree as ET
from datetime import datetime
import os
import re

BASE_URL = "https://joyandco.com"
PRODUCT_LIST_URL = f"{BASE_URL}/product/"

async def main():
    async with async_playwright() as p:
        # Launch browser
        browser = await p.chromium.launch()
        page = await browser.new_page()
        
        # Navigate to products page
        await page.goto(PRODUCT_LIST_URL)
        
        # Click "view more" until all products are loaded
        while True:
            try:
                # Wait a moment for any dynamic content to load
                await page.wait_for_timeout(2000)
                view_more_button = await page.query_selector("button.view-more, a.view-more")
                if not view_more_button:
                    break
                await view_more_button.click()
                # Wait for new products to load
                await page.wait_for_timeout(3000)
            except Exception as e:
                print(f"No more 'view more' buttons found or error: {e}")
                break
        
        # Extract all product links
        product_links = await page.evaluate('''
            () => {
                const links = Array.from(document.querySelectorAll('.product-card a, .product-item a'));
                return links.filter(link => link.href.includes('/product/')).map(link => link.href);
            }
        ''')
        
        # Remove duplicates
        product_links = list(set(product_links))
        print(f"Found {len(product_links)} unique product links")
        
        products = []
        
        # Visit each product page and extract details
        for link in product_links:
            try:
                await page.goto(link)
                await page.wait_for_selector('.product-details', { timeout: 5000 })
                
                # Extract product data
                product_data = await page.evaluate('''
                    () => {
                        // Try different selectors to find product info
                        const title = document.querySelector('h1.product-title')?.innerText || 
                                    document.querySelector('.product-details h1')?.innerText;
                        
                        const priceText = document.querySelector('.product-price')?.innerText || 
                                        document.querySelector('.price')?.innerText || '';
                        const price = priceText.replace(/[^0-9.]/g, '');
                        
                        const description = document.querySelector('.product-description')?.innerText || 
                                          document.querySelector('.description')?.innerText;
                        
                        const imageEl = document.querySelector('.product-image img') || 
                                      document.querySelector('.product-gallery img');
                        
                        // Generate a unique ID if none exists
                        const id = document.querySelector('[data-product-id]')?.getAttribute('data-product-id') || 
                                 window.location.pathname.split('/').pop();
                        
                        const stockElement = document.querySelector('.stock-status, .availability');
                        const inStock = stockElement ? 
                            !stockElement.innerText.toLowerCase().includes('out of stock') : true;
                        
                        return {
                            id: id,
                            title: title,
                            description: description,
                            price: price,
                            currency: 'AED', // Dubai currency
                            image_link: imageEl ? (imageEl.src.startsWith('http') ? imageEl.src : window.location.origin + imageEl.src) : '',
                            availability: inStock ? 'in stock' : 'out of stock',
                            condition: 'new',
                            link: window.location.href,
                            brand: document.querySelector('.brand')?.innerText || 'Joy and Co'
                        };
                    }
                ''')
                
                # Only add products with valid data
                if product_data['title'] and product_data['price']:
                    products.append(product_data)
                    print(f"Extracted data for: {product_data['title']}")
                else:
                    print(f"Skipping product at {link} due to missing critical data")
            except Exception as e:
                print(f"Error processing {link}: {e}")
        
        await browser.close()
        
        # Generate feeds
        if products:
            generate_csv_feed(products)
            generate_xml_feed(products)
            print(f"Successfully generated product feeds for {len(products)} products")
        else:
            print("No products found to generate feeds")

def generate_csv_feed(products):
    # Ensure output directory exists
    os.makedirs('feeds', exist_ok=True)
    
    with open('feeds/google_shopping_feed.csv', 'w', newline='', encoding='utf-8') as csvfile:
        fieldnames = ['id', 'title', 'description', 'link', 'image_link', 'price', 'currency', 'availability', 'condition', 'brand']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        
        writer.writeheader()
        for product in products:
            writer.writerow(product)

def generate_xml_feed(products):
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
    os.makedirs('feeds', exist_ok=True)
    tree.write('feeds/google_shopping_feed.xml', encoding='utf-8', xml_declaration=True)
    
    # Create a separate XML feed for Meta shopping ads
    generate_meta_xml_feed(products)

def generate_meta_xml_feed(products):
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
    os.makedirs('feeds', exist_ok=True)
    tree.write('feeds/meta_shopping_feed.xml', encoding='utf-8', xml_declaration=True)

if __name__ == "__main__":
    asyncio.run(main())
