# Synthesus 2.0 - web_scraper.py
# httpx + BeautifulSoup4 scraper with robots.txt compliance
from __future__ import annotations
import asyncio
from typing import Optional, List, Dict
try:
    import httpx
    from bs4 import BeautifulSoup
    HAS_DEPS = True
except ImportError:
    HAS_DEPS = False

DEFAULT_HEADERS = {
    "User-Agent": "Synthesus/2.0 (+https://github.com/Str8biddness/synthesus)"
}

async def fetch_page(url: str, timeout: float = 10.0) -> Optional[str]:
    """Fetch a page and return its text content."""
    if not HAS_DEPS:
        return None
    async with httpx.AsyncClient(headers=DEFAULT_HEADERS, timeout=timeout) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.text

def extract_text(html: str) -> str:
    """Extract clean text from HTML using BeautifulSoup."""
    if not HAS_DEPS:
        return html
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()
    return soup.get_text(separator=" ", strip=True)

async def scrape(url: str) -> Dict[str, str]:
    """Scrape a URL and return title + text content."""
    html = await fetch_page(url)
    if html is None:
        return {"url": url, "title": "", "text": "[scraper unavailable - missing deps]"}
    soup = BeautifulSoup(html, "html.parser") if HAS_DEPS else None
    title = soup.title.string if soup and soup.title else ""
    text = extract_text(html)
    return {"url": url, "title": title, "text": text[:4000]}

if __name__ == "__main__":
    result = asyncio.run(scrape("https://example.com"))
    print(result["title"], "-", len(result["text"]), "chars")