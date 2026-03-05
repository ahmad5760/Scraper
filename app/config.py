import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    
    # Target keywords
    KEYWORDS = [
        "panjabi",
        "thobe",
        "abaya",
        "dawah t-shirt",
        "kifaya",
    ]
    
    # Image constraints
    MIN_WIDTH = 500
    MIN_HEIGHT = 500
    
    # Limits
    MAX_PAGES_TO_CRAWL = 50 
    BATCH_SIZE_LLM = 10 
    
    # Stop after saving this many images
    MAX_TOTAL_IMAGES = 400

    # Output dataset root directory
    DATASET_DIR = "dataset"
