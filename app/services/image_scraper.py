import os
import aiofiles
import requests
import random
import asyncio
from PIL import Image
from io import BytesIO
from fake_useragent import UserAgent
from playwright.async_api import Page
from app.config import Config

class ImageScraper:
    # Global counter shared across the app
    total_saved_count = 0 

    def __init__(self):
        self.ua = UserAgent()

    def get_random_headers(self):
        return {
            "User-Agent": self.ua.random,
            "Accept-Language": "en-US,en;q=0.9",
        }

    async def scrape_images_from_url(self, page: Page, url: str):
        # 🛑 STOP CHECK 1: Don't open page if limit reached
        if ImageScraper.total_saved_count >= Config.MAX_TOTAL_IMAGES:
            return

        print(f"📸 Scraping images from: {url}")
        
        try:
            await asyncio.sleep(random.uniform(1, 2)) # Throttling
            
            # Go to page
            await page.goto(url, wait_until="domcontentloaded", timeout=40000)
            
            # Extract images
            img_elements = await page.query_selector_all("img")
            
            for img in img_elements:
                # 🛑 STOP CHECK 2: Stop processing images inside the loop
                if ImageScraper.total_saved_count >= Config.MAX_TOTAL_IMAGES:
                    print("✅ Target reached (120 images). Stopping download.")
                    break

                src = await img.get_attribute("src")
                if not src: continue
                
                if not src.startswith("http"):
                    src = requests.compat.urljoin(url, src)

                await self._download_and_save(src, url)

        except Exception as e:
            print(f"❌ Error on {url}: {e}")

    async def _download_and_save(self, img_url: str, source_url: str):
        try:
            # 🛑 STOP CHECK 3: Final check before saving
            if ImageScraper.total_saved_count >= Config.MAX_TOTAL_IMAGES:
                return

            response = requests.get(img_url, headers=self.get_random_headers(), timeout=5)
            if response.status_code != 200: return

            image_data = BytesIO(response.content)
            img = Image.open(image_data)
            
            width, height = img.size
            if width >= Config.MIN_WIDTH and height >= Config.MIN_HEIGHT:
                
                # Identify Category
                category = "misc"
                for keyword in Config.KEYWORDS:
                    if keyword in source_url.lower():
                        category = keyword
                        break
                
                # Save
                save_dir = f"data/{category}"
                os.makedirs(save_dir, exist_ok=True)
                
                filename = f"{random.randint(1000,9999)}_{img_url.split('/')[-1].split('?')[0]}"
                if not filename.endswith(('.jpg', '.png', '.jpeg')): filename += ".jpg"
                
                save_path = os.path.join(save_dir, filename)
                
                async with aiofiles.open(save_path, mode='wb') as f:
                    await f.write(response.content)
                
                # ✅ Increment Counter
                ImageScraper.total_saved_count += 1
                print(f"✅ [{ImageScraper.total_saved_count}/{Config.MAX_TOTAL_IMAGES}] Saved: {filename}")
                
        except Exception:
            pass