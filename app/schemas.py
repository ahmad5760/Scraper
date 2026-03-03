from pydantic import BaseModel, HttpUrl
from typing import List, Optional

class CrawlRequest(BaseModel):
    # Validates that the input is a list of strings
    seed_urls: List[str] 
    
    # Optional: You can allow the user to limit pages from the API
    max_pages: Optional[int] = 50