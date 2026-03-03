import asyncio
import json
from typing import List

import google.generativeai as genai

from app.config import Config

if Config.GEMINI_API_KEY:
    genai.configure(api_key=Config.GEMINI_API_KEY)


class LLMService:
    def __init__(self):
        self.model_name = self._resolve_model_name()
        self.model = genai.GenerativeModel(self.model_name)
        print(f"Using Gemini model: {self.model_name}")

    def _candidate_models(self) -> List[str]:
        candidates = [
            Config.GEMINI_MODEL,
            "gemini-2.5-flash",
            "gemini-2.0-flash",
            "gemini-2.0-flash-001",
        ]
        unique = []
        for name in candidates:
            if name and name not in unique:
                unique.append(name)
        return unique

    def _resolve_model_name(self) -> str:
        candidates = self._candidate_models()

        if not Config.GEMINI_API_KEY:
            return candidates[0]

        try:
            available_models = {}
            for model in genai.list_models():
                raw_name = getattr(model, "name", "")
                name = raw_name.split("/", 1)[1] if raw_name.startswith("models/") else raw_name
                supported_methods = set(getattr(model, "supported_generation_methods", []) or [])
                if name:
                    available_models[name] = supported_methods

            for candidate in candidates:
                if "generateContent" in available_models.get(candidate, set()):
                    return candidate

            for name, methods in available_models.items():
                if name.startswith("gemini-") and "generateContent" in methods:
                    return name
        except Exception as e:
            print(f"Could not validate Gemini model list: {e}")

        return candidates[0]

    def _local_filter_urls(self, urls: List[str]) -> List[str]:
        blocked_tokens = (
            "login",
            "signin",
            "signup",
            "cart",
            "checkout",
            "policy",
            "privacy",
            "terms",
            "about",
            "contact",
            "account",
        )
        kept = []
        for url in urls:
            lowered_url = url.lower()
            if any(token in lowered_url for token in blocked_tokens):
                continue

            for keyword in Config.KEYWORDS:
                keyword_lower = keyword.lower()
                slug_form = keyword_lower.replace(" ", "-")
                underscore_form = keyword_lower.replace(" ", "_")
                if (
                    keyword_lower in lowered_url
                    or slug_form in lowered_url
                    or underscore_form in lowered_url
                ):
                    kept.append(url)
                    break
        return kept

    async def filter_urls_batch(self, urls: List[str]) -> List[str]:
        """
        Sends a batch of URLs to Gemini to check relevance.
        """
        if not urls:
            return []

        if not Config.GEMINI_API_KEY:
            print("GEMINI_API_KEY is missing. Using local URL filter.")
            return self._local_filter_urls(urls)

        prompt = f"""
        You are a Data Engineer filtering URLs for an e-commerce dataset.
        Target Keywords: {Config.KEYWORDS}

        Task: Analyze the following list of URLs. Return a JSON list containing ONLY the URLs that likely contain product pages for the target keywords based on the slug or path.
        Ignore login pages, cart, policies, or general category pages if they don't look like specific items.

        Input URLs:
        {json.dumps(urls)}

        Output format: JSON list of strings only. No markdown.
        """

        try:
            response = await asyncio.to_thread(self.model.generate_content, prompt)
            text = (response.text or "").replace("```json", "").replace("```", "").strip()
            relevant_urls = json.loads(text)
            if isinstance(relevant_urls, list):
                return [url for url in relevant_urls if isinstance(url, str)]
            return self._local_filter_urls(urls)
        except Exception as e:
            print(f"Error calling Gemini: {e}")
            return self._local_filter_urls(urls)
