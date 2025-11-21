# Bus Router Tool 🚌

A sophisticated bus routing tool that combines **Google Maps Transit Directions** with **GTFS Realtime vehicle positions** to find the optimal bus route based on actual real-time bus locations.

## Features

✅ **Google Maps Integration** - Gets multiple transit route options
✅ **GTFS Realtime Support** - Fetches live vehicle positions from transit agencies
✅ **Smart Route Analysis** - Calculates which route is fastest based on real-time data
✅ **Vehicle Tracking** - Shows distance and estimated arrival time of next bus
✅ **Congestion Awareness** - Considers traffic congestion levels when available
✅ **Multiple Routes** - Compares all available options and recommends the best one

## Setup

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

The tool requires:

- `requests` - For API calls
- `python-dotenv` - For environment variables
- `gtfs-realtime-bindings` - For parsing GTFS Realtime data

### 2. Get Google Maps API Key

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select existing one
3. Enable **Directions API** and **Maps JavaScript API**
4. Create API credentials (API Key)
5. Add the key to your `.env` file:

```env
GOOGLE_MAPS_API_KEY=your_api_key_here
```

### 3. Find Your Local GTFS Realtime Feed

Most transit agencies provide GTFS Realtime feeds. Here are some examples:

**United States:**

- **San Francisco (BART)**: `http://api.bart.gov/gtfsrt/tripupdate.aspx`
- **NYC (MTA)**: `https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs`
- **LA Metro**: `https://api.metro.net/gtfsrt/vehicle-positions/all`
- **Chicago (CTA)**: `http://www.transitchicago.com/downloads/sch_data/google_transit.zip`

**Find Your Agency:**

