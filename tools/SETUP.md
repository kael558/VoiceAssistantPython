# Bus Router Tool Setup Guide

## Quick Start

### 1. Install Dependencies

```bash
pip install -r ../requirements.txt
```

### 2. Set up Google Maps API Key

Create a `.env` file in the project root with:

```env
GOOGLE_MAPS_API_KEY=your_api_key_here
```

**Getting Your API Key:**

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select an existing one
3. Navigate to "APIs & Services" > "Credentials"
4. Click "Create Credentials" > "API Key"
5. Enable the following APIs:
   - **Directions API**
   - **Maps JavaScript API**
6. Copy your API key to the `.env` file

**Important:** Set up billing and API restrictions to avoid unexpected charges!

### 3. Find Your Local GTFS Feed (Optional but Recommended)

For real-time vehicle tracking, you need your transit agency's GTFS Realtime feed:

**How to Find It:**

1. Visit [Mobility Database](https://database.mobilitydata.org/) or [TransitFeeds.com](https://transitfeeds.com/)
2. Search for your city or transit agency
3. Look for "GTFS Realtime" or "Vehicle Positions" feed
4. Copy the feed URL

**Common US Transit Agencies:**

| City          | Agency            | GTFS Realtime Feed URL                                                  |
| ------------- | ----------------- | ----------------------------------------------------------------------- |
| Los Angeles   | LA Metro          | `https://api.metro.net/gtfsrt/vehicle-positions/all`                    |
| New York      | MTA               | `https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs`    |
| San Francisco | BART              | `http://api.bart.gov/gtfsrt/tripupdate.aspx`                            |
| Chicago       | CTA               | Contact CTA for feed access                                             |
| Seattle       | King County Metro | `https://s3.amazonaws.com/kcm-alerts-realtime-prod/vehiclepositions.pb` |
| Boston        | MBTA              | `https://cdn.mbta.com/realtime/VehiclePositions.pb`                     |
| Washington DC | WMATA             | Requires API key from WMATA                                             |

**Note:** Some feeds require API keys or authentication. Check your agency's developer portal.

### 4. Test the Tool

Run the example:

```bash
cd tools
python bus_router_example.py
```

Or test in Python:

```python
from tools.bus_router import get_bus_route

# Basic usage (no real-time data)
result = get_bus_route(
    "Your starting address",
    "Your destination address"
)
print(result)

# With real-time data
result = get_bus_route(
    "Your starting address",
    "Your destination address",
    gtfs_feed_url="https://your-transit-agency.com/gtfs-rt"
)
print(result)
```

## Troubleshooting

### Google Maps API Errors

**Error: "Google Maps API key not found"**

- Make sure `.env` file exists in project root
- Check that `GOOGLE_MAPS_API_KEY` is set correctly
- Restart your application after adding the key

**Error: "REQUEST_DENIED" or "API key not valid"**

- Verify the API key is correct
- Enable Directions API in Google Cloud Console
- Check API key restrictions (should allow your IP/domain)

**Error: "OVER_QUERY_LIMIT"**

- You've exceeded your free quota
- Check usage in Google Cloud Console
- Consider enabling billing for higher limits

### GTFS Feed Errors

**Error: "Failed to fetch GTFS data"**

- Verify the feed URL is correct and accessible
- Check if the feed requires authentication
- Try accessing the URL directly in a browser
- Some feeds may be temporarily down

**No real-time data showing**

- Not all agencies provide vehicle positions
- Some feeds only include trip updates, not positions
- Vehicle may not have GPS enabled
- Feed may only update every few minutes

### Network Issues

**Error: Timeout or connection errors**

- Check your internet connection
- Some corporate networks block certain APIs
- Try using a VPN if behind a firewall
- Increase timeout in the code if on slow connection

## Advanced Configuration

### Custom Feed Integration

If your transit agency isn't listed, you can add it:

```python
from tools.bus_router import BusRouter

router = BusRouter()

# Add your custom feed
router.gtfs_feeds["my_city"] = {
    "vehicle_positions": "https://example.com/gtfs-rt/vehicles",
    "trip_updates": "https://example.com/gtfs-rt/trips",  # optional
}
```

### API Rate Limiting

To avoid hitting API limits:

```python
import time
from tools.bus_router import get_bus_route

# Add delay between requests
result = get_bus_route(origin, destination)
time.sleep(1)  # Wait 1 second before next request
```

### Caching Results

For repeated queries, cache the results:

```python
from functools import lru_cache
from tools.bus_router import get_bus_route

@lru_cache(maxsize=100)
def cached_route(origin, destination, feed_url=None):
    return get_bus_route(origin, destination, feed_url)

# This will use cached result for same inputs
result1 = cached_route("A", "B")
result2 = cached_route("A", "B")  # Cached, no API call
```

## Cost Considerations

### Google Maps API Pricing

**Free Tier:**

- $200 credit per month
- Directions API: $5 per 1,000 requests
- This gives you ~40,000 free requests/month

**Tips to Reduce Costs:**

- Cache frequent routes
- Implement rate limiting
- Set up budget alerts in Google Cloud
- Use API key restrictions

### Best Practices

1. **Cache results** for repeated queries
2. **Batch similar requests** when possible
3. **Monitor usage** in Google Cloud Console
4. **Set up billing alerts** to avoid surprises
5. **Restrict API key** to only necessary APIs

## Integration with Voice Assistant

To integrate with your voice assistant:

```python
# In your bot.py or main voice assistant file

from tools.bus_router import get_bus_route

def handle_bus_routing_request(origin, destination):
    """Handle voice command for bus routing"""

    # Get the route with your local GTFS feed
    result = get_bus_route(
        origin=origin,
        destination=destination,
        gtfs_feed_url="https://your-agency.com/gtfs-rt"
    )

    # Convert to voice-friendly format
    # (remove emojis, simplify language, etc.)
    voice_result = simplify_for_voice(result)

    return voice_result
```

## Support

For more information:

- [GTFS Realtime Documentation](https://gtfs.org/documentation/realtime/)
- [Google Maps Directions API Docs](https://developers.google.com/maps/documentation/directions)
- [Mobility Database](https://database.mobilitydata.org/)

## Next Steps

1. ✅ Install dependencies
2. ✅ Get Google Maps API key
3. ✅ Find local GTFS feed
4. ✅ Test with example
5. ⬜ Integrate with voice assistant
6. ⬜ Set up monitoring and alerts

Happy routing! 🚌
