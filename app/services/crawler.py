import asyncio
import sys
from urllib.parse import urlparse

from playwright.async_api import async_playwright

from app.config import Config
from app.services.image_scraper import ImageScraper
from app.services.llm_filter import LLMService

class CrawlerService:
    def __init__(self):
        self.visited = set()
        self.found_links = set()
        self.llm_service = LLMService()
        self.image_scraper = ImageScraper()

    # ... keep is_valid_internal_link function exactly as before ...
    def is_valid_internal_link(self, base_domain, url):
        parsed = urlparse(url)
        return (
            parsed.netloc == base_domain and
            url not in self.visited and
            not any(ext in url for ext in ['.pdf', '.zip', '.css', '.js'])
        )

    async def start_crawl(self, seed_urls: list[str]):
        """
        Playwright needs subprocess support.
        On Windows, Uvicorn can run a Selector loop where subprocess APIs are not implemented.
        If that loop is detected, run the crawl in a dedicated Proactor loop in a worker thread.
        """
        try:
            running_loop = asyncio.get_running_loop()

            if sys.platform == "win32" and isinstance(running_loop, asyncio.SelectorEventLoop):
                await asyncio.to_thread(self._run_with_proactor_loop, seed_urls)
                return

            await self._start_crawl(seed_urls)
        except Exception as exc:
            print(f"CRAWL ERROR: {exc}")

    def _run_with_proactor_loop(self, seed_urls: list[str]) -> None:
        policy = asyncio.WindowsProactorEventLoopPolicy()
        loop = policy.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._start_crawl(seed_urls))
            loop.run_until_complete(loop.shutdown_asyncgens())
        finally:
            loop.close()
            asyncio.set_event_loop(None)

    async def _start_crawl(self, seed_urls: list[str]):
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()

            # 1. Collect Links (DFS)
            for seed in seed_urls:
                domain = urlparse(seed).netloc
                await self._dfs_traverse(page, seed, domain)

            print(f"\n🔍 Found {len(self.found_links)} potential links.")
            print(f"🎯 Target: {Config.MAX_TOTAL_IMAGES} images.")

            # 2. Filter & Scrape (Batch Processing)
            all_links = list(self.found_links)
            
            # Process in chunks of 10 to check image count frequently
            for i in range(0, len(all_links), Config.BATCH_SIZE_LLM):
                
                # 🛑 CRITICAL CHECK: Stop asking Gemini if we have 120 images
                if ImageScraper.total_saved_count >= Config.MAX_TOTAL_IMAGES:
                    print("🎉 Reached 120 images limit! Stopping crawler.")
                    break

                batch = all_links[i : i + Config.BATCH_SIZE_LLM]
                
                print(f"🤖 Asking Gemini to filter batch {i}...")
                relevant_links = await self.llm_service.filter_urls_batch(batch)
                
                # Scrape this batch
                for url in relevant_links:
                    if ImageScraper.total_saved_count >= Config.MAX_TOTAL_IMAGES:
                        break
                    await self.image_scraper.scrape_images_from_url(page, url)
                
                # Sleep to respect Gemini Rate Limit
                await asyncio.sleep(4)

            await browser.close()

    async def _dfs_traverse(self, page, url, domain):
        # Stop traversing if we gathered enough initial links (Speed up)
        if len(self.found_links) > 200: 
            return

        if url in self.visited: return
        self.visited.add(url)
        
        try:
            await page.goto(url, timeout=10000, wait_until="domcontentloaded")
            hrefs = await page.eval_on_selector_all("a", "elements => elements.map(el => el.href)")
            
            for link in hrefs:
                if self.is_valid_internal_link(domain, link):
                    self.found_links.add(link)
                    # Recursion
                    await self._dfs_traverse(page, link, domain)
        except:
            pass
