import os
from dotenv import load_dotenv
from loguru import logger

load_dotenv()

FIRECRAWL_API_KEY = os.getenv("FIRECRAWL_API_KEY")

MAX_CONTENT_LENGTH = 4000


def scrape_url(url: str) -> str:
    """Scrape a URL using Firecrawl and return the page content as markdown.
    Truncates to ~4000 chars to fit within LLM context limits."""
    try:
        from firecrawl import FirecrawlApp

        app = FirecrawlApp(api_key=FIRECRAWL_API_KEY)
        result = app.scrape_url(url, params={"formats": ["markdown"]})

        content = ""
        if isinstance(result, dict):
            content = result.get("markdown", "") or result.get("content", "")
        elif hasattr(result, "markdown"):
            content = result.markdown or ""

        if not content:
            return f"Could not extract content from {url}."

        if len(content) > MAX_CONTENT_LENGTH:
            content = content[:MAX_CONTENT_LENGTH] + "\n\n[... content truncated ...]"

        return content

    except ImportError:
        logger.error("firecrawl-py is not installed. Run: pip install firecrawl-py")
        return "Firecrawl SDK not available."
    except Exception as e:
        logger.error(f"Firecrawl scrape error for {url}: {e}")
        return f"Failed to scrape {url}: {str(e)}"
