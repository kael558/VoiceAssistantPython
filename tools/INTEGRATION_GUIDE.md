# Integrating Bus Router with Voice Assistant

This guide shows you how to integrate the `bus_router` tool into your voice assistant (`bot.py`).

## Quick Integration Steps

### Step 1: Import the Bus Router

Add this import at the top of `bot.py`:

```python
from tools.bus_router import get_bus_route
```

### Step 2: Add to `get_tools()` Function

Add the bus router tool definition to the `get_tools()` function:

```python
def get_tools():
    return [
        # ... existing tools ...
        {
            "type": "function",
            "function": {
                "name": "get_bus_route",
                "description": "Find the best bus route between two locations. Uses Google Maps and real-time vehicle positions to recommend the fastest route. Use this when user asks for transit directions, bus routes, or how to get somewhere by bus.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "origin": {
                            "type": "string",
                            "description": "Starting location (address or 'lat,lng')",
                        },
                        "destination": {
                            "type": "string",
                            "description": "Destination location (address or 'lat,lng')",
                        },
                        "gtfs_feed_url": {
                            "type": "string",
                            "description": "Optional GTFS Realtime feed URL for vehicle positions. Leave empty to use Google Maps only.",
                        }
                    },
                    "required": ["origin", "destination"],
                },
            }
        }
    ]
```

### Step 3: Add to Available Functions

In the `handle_tools()` function, add the bus router to available functions:

```python
async def handle_tools(messages, tool_calls, from_, to_):
    try:
        available_functions = {
            "search_bing": search_bing,
            "toggle_wifi": toggle_wifi,
            "get_bus_route": get_bus_route  # Add this line
        }
        # ... rest of the function
```

### Step 4: Register with LLM Service (for WebRTC calls)

In the `run_bot()` function, register the function with the LLM:

```python
async def run_bot(websocket_client, stream_sid):
    # ... existing code ...

    # After creating the llm service:
    llm.register_function(
        "search_bing",
        search,
        start_callback=start_search)

    # Add bus router registration:
    llm.register_function(
        "get_bus_route",
        get_bus_route_async,  # We'll create this wrapper
        start_callback=start_bus_routing)
```

### Step 5: Create Async Wrapper and Callbacks

Add these functions before `run_bot()`:

```python
async def start_bus_routing(llm):
    """Callback when bus routing starts"""
    await llm.push_frame(TextFrame("Let me find the best bus route for you. One moment."))


async def get_bus_route_async(llm, args):
    """Async wrapper for get_bus_route"""
    try:
        # Get the GTFS feed URL from environment or use None
        gtfs_feed_url = args.get("gtfs_feed_url") or os.getenv("GTFS_FEED_URL")

        result = get_bus_route(
            origin=args["origin"],
            destination=args["destination"],
            gtfs_feed_url=gtfs_feed_url
        )

        # Simplify result for voice output (remove emojis, etc.)
        voice_result = simplify_for_voice(result)
        return voice_result
    except Exception as e:
        logger.error(f"Error getting bus route: {e}")
        return "Sorry, I couldn't find a bus route at this time. Please try again."


def simplify_for_voice(text: str) -> str:
    """
    Simplify the route output for voice reading.
    Removes emojis and formats for audio.
    """
    # Remove common emojis
    emojis_to_remove = ['🚌', '📍', '⏱️', '📊', '✅', '🔴', '⬜', '🗺️']
    for emoji in emojis_to_remove:
        text = text.replace(emoji, '')

    # Replace special characters
    text = text.replace('=', '')
    text = text.replace('-', '')

    # Simplify formatting
    text = text.replace('LIVE:', 'Real-time:')
    text = text.replace('~', 'approximately')

    return text.strip()
```

## Complete Modified `bot.py` Section

Here's how the relevant sections should look after integration:

