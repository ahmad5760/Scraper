import sys
import asyncio
from fastapi import FastAPI, BackgroundTasks
from app.services.crawler import CrawlerService
from app.schemas import CrawlRequest

# 👇 ADD THIS BLOCK TO FIX THE WINDOWS ERROR 👇
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
# 👆 END OF FIX 👆

app = FastAPI(title="Fashion AI Data Scraper")

@app.post("/start-crawl")
async def start_crawl(request: CrawlRequest, background_tasks: BackgroundTasks):
    crawler = CrawlerService()
    background_tasks.add_task(crawler.start_crawl, request.seed_urls)
    
    return {
        "message": "Crawl started successfully", 
        "urls_submitted": len(request.seed_urls)
    }

@app.get("/")
def home():
    return {"status": "Running", "docs_url": "http://127.0.0.1:8000/docs"}