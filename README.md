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
hf_upload.py               # Batch uploader from local dataset/ to Hugging Face dataset repo
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

## Upload Dataset to Hugging Face

`hf_upload.py` uploads scraped images from `dataset/` to a Hugging Face dataset repository in resumable batches.

Install dependencies (already included in `requirements.txt`):

```bash
pip install -r requirements.txt
```

Set auth and repo env vars in `.env`:

```env
HF_TOKEN=your_huggingface_token
# Optional:
# HUGGINGFACE_HUB_TOKEN=your_huggingface_token
# HF_DATASET_REPO=username/repo_name
# HF_DATASET_NAME=fashion-product-images
# HF_DATASET_PRIVATE=true
```

Run upload:

```bash
python hf_upload.py
```

Dry run (no upload, no file deletion):

```bash
python hf_upload.py --dry-run
```

### hf_upload.py behavior

- Reads local `.env` automatically.
- Scans `LOCAL_DATASET_DIR` (default `dataset/`) for image files in keyword subfolders.
- Uploads image extensions: `.jpg`, `.jpeg`, `.png`, `.webp`.
- Optionally requires sidecar metadata (`.json`) per image (`HF_REQUIRE_METADATA=true` by default).
- Uploads in batches (`HF_BATCH_SIZE`, default `300`) with retry/backoff controls.
- Verifies uploaded files exist remotely before marking success.
- On successful batch upload, updates local state and deletes uploaded local files.

State files created under `dataset/`:

- `.hf_upload_manifest.json`: tracks uploaded images to avoid re-uploading.
- `.hf_upload_batches.jsonl`: append-only batch run log.

### hf_upload.py environment variables

- `HF_TOKEN` or `HUGGINGFACE_HUB_TOKEN`: Hugging Face access token (required).
- `HF_DATASET_REPO`: target dataset repo (`username/repo` or just `repo`).
- `HF_DATASET_NAME`: default repo name when `HF_DATASET_REPO` is not set.
- `HF_DATASET_PRIVATE`: `true/false` (default `true`) when creating repo.
- `LOCAL_DATASET_DIR`: local dataset root (default `dataset`).
- `HF_REQUIRE_METADATA`: require matching `.json` for each image (default `true`).
- `HF_BATCH_SIZE`: images per batch (default `300`).
- `HF_UPLOAD_MAX_RETRIES`: retries per failed batch (default `5`).
- `HF_UPLOAD_INITIAL_BACKOFF_SECONDS`: retry backoff base seconds (default `2`).

## Download Dataset from Hugging Face

Use `load_dataset.py` to download the full dataset repository snapshot locally.

```bash
python load_dataset.py
```

Defaults:

- Repo: `Ahmad1931259/fashion-product-images`
- Local directory: `load_dataset/`
- Auth token (optional for public repos): `HF_TOKEN` or `HUGGINGFACE_HUB_TOKEN`

## Check Person Presence in an Image

Use `person_checker.py` to check whether an image contains at least one person with GPT-4o Mini Vision.

```bash
python person_checker.py
```

Default image path:

- `dawah_t-shirt/1195_image.jpg` (it also tries `load_dataset/dawah_t-shirt/1195_image.jpg`)

Output format:

```json
{"person_present": "yes"}
```

or

```json
{"person_present": "no"}
```

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