```python
# ... existing imports ...
from tools.web_search import search_bing
from tools.wifi_controller import toggle_wifi
from tools.bus_router import get_bus_route  # ADD THIS

# ... existing code ...

def get_tools():
    return [
        {
            "type": "function",
            "function": {
                "name": "search_bing",
                "description": "Search the web. Use this to search up real-time information, current events or weather updates (basically anything that requires latest information).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "The search query",
                        },
                    },
                    "required": ["query"],
                },
            }
        },
        {
            "type": "function",
            "function": {
                "name": "toggle_wifi",
                "description": "Toggle the WiFi",
                "parameters": {
                    "type": "object",
                    "properties": {},
                },
            }
        },
        {
            "type": "function",
            "function": {
                "name": "get_bus_route",
                "description": "Find the best bus route between two locations. Uses Google Maps and real-time vehicle positions to recommend the fastest route. Use this when user asks for transit directions, bus routes, or how to get somewhere by bus.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "origin": {
                            "type": "string",
                            "description": "Starting location (address or 'lat,lng')",
                        },
                        "destination": {
                            "type": "string",
                            "description": "Destination location (address or 'lat,lng')",
                        },
                        "gtfs_feed_url": {
                            "type": "string",
                            "description": "Optional GTFS Realtime feed URL for vehicle positions",
                        }
                    },
                    "required": ["origin", "destination"],
                },
            }
        }
    ]

async def handle_tools(messages, tool_calls, from_, to_):
    try:
        available_functions = {
            "search_bing": search_bing,
            "toggle_wifi": toggle_wifi,
            "get_bus_route": get_bus_route  # ADD THIS
        }
        # ... rest remains the same ...

async def start_bus_routing(llm):
    """Callback when bus routing starts"""
    await llm.push_frame(TextFrame("Let me find the best bus route for you. One moment."))


async def get_bus_route_async(llm, args):
    """Async wrapper for get_bus_route"""
    try:
        gtfs_feed_url = args.get("gtfs_feed_url") or os.getenv("GTFS_FEED_URL")

        result = get_bus_route(
            origin=args["origin"],
            destination=args["destination"],
            gtfs_feed_url=gtfs_feed_url
        )

        voice_result = simplify_for_voice(result)
        return voice_result
    except Exception as e:
        logger.error(f"Error getting bus route: {e}")
        return "Sorry, I couldn't find a bus route at this time. Please try again."


def simplify_for_voice(text: str) -> str:
    """Simplify the route output for voice reading."""
    emojis_to_remove = ['🚌', '📍', '⏱️', '📊', '✅', '🔴', '⬜', '🗺️']
    for emoji in emojis_to_remove:
        text = text.replace(emoji, '')

    text = text.replace('=', '')
    text = text.replace('-', '')
    text = text.replace('LIVE:', 'Real-time:')
    text = text.replace('~', 'approximately')

    return text.strip()


async def run_bot(websocket_client, stream_sid):
    # ... existing code up to llm.register_function ...

    llm.register_function(
        "search_bing",
        search,
        start_callback=start_search)

    llm.register_function(
        "get_bus_route",
        get_bus_route_async,
        start_callback=start_bus_routing)

    # ... rest of the function remains the same ...
```

## Environment Variables

Add to your `.env` file:

```env
# Required for bus routing
GOOGLE_MAPS_API_KEY=your_google_maps_api_key

# Optional: Default GTFS feed for your area
GTFS_FEED_URL=https://your-transit-agency.com/gtfs-realtime/vehicle-positions
```

## Testing the Integration

### Via SMS (using choose_tools)

User texts: "How do I get from Times Square to Central Park by bus?"

The assistant will:

1. Recognize this as a bus routing request
2. Call `get_bus_route` with parsed origin and destination
3. Return the best route via SMS

### Via Voice Call (using run_bot)

User says: "Hey Lucy, what's the best bus to Santa Monica from downtown?"

The assistant will:

1. Say: "Let me find the best bus route for you. One moment."
2. Call the API and analyze routes
3. Read out the simplified route information

## Example User Queries

The assistant will automatically recognize these types of queries:

- "How do I get to [destination] by bus?"
- "What bus goes from [origin] to [destination]?"
- "Find me a bus route to [destination]"
- "Best way to get to [destination] using public transit"
- "When is the next bus from [origin] to [destination]?"

## Advanced: Location-Specific GTFS Feed

If you want to automatically use the correct GTFS feed based on location:

```python
def get_gtfs_feed_for_location(location: str) -> str:
    """Get GTFS feed URL based on location"""

    # Simple keyword matching (could be improved with geocoding)
    location_lower = location.lower()

    if "los angeles" in location_lower or "la" in location_lower:
        return "https://api.metro.net/gtfsrt/vehicle-positions/all"
    elif "new york" in location_lower or "nyc" in location_lower:
        return "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs"
    elif "san francisco" in location_lower:
        return "http://api.bart.gov/gtfsrt/tripupdate.aspx"
    # Add more cities...

    return None  # Fall back to Google Maps only

# In get_bus_route_async:
async def get_bus_route_async(llm, args):
    gtfs_feed_url = args.get("gtfs_feed_url")

    if not gtfs_feed_url:
        # Try to infer from origin location
        gtfs_feed_url = get_gtfs_feed_for_location(args["origin"])

    # ... rest of function
```

## Troubleshooting

### Tool Not Being Called

If the LLM doesn't call the tool:

1. Check the tool description is clear
2. Ensure the tool is in the tools list
3. Test with explicit queries like "Find me a bus route from X to Y"

### API Errors

If you get API errors:

1. Verify `GOOGLE_MAPS_API_KEY` is set in `.env`
2. Check Google Cloud Console for API limits
3. Enable Directions API in Google Cloud

### Voice Output Issues

If the voice sounds wrong:

1. Improve `simplify_for_voice()` function
2. Remove more special characters
3. Convert times to words ("5 minutes" not "5 min")

## Next Steps

1. ✅ Add the integration code
2. ✅ Set environment variables
3. ⬜ Test with sample queries
4. ⬜ Fine-tune voice output
5. ⬜ Add error handling for edge cases

Happy routing! 🚌
