import httpx
from bs4 import BeautifulSoup
import logging

logger = logging.getLogger(__name__)

class WebScraper:
    """A tool for Synthesus characters to autonomously fetch and parse web content."""
    
    def __init__(self, timeout: int = 10, max_chars: int = 15000):
        self.timeout = timeout
        self.max_chars = max_chars

    async def fetch(self, url: str) -> dict:
        """Fetches a URL and returns the parsed text content."""
        logger.info(f"Agent requested web fetch: {url}")
        if not url.startswith("http"):
            url = f"https://{url}"

        try:
            async with httpx.AsyncClient(timeout=self.timeout, verify=False) as client:
                response = await client.get(url, follow_redirects=True)
                response.raise_for_status()
                
                # Parse HTML
                soup = BeautifulSoup(response.text, "html.parser")
                
                # Remove scripts and styles
                for script in soup(["script", "style", "nav", "footer", "header"]):
                    script.decompose()
                    
                text = soup.get_text(separator="\n", strip=True)
                
                # Truncate to avoid context window explosion
                if len(text) > self.max_chars:
                    text = text[:self.max_chars] + "... [TRUNCATED]"
                    
                return {
                    "status": "success",
                    "url": str(response.url),
                    "content": text,
                    "length": len(text)
                }
        except Exception as e:
            logger.error(f"Failed to scrape {url}: {e}")
            return {
                "status": "error",
                "url": url,
                "error": str(e)
            }
