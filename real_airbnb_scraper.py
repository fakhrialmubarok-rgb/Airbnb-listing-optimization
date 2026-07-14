#!/usr/bin/env python3
"""
REAL AIRBNB SCRAPER - Extract actual property data and photos
Uses Playwright for JavaScript rendering
"""

import asyncio
import json
import re
from pathlib import Path
from playwright.async_api import async_playwright
import urllib.request
from datetime import datetime

async def scrape_airbnb_listing(listing_url):
    """Scrape real Airbnb listing data and download photos"""
    
    print(f"\n🔍 REAL SCRAPE: {listing_url}\n")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        
        print("📄 Loading page...")
        await page.goto(listing_url, wait_until="networkidle", timeout=30000)
        
        # Extract listing ID
        listing_id = listing_url.split('/rooms/')[1].split('?')[0] if '/rooms/' in listing_url else 'unknown'
        print(f"✅ Listing ID: {listing_id}")
        
        # Get page HTML
        print("📊 Extracting data...", end="")
        
        # Extract from JavaScript-rendered content
        data = await page.evaluate("""() => {
            const data = {};
            
            // Extract title
            const titleEl = document.querySelector('h1');
            data.title = titleEl ? titleEl.textContent : 'Unknown';
            
            // Extract price
            const priceMatch = document.documentElement.outerHTML.match(/\\$(\\d+)/);
            data.price = priceMatch ? priceMatch[1] : 'Unknown';
            
            // Extract rating
            const ratingEl = document.querySelector('[role="img"][aria-label*="rating"], [aria-label*="rating"]');
            data.rating = ratingEl ? ratingEl.getAttribute('aria-label') : 'Unknown';
            
            // Extract amenities
            const amenities = [];
            document.querySelectorAll('[data-testid="amenities"]').forEach(el => {
                amenities.push(el.textContent.trim());
            });
            data.amenities = amenities.slice(0, 15);
            
            // Extract description
            const descEl = document.querySelector('[data-testid="pdp-description"]');
            data.description = descEl ? descEl.textContent.trim() : 'No description';
            
            // Extract location
            const locEl = document.querySelector('[data-testid="address"]');
            data.location = locEl ? locEl.textContent : 'Unknown';
            
            // Extract images
            const images = [];
            document.querySelectorAll('img[src*="airbnb"]').forEach(img => {
                if (img.src && img.src.includes('muscdn.com')) {
                    images.push(img.src);
                }
            });
            data.images = [...new Set(images)].slice(0, 5);
            
            return data;
        }""")
        
        print(" ✅")
        print(f"   Title: {data.get('title', 'N/A')}")
        print(f"   Price: ${data.get('price', 'N/A')}/night")
        print(f"   Rating: {data.get('rating', 'N/A')}")
        print(f"   Amenities: {len(data.get('amenities', []))} found")
        print(f"   Images: {len(data.get('images', []))} found")
        
        # Download images
        print("\n📸 Downloading images...")
        downloaded_images = []
        
        for i, img_url in enumerate(data.get('images', [])[:5], 1):
            if img_url:
                try:
                    # Clean URL
                    img_url = img_url.split('?')[0] + '?w=800&h=600'
                    filename = f'/tmp/property_actual_{listing_id}_{i}.jpg'
                    
                    urllib.request.urlretrieve(img_url, filename)
                    print(f"   ✅ Downloaded image {i}: {Path(filename).stat().st_size / 1024:.0f} KB")
                    downloaded_images.append(filename)
                except Exception as e:
                    print(f"   ⚠️  Image {i} failed: {e}")
        
        data['downloaded_images'] = downloaded_images
        
        await browser.close()
        
        return listing_id, data

async def main():
    listing_url = "https://www.airbnb.com/rooms/1666803211367302582?unique_share_id=558842bc-b9a9-482a-a9b0-daa619444b72&viralityEntryPoint=1&s=76"
    
    try:
        listing_id, data = await scrape_airbnb_listing(listing_url)
        
        # Save data
        print("\n💾 Saving data...")
        
        with open(f'/tmp/airbnb_listing_{listing_id}.json', 'w') as f:
            json.dump(data, f, indent=2)
        
        print(f"✅ Saved to: /tmp/airbnb_listing_{listing_id}.json")
        
        print("\n" + "="*80)
        print("EXTRACTED DATA SUMMARY")
        print("="*80)
        print(json.dumps({
            'title': data.get('title'),
            'price': data.get('price'),
            'rating': data.get('rating'),
            'amenities_count': len(data.get('amenities', [])),
            'images_downloaded': len(data.get('downloaded_images', [])),
            'description_length': len(data.get('description', ''))
        }, indent=2))
        
        return listing_id, data
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
