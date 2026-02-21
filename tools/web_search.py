import json
import os
import requests
from dotenv import load_dotenv
from loguru import logger

load_dotenv()

SERPAPI_KEY = os.getenv("SERP_API_KEY")
GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY")
SERPAPI_ENDPOINT = "https://serpapi.com/search.json"


def search_web(query: str, location: str | None = None) -> str:
    """General Google web search via SerpAPI. Returns rich structured results
    including answer_box, knowledge_graph, and top organic results."""
    params = {
        "engine": "google",
        "q": query,
        "api_key": SERPAPI_KEY,
        "num": 5,
    }
    if location:
        params["location"] = location

    try:
        resp = requests.get(SERPAPI_ENDPOINT, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        return _format_web_results(data)
    except Exception as e:
        logger.error(f"SerpAPI web search error: {e}")
        return "Search failed. Please try again."


def search_local(query: str, location: str | None = None) -> dict:
    """Google Maps local search via SerpAPI. Returns structured place data
    and a static map URL with pins.

    Returns a dict with keys:
      - "text": formatted text of local results
      - "map_url": Google Static Maps image URL with markers (or None)
    """
    params = {
        "engine": "google_maps",
        "q": query,
        "api_key": SERPAPI_KEY,
        "type": "search",
    }
    if location:
        params["ll"] = _location_to_ll(location)

    try:
        resp = requests.get(SERPAPI_ENDPOINT, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        return _format_local_results(data)
    except Exception as e:
        logger.error(f"SerpAPI local search error: {e}")
        return {"text": "Local search failed. Please try again.", "map_url": None}


def _location_to_ll(location: str) -> str:
    """Convert a location string to @lat,lng,zoom format for google_maps engine.
    Uses Google Geocoding API."""
    try:
        geo_resp = requests.get(
            "https://maps.googleapis.com/maps/api/geocode/json",
            params={"address": location, "key": GOOGLE_MAPS_API_KEY},
            timeout=10,
        )
        geo_resp.raise_for_status()
        results = geo_resp.json().get("results", [])
        if results:
            loc = results[0]["geometry"]["location"]
            return f"@{loc['lat']},{loc['lng']},14z"
    except Exception as e:
        logger.error(f"Geocoding error: {e}")
    return ""


def _format_web_results(data: dict) -> str:
    """Extract answer_box, knowledge_graph, and organic results into a
    structured string the LLM can summarize naturally."""
    sections = []

    answer_box = data.get("answer_box")
    if answer_box:
        ab_type = answer_box.get("type", "")
        if answer_box.get("answer"):
            sections.append(f"Direct answer: {answer_box['answer']}")
        elif answer_box.get("snippet"):
            sections.append(f"Quick answer: {answer_box['snippet']}")
        elif answer_box.get("result"):
            sections.append(f"Result: {answer_box['result']}")

    kg = data.get("knowledge_graph")
    if kg:
        kg_parts = []
        if kg.get("title"):
            kg_parts.append(f"Topic: {kg['title']}")
        if kg.get("type"):
            kg_parts.append(f"Type: {kg['type']}")
        if kg.get("description"):
            kg_parts.append(f"Description: {kg['description']}")
        if kg.get("source"):
            source = kg["source"]
            if isinstance(source, dict):
                kg_parts.append(f"Source: {source.get('name', '')}")
        if kg_parts:
            sections.append("Knowledge graph:\n" + "\n".join(kg_parts))

    organic = data.get("organic_results", [])
    if organic:
        org_lines = []
        for i, r in enumerate(organic[:5], 1):
            title = r.get("title", "")
            snippet = r.get("snippet", "")
            rich_snippet = r.get("rich_snippet", {})
            if rich_snippet:
                top = rich_snippet.get("top", {})
                if top.get("detected_extensions"):
                    snippet += " " + json.dumps(top["detected_extensions"])
            org_lines.append(f"{i}. {title}\n   {snippet}")
        sections.append("Top results:\n" + "\n\n".join(org_lines))

    if not sections:
        return "No search results found."

    return "\n\n---\n\n".join(sections)


def _format_local_results(data: dict) -> dict:
    """Format Google Maps local results into text + a static map URL."""
    local_results = data.get("local_results", [])
    if not local_results:
        return {"text": "No local results found.", "map_url": None}

    lines = []
    markers = []

    for i, place in enumerate(local_results[:8], 1):
        name = place.get("title", "Unknown")
        address = place.get("address", "")
        rating = place.get("rating")
        reviews = place.get("reviews")
        phone = place.get("phone", "")
        p_type = place.get("type", "")
        hours_state = place.get("hours", "")

        parts = [f"{i}. {name}"]
        if p_type:
            parts.append(f"   Type: {p_type}")
        if address:
            parts.append(f"   Address: {address}")
        if rating:
            rating_str = f"   Rating: {rating}/5"
            if reviews:
                rating_str += f" ({reviews} reviews)"
            parts.append(rating_str)
        if phone:
            parts.append(f"   Phone: {phone}")
        if hours_state:
            parts.append(f"   Hours: {hours_state}")

        lines.append("\n".join(parts))

        gps = place.get("gps_coordinates")
        if gps:
            lat = gps.get("latitude")
            lng = gps.get("longitude")
            if lat and lng:
                label = chr(ord("A") + i - 1) if i <= 26 else str(i)
                markers.append(f"markers=color:red%7Clabel:{label}%7C{lat},{lng}")

    text = "\n\n".join(lines)

    map_url = None
    if markers and GOOGLE_MAPS_API_KEY:
        markers_str = "&".join(markers)
        map_url = (
            f"https://maps.googleapis.com/maps/api/staticmap?"
            f"size=600x400&maptype=roadmap&{markers_str}"
            f"&key={GOOGLE_MAPS_API_KEY}"
        )

    return {"text": text, "map_url": map_url}