- Visit [TransitFeeds.com](https://transitfeeds.com/) or [Mobility Database](https://database.mobilitydata.org/)
- Search for your city's transit agency
- Look for "GTFS Realtime" or "Vehicle Positions" feed

**Note:** Some feeds require API keys. Check your transit agency's developer portal.

## Usage

### Basic Usage (Without Real-time Data)

```python
from tools.bus_router import get_bus_route

# Get bus routes using Google Maps only
result = get_bus_route(
    origin="Union Station, Los Angeles",
    destination="Santa Monica Pier, Santa Monica"
)
print(result)
```

### Advanced Usage (With Real-time Vehicle Data)

```python
from tools.bus_router import get_bus_route

# Get bus routes with real-time vehicle positions
result = get_bus_route(
    origin="Times Square, New York",
    destination="Central Park, New York",
    gtfs_feed_url="https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs"
)
print(result)
```

### Using Coordinates Instead of Addresses

```python
result = get_bus_route(
    origin="34.0522,-118.2437",  # Downtown LA coordinates
    destination="34.0195,-118.4912"  # Santa Monica coordinates
)
```

## Output Example

```
🚌 Bus Route Options:

============================================================

📍 Route 1: Metro Local Line
   From: Union Station, Los Angeles, CA
   To: Santa Monica Pier, Santa Monica, CA
   Distance: 15.2 miles
   ⏱️  Estimated Time (with real-time): 52.3 min
   📊 Scheduled Time: 55 min

   Steps:
   1. Take Metro Rapid Line 704 (704)
      From: Union Station
      To: Wilshire/26th St
      Duration: 42 min (28 stops)
      🔴 LIVE: Next bus in ~3.2 min
      Vehicle: MTA_5412 (450.5m away)

   2. Walk to Santa Monica Pier (8 min)

------------------------------------------------------------

📍 Route 2: Express Route
   From: Union Station, Los Angeles, CA
   To: Santa Monica Pier, Santa Monica, CA
   Distance: 16.8 miles
   ⏱️  Estimated Time (with real-time): 58.7 min
   📊 Scheduled Time: 50 min

   Steps:
   1. Take Metro Express 534 (534)
      From: Union Station
      To: Santa Monica Blvd/4th St
      Duration: 38 min (12 stops)
      🔴 LIVE: Next bus in ~12.5 min
      Vehicle: MTA_6201 (1823.2m away)

   2. Walk to destination (15 min)

------------------------------------------------------------

✅ RECOMMENDED: Route 1
   Fastest option with real-time data: ~52.3 min
```

## How It Works

### 1. **Google Maps Query**

The tool queries Google Maps Directions API for all available transit routes between origin and destination.

### 2. **GTFS Realtime Data Fetch**

If a GTFS feed URL is provided, it fetches current vehicle positions including:

- GPS coordinates
- Vehicle ID
- Current speed
- Congestion level
- Occupancy status

### 3. **Smart Matching**

For each bus route, the tool:

- Finds the closest vehicle on that route
- Calculates distance to your departure stop
- Estimates when the bus will arrive
- Considers current traffic/congestion

### 4. **Route Optimization**

Routes are ranked by:

1. **Real-time estimated duration** (if available)
2. **Scheduled duration** (fallback)
3. **Number of transfers**
4. **Total distance**

### 5. **Recommendation**

The tool recommends the fastest route based on current conditions.

## API Reference

### `get_bus_route(origin, destination, gtfs_feed_url=None)`

**Parameters:**

- `origin` (str): Starting location - can be address or "lat,lng"
- `destination` (str): Ending location - can be address or "lat,lng"
- `gtfs_feed_url` (str, optional): URL to GTFS Realtime vehicle positions feed

**Returns:**

- `str`: Formatted summary of routes with recommendations

### `BusRouter` Class

**Methods:**

- `get_transit_directions(origin, destination)` - Query Google Maps
- `get_gtfs_vehicle_positions(feed_url)` - Fetch vehicle positions
- `analyze_routes_with_realtime(directions_data, feed_url)` - Analyze routes
- `calculate_distance(lat1, lon1, lat2, lon2)` - Haversine distance
- `estimate_arrival_time(vehicle, stop_lat, stop_lon)` - Estimate ETA

## Limitations

1. **API Rate Limits**: Google Maps API has usage limits (check your quota)
2. **GTFS Availability**: Not all transit agencies provide real-time data
3. **Feed Quality**: Some feeds may be incomplete or delayed
4. **Coverage**: Only works for public transit routes covered by Google Maps
5. **Accuracy**: Real-time estimates depend on vehicle GPS accuracy

## Troubleshooting

### "Google Maps API key not found"

- Ensure `GOOGLE_MAPS_API_KEY` is set in your `.env` file
- Check that the API key has Directions API enabled

### "No routes found"

- Verify origin and destination are valid
- Check if transit is available for your route
- Try using coordinates instead of addresses

### "Error fetching GTFS data"

- Verify the GTFS feed URL is correct
- Check if the feed requires authentication
- Some feeds may be temporarily unavailable

### Real-time data not showing

- Not all transit agencies provide vehicle positions
- Some feeds only update every few minutes
- Vehicle may not have GPS enabled

## Advanced Features

### Custom GTFS Feeds

```python
from tools.bus_router import BusRouter

router = BusRouter()

# Add custom feed
router.gtfs_feeds["my_city"] = "https://my-transit-agency.com/gtfs-rt"

# Use it
directions = router.get_transit_directions("Origin", "Destination")
vehicles = router.get_gtfs_vehicle_positions(router.gtfs_feeds["my_city"])
```

### Accessing Raw Data

```python
from tools.bus_router import BusRouter

router = BusRouter()

# Get raw Google Maps response
directions = router.get_transit_directions("Origin", "Destination")

# Get raw vehicle data
vehicles = router.get_gtfs_vehicle_positions("https://feed-url.com")

# Analyze routes
analysis = router.analyze_routes_with_realtime(directions, "https://feed-url.com")
```

## Contributing

To add support for more transit agencies:

1. Find the GTFS Realtime feed URL
2. Add it to the `gtfs_feeds` dictionary in `BusRouter.__init__`
3. Test with local routes

## Resources

- [GTFS Realtime Documentation](https://gtfs.org/documentation/realtime/)
- [Google Maps Directions API](https://developers.google.com/maps/documentation/directions)
- [Mobility Database](https://database.mobilitydata.org/) - Find GTFS feeds
- [GTFS Realtime Vehicle Positions](https://gtfs.org/documentation/realtime/feed-entities/vehicle-positions/)

## License

This tool is part of the VoiceAssistant project.

---

**Happy Routing! 🚌🗺️**
