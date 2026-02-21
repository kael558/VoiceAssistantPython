"""
Weekly news summary: AI news + U.S. politics + Canadian politics.

Uses SerpAPI to discover articles, Firecrawl to scrape content,
and Groq LLM to produce a concise summary sent via Twilio SMS.
"""

import os
import time

import requests
from dotenv import load_dotenv
from loguru import logger

load_dotenv()

SERPAPI_KEY = os.getenv("SERP_API_KEY")
SERPAPI_ENDPOINT = "https://serpapi.com/search.json"

SEARCH_TOPICS = [
    "AI artificial intelligence news this week",
    "US politics news this week",
    "Canadian politics news this week",
]


def _search_news(query: str, num_results: int = 5) -> list[dict]:
    """Search for recent news articles on a topic via SerpAPI."""
    try:
        resp = requests.get(
            SERPAPI_ENDPOINT,
            params={
                "engine": "google",
                "q": query,
                "api_key": SERPAPI_KEY,
                "tbm": "nws",
                "num": num_results,
            },
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        results = []
        for r in data.get("news_results", [])[:num_results]:
            results.append({
                "title": r.get("title", ""),
                "link": r.get("link", ""),
                "snippet": r.get("snippet", ""),
                "source": r.get("source", ""),
                "date": r.get("date", ""),
            })
        return results
    except Exception as e:
        logger.error(f"News search error for '{query}': {e}")
        return []


def _scrape_articles(articles: list[dict], max_per_topic: int = 3) -> list[dict]:
    """Scrape article content via Firecrawl. Falls back to snippet if scraping fails."""
    try:
        from tools.firecrawl_scraper import scrape_url
    except ImportError:
        logger.warning("Firecrawl not available, using snippets only")
        return articles

    scraped = []
    for article in articles[:max_per_topic]:
        url = article.get("link", "")
        if not url:
            scraped.append(article)
            continue

        content = scrape_url(url)
        if content and "Failed to scrape" not in content and "not available" not in content.lower():
            article["full_content"] = content[:2000]
        scraped.append(article)

    return scraped


def generate_weekly_summary(llm_client) -> str:
    """Gather news across all topics, scrape articles, and produce an
    LLM-generated summary. Returns the summary text."""

    all_articles = {}
    for topic in SEARCH_TOPICS:
        articles = _search_news(topic)
        scraped = _scrape_articles(articles)
        all_articles[topic] = scraped

    context_parts = []
    for topic, articles in all_articles.items():
        if not articles:
            context_parts.append(f"## {topic}\nNo articles found.\n")
            continue

        article_texts = []
        for a in articles:
            text = f"Title: {a['title']}\nSource: {a.get('source', 'Unknown')} ({a.get('date', '')})\n"
            if a.get("full_content"):
                text += f"Content: {a['full_content']}\n"
            else:
                text += f"Snippet: {a.get('snippet', '')}\n"
            article_texts.append(text)

        context_parts.append(f"## {topic}\n" + "\n---\n".join(article_texts))

    full_context = "\n\n".join(context_parts)

    try:
        response = llm_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a concise news briefing writer. Create a weekly summary "
                        "organized into three sections: AI News, U.S. Politics, and Canadian Politics. "
                        "For each section, highlight the 3-5 most important stories with a 1-2 sentence "
                        "summary of each. Use plain text only (no markdown, no emojis, no URLs). "
                        "Keep the total under 1500 characters so it fits in SMS messages. "
                        "Start with 'WEEKLY BRIEFING' as a header."
                    ),
                },
                {
                    "role": "user",
                    "content": f"Here are this week's articles:\n\n{full_context}",
                },
            ],
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"Summary generation failed: {e}")
        return "Failed to generate weekly summary. Please try again later."


def send_weekly_summary(llm_client, twilio_client, from_number: str, to_number: str) -> None:
    """Full pipeline: generate summary and send via SMS."""
    logger.info(f"Generating weekly summary for {to_number}")
    summary = generate_weekly_summary(llm_client)

    parts = [summary[i:i + 1600] for i in range(0, len(summary), 1600)]
    for i, part in enumerate(parts):
        if i > 0:
            time.sleep(1)
        try:
            twilio_client.messages.create(
                body=part,
                from_=from_number,
                to=to_number,
            )
        except Exception as e:
            logger.error(f"Failed to send summary SMS part {i + 1}: {e}")

    logger.info(f"Weekly summary sent to {to_number} ({len(parts)} parts)")
