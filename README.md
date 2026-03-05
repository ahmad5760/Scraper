# Fashion AI Data Scraper

FastAPI service that crawls e-commerce websites, filters likely product URLs with Gemini, and downloads product images for dataset building.

## Features

- Crawl internal links from one or more seed URLs (DFS traversal).
- Filter candidate links with Gemini (`google-generativeai`) in batches.
- Fallback to local keyword-based filtering when Gemini fails.
- Download images with size constraints into keyword-based folders.
- Save per-image sidecar metadata (`.json`) with source/page details.
- Stop automatically after reaching a max image limit.

## Project Structure

```text
app/
  main.py                  # FastAPI app and routes
  config.py                # Env + crawler settings
  schemas.py               # Request schema
  services/
    crawler.py             # Crawl flow (collect -> filter -> scrape)
    llm_filter.py          # Gemini + fallback URL filtering
    image_scraper.py       # Image download and save logic
dataset/                   # Downloaded images + metadata (generated at runtime)
requirements.txt
```

## Requirements

- Python 3.10+
- Playwright browser binaries
- Gemini API key 

## Setup

1. Create and activate a virtual environment.
2. Install dependencies.
3. Install Playwright Chromium.
4. Add environment variables.

```bash
python -m venv virtual
virtual\Scripts\activate
pip install -r requirements.txt
playwright install chromium
```

Create a `.env` file:

```env
GEMINI_API_KEY=your_api_key_here
GEMINI_MODEL=gemini-2.5-flash
```

## Run the API

```bash
uvicorn app.main:app --reload
```

- API root: `http://127.0.0.1:8000/`
- Swagger docs: `http://127.0.0.1:8000/docs`

## Start Crawling

`POST /start-crawl`

Example request body:

```json
{
  "seed_urls": [
    "https://example-shop.com"
  ],
  "max_pages": 50
}
```

Example curl:

```bash
curl -X POST "http://127.0.0.1:8000/start-crawl" \
  -H "Content-Type: application/json" \
  -d "{\"seed_urls\": [\"https://example-shop.com\"], \"max_pages\": 50}"
```

## Configuration

Edit values in `app/config.py`:

- `KEYWORDS`: target product keywords used for categorization/filtering.
- `DATASET_DIR`: root folder for output dataset.
- `MIN_WIDTH`, `MIN_HEIGHT`: minimum image size.
- `MAX_PAGES_TO_CRAWL`: crawler exploration cap.
- `BATCH_SIZE_LLM`: URLs sent per Gemini request.
- `MAX_TOTAL_IMAGES`: hard stop for downloads.

## Notes

- On Windows, `main.py` sets a Proactor event loop policy to avoid Playwright subprocess issues.
- If Gemini is unavailable or errors, URL filtering falls back to local keyword matching.
- `max_pages` is accepted by the request schema but is not currently wired into crawl limits.
