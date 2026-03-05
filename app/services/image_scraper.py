import os
import re
import json
import aiofiles
import requests
import random
import asyncio
from PIL import Image
from io import BytesIO
from urllib.parse import urlparse
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

    def _match_keyword(self, *texts):
        combined = " ".join((text or "").lower() for text in texts)
        for keyword in Config.KEYWORDS:
            keyword_lower = keyword.lower()
            variants = {
                keyword_lower,
                keyword_lower.replace(" ", "-"),
                keyword_lower.replace(" ", "_"),
            }
            if any(variant in combined for variant in variants):
                return keyword
        return None

    def _keyword_dir_name(self, keyword: str) -> str:
        sanitized = re.sub(r"[^a-z0-9_-]+", "_", keyword.lower()).strip("_")
        return sanitized or "misc"

    def _build_image_basename(self, img_url: str) -> tuple[str, str]:
        path_name = os.path.basename(urlparse(img_url).path) or "image"
        stem, ext = os.path.splitext(path_name)
        safe_stem = re.sub(r"[^A-Za-z0-9_-]+", "_", stem).strip("_") or "image"
        ext = ext.lower() if ext.lower() in {".jpg", ".jpeg", ".png", ".webp"} else ".jpg"
        return f"{random.randint(1000, 9999)}_{safe_stem}", ext

    async def _extract_page_metadata(self, page: Page) -> tuple[str, str]:
        page_title = await page.title()
        page_description = ""

        desc_el = await page.query_selector("meta[name='description']")
        if desc_el:
            page_description = (await desc_el.get_attribute("content")) or ""

        if not page_description:
            og_desc_el = await page.query_selector("meta[property='og:description']")
            if og_desc_el:
                page_description = (await og_desc_el.get_attribute("content")) or ""

        return page_title or "", page_description

    async def scrape_images_from_url(self, page: Page, url: str):
        # Stop check 1: Don't open page if limit reached
        if ImageScraper.total_saved_count >= Config.MAX_TOTAL_IMAGES:
            return

        print(f"Scraping images from: {url}")

        try:
            await asyncio.sleep(random.uniform(1, 2))  # Throttling

            # Go to page
            await page.goto(url, wait_until="domcontentloaded", timeout=40000)
            page_title, page_description = await self._extract_page_metadata(page)

            # Extract images
            img_elements = await page.query_selector_all("img")

            for img in img_elements:
                # Stop check 2: Stop processing images inside the loop
                if ImageScraper.total_saved_count >= Config.MAX_TOTAL_IMAGES:
                    print("Target reached. Stopping download.")
                    break

                src = await img.get_attribute("src")
                if not src:
                    continue

                if not src.startswith("http"):
                    src = requests.compat.urljoin(url, src)

                await self._download_and_save(
                    img_url=src,
                    source_url=url,
                    page_title=page_title,
                    page_description=page_description,
                )

        except Exception as e:
            print(f"Error on {url}: {e}")

    async def _download_and_save(
        self,
        img_url: str,
        source_url: str,
        page_title: str,
        page_description: str,
    ):
        try:
            # Stop check 3: Final check before saving
            if ImageScraper.total_saved_count >= Config.MAX_TOTAL_IMAGES:
                return

            response = requests.get(img_url, headers=self.get_random_headers(), timeout=5)
            if response.status_code != 200:
                return

            image_data = BytesIO(response.content)
            img = Image.open(image_data)
            width, height = img.size
            if width < Config.MIN_WIDTH or height < Config.MIN_HEIGHT:
                return

            keyword = self._match_keyword(source_url, page_title, page_description, img_url)
            if not keyword:
                return

            save_dir = os.path.join(Config.DATASET_DIR, self._keyword_dir_name(keyword))
            os.makedirs(save_dir, exist_ok=True)

            basename, ext = self._build_image_basename(img_url)
            image_filename = f"{basename}{ext}"
            metadata_filename = f"{basename}.json"
            image_path = os.path.join(save_dir, image_filename)
            metadata_path = os.path.join(save_dir, metadata_filename)

            async with aiofiles.open(image_path, mode="wb") as f:
                await f.write(response.content)

            metadata = {
                "keyword": keyword,
                "source_url": source_url,
                "page_title": page_title,
                "page_description": page_description,
                "image_url": img_url,
            }
            async with aiofiles.open(metadata_path, mode="w", encoding="utf-8") as f:
                await f.write(json.dumps(metadata, indent=2))

            ImageScraper.total_saved_count += 1
            print(
                f"[{ImageScraper.total_saved_count}/{Config.MAX_TOTAL_IMAGES}] "
                f"Saved: {image_filename} + {metadata_filename}"
            )
        except Exception:
            pass
