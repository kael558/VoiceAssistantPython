import os
import json
import requests
import time
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
from dotenv import load_dotenv
from google.transit import gtfs_realtime_pb2
import math

# Load environment variables
load_dotenv()

GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY")
OC_TRANSPO_PRIMARY_KEY = os.getenv("OC_TRANSPO_PRIMARY_KEY")


class BusRouter:
    """
    Advanced bus routing tool that combines Google Maps transit directions
    with GTFS Realtime vehicle positions to find the optimal route.
    """
    
    def __init__(self):
        self.google_api_key = GOOGLE_MAPS_API_KEY
        # Common GTFS Realtime feeds by region
        # Users should add their local transit agency's GTFS feed URL
        self.gtfs_feeds = {
            # Example feeds (users need to add their local transit agency)
            "default": None,  # Will be set based on location
        }
    
    def get_transit_directions(self, origin: str, destination: str) -> Optional[Dict]:
        """
        Get transit directions from Google Maps API.
        
        Args:
            origin: Starting location (address or coordinates)
            destination: Ending location (address or coordinates)
            
        Returns:
            Dictionary containing route information
        """
        if not self.google_api_key:
            return {"error": "Google Maps API key not found in environment variables"}
        
        url = "https://maps.googleapis.com/maps/api/directions/json"
        
        params = {
            "origin": origin,
            "destination": destination,
            "mode": "transit",
            # Include all common transit types instead of bus-only
            # Valid values: bus, subway, train, tram, rail (pipe-separated)
            "transit_mode": "bus|subway|train|tram|rail",
            "departure_time": "now",
            "alternatives": "true",
            "key": self.google_api_key
        }
        
        try:
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            if data.get("status") != "OK":
                return {"error": f"Google Maps API error: {data.get('status')}"}
            
            return data
        except Exception as e:
            return {"error": f"Failed to get directions: {str(e)}"}
    
    def get_gtfs_vehicle_positions(self, feed_url: str) -> Optional[List[Dict]]:
        """
        Fetch real-time vehicle positions from GTFS Realtime feed.
        
        Args:
            feed_url: URL of the GTFS Realtime feed
            
        Returns:
            List of vehicle position data
        """
        if not feed_url:
            return None

        try:
            # Some agencies (e.g. OC Transpo) require an API subscription key header.
            headers: Dict[str, str] = {}
            if "nextrip-public-api.azure-api.net/octranspo" in feed_url:
                # OC Transpo GTFS-RT Vehicle Positions endpoint
                if OC_TRANSPO_PRIMARY_KEY:
                    headers["Ocp-Apim-Subscription-Key"] = OC_TRANSPO_PRIMARY_KEY
                else:
                    # Fail gracefully but log for debugging
                    print(
                        "Warning: OC_TRANSPO_PRIMARY_KEY not set; "
                        "OC Transpo GTFS-Realtime requests may fail."
                    )

            response = requests.get(feed_url, headers=headers or None, timeout=10)
            response.raise_for_status()

            vehicles: List[Dict] = []

            # Helper to safely extract from multiple possible key casings
            def _get_first(mapping: Dict, *keys):
                for key in keys:
                    if key in mapping:
                        return mapping[key]
                return None

            # Some feeds (like OC Transpo when using ?format=json) return JSON
            # with the GTFS-Realtime structure instead of raw protobuf.
            content_type = (response.headers.get("Content-Type") or "").lower()
            is_probably_json = "json" in content_type or "format=json" in feed_url.lower()

            if is_probably_json:
                try:
                    data = response.json()
                    entities = data.get("entity") or data.get("Entity") or []

                    for entity in entities:
                        vehicle = entity.get("vehicle") or entity.get("Vehicle")
                        if not vehicle:
                            continue

                        trip = vehicle.get("trip") or vehicle.get("Trip") or {}
                        position = vehicle.get("position") or vehicle.get("Position") or {}
                        descriptor = vehicle.get("vehicle") or vehicle.get("Vehicle") or {}

                        vehicle_data = {
                            "vehicle_id": _get_first(descriptor, "id", "Id"),
                            "trip_id": _get_first(trip, "trip_id", "tripId"),
                            "route_id": _get_first(trip, "route_id", "routeId"),
                            "latitude": _get_first(position, "latitude", "lat", "Latitude"),
                            "longitude": _get_first(position, "longitude", "lon", "Longitude", "lng"),
                            "bearing": _get_first(position, "bearing", "Bearing"),
                            "speed": _get_first(position, "speed", "Speed"),
                            "timestamp": _get_first(vehicle, "timestamp", "Timestamp"),
                            "current_stop_sequence": _get_first(
                                vehicle, "current_stop_sequence", "currentStopSequence"
                            ),
                            "stop_id": _get_first(vehicle, "stop_id", "stopId"),
                            "current_status": _get_first(
                                vehicle, "current_status", "currentStatus"
                            ),
                            "congestion_level": _get_first(
                                vehicle, "congestion_level", "congestionLevel"
                            ),
                            "occupancy_status": _get_first(
                                vehicle, "occupancy_status", "occupancyStatus"
                            ),
                        }
                        vehicles.append(vehicle_data)

                    return vehicles
                except Exception as json_err:
                    # If JSON parsing fails, fall back to protobuf parsing below.
                    print(f"Warning: Failed to parse GTFS-Realtime JSON, falling back to protobuf: {json_err}")

            # Default: parse protobuf GTFS-Realtime feed
            feed = gtfs_realtime_pb2.FeedMessage()
            feed.ParseFromString(response.content)

            for entity in feed.entity:
                if entity.HasField("vehicle"):
                    vehicle = entity.vehicle
                    vehicle_data = {
                        "vehicle_id": vehicle.vehicle.id if vehicle.HasField("vehicle") else None,
                        "trip_id": vehicle.trip.trip_id if vehicle.HasField("trip") else None,
                        "route_id": vehicle.trip.route_id if vehicle.HasField("trip") else None,
                        "latitude": vehicle.position.latitude if vehicle.HasField("position") else None,
                        "longitude": vehicle.position.longitude if vehicle.HasField("position") else None,
                        "bearing": vehicle.position.bearing if vehicle.HasField("position") else None,
                        "speed": vehicle.position.speed if vehicle.HasField("position") else None,
                        "timestamp": vehicle.timestamp if vehicle.HasField("timestamp") else None,
                        "current_stop_sequence": vehicle.current_stop_sequence
                        if vehicle.HasField("current_stop_sequence")
                        else None,
                        "stop_id": vehicle.stop_id if vehicle.HasField("stop_id") else None,
                        "current_status": vehicle.current_status if vehicle.HasField("current_status") else None,
                        "congestion_level": vehicle.congestion_level
                        if vehicle.HasField("congestion_level")
                        else None,
                        "occupancy_status": vehicle.occupancy_status
                        if vehicle.HasField("occupancy_status")
                        else None,
                    }
                    vehicles.append(vehicle_data)

            return vehicles
        except Exception as e:
            print(f"Error fetching GTFS data: {str(e)}")
            return None
    
    def calculate_distance(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """
        Calculate distance between two coordinates using Haversine formula.
        Returns distance in meters.
        """
        R = 6371000  # Earth's radius in meters
        
        phi1 = math.radians(lat1)
        phi2 = math.radians(lat2)
        delta_phi = math.radians(lat2 - lat1)
        delta_lambda = math.radians(lon2 - lon1)
        
        a = math.sin(delta_phi/2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda/2)**2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
        
        return R * c
    
    def find_closest_vehicle(self, route_id: str, stop_lat: float, stop_lon: float, 
                           vehicles: List[Dict]) -> Optional[Dict]:
        """
        Find the closest vehicle for a specific route near a stop.
        
        Args:
            route_id: Route ID to filter vehicles
            stop_lat: Latitude of the stop
            stop_lon: Longitude of the stop
            vehicles: List of all vehicle positions
            
        Returns:
            Closest vehicle data or None
        """
        if not vehicles:
            return None
        
        closest_vehicle = None
        min_distance = float('inf')
        
        for vehicle in vehicles:
            if vehicle.get('route_id') == route_id and vehicle.get('latitude') and vehicle.get('longitude'):
                distance = self.calculate_distance(
                    stop_lat, stop_lon,
                    vehicle['latitude'], vehicle['longitude']
                )
                
                if distance < min_distance:
                    min_distance = distance
                    closest_vehicle = vehicle
                    closest_vehicle['distance_to_stop'] = distance
        
        return closest_vehicle
    
    def estimate_arrival_time(self, vehicle: Dict, stop_lat: float, stop_lon: float) -> Optional[float]:
        """
        Estimate time until vehicle reaches stop based on current position and speed.
        
        Returns:
            Estimated time in minutes, or None if cannot estimate
        """
        if not vehicle or not vehicle.get('latitude') or not vehicle.get('longitude'):
            return None
        
        distance = vehicle.get('distance_to_stop', 0)
        
        # If vehicle has speed data, use it
        if vehicle.get('speed') and vehicle['speed'] > 0:
            # Speed is in m/s, convert to minutes
            time_minutes = (distance / vehicle['speed']) / 60
            return max(0, time_minutes)
        
        # Otherwise, assume average bus speed of 20 km/h in urban areas
        avg_speed_ms = 20000 / 3600  # 20 km/h in m/s
        time_minutes = (distance / avg_speed_ms) / 60
        
        return max(0, time_minutes)
    
    def analyze_routes_with_realtime(self, directions_data: Dict, gtfs_feed_url: Optional[str] = None) -> Dict:
        """
        Analyze routes from Google Maps and enhance with real-time vehicle data.
        
        Args:
            directions_data: Response from Google Maps Directions API
            gtfs_feed_url: URL of GTFS Realtime feed (optional)
            
        Returns:
            Dictionary with analyzed routes and recommendations
        """
        if "error" in directions_data:
            return directions_data
        
        routes = directions_data.get("routes", [])
        if not routes:
            return {"error": "No routes found"}
        
        # Get vehicle positions if feed URL provided
        vehicles = None
        if gtfs_feed_url:
            vehicles = self.get_gtfs_vehicle_positions(gtfs_feed_url)
        
        analyzed_routes = []
        
        for idx, route in enumerate(routes):
            legs = route.get("legs", [])
            if not legs:
                continue
            
            leg = legs[0]  # Usually only one leg for simple origin-destination
            leg_departure_time = leg.get("departure_time", {}) or {}
            
            route_info = {
                "route_number": idx + 1,
                "summary": route.get("summary", ""),
                "duration_text": leg.get("duration", {}).get("text", ""),
                "duration_seconds": leg.get("duration", {}).get("value", 0),
                "distance_text": leg.get("distance", {}).get("text", ""),
                "distance_meters": leg.get("distance", {}).get("value", 0),
                "start_address": leg.get("start_address", ""),
                "end_address": leg.get("end_address", ""),
                "steps": [],
                "estimated_duration_with_realtime": None,
                "realtime_available": False,
                # When you should leave your origin to follow this route
                "departure_time_text": leg_departure_time.get("text"),
                "departure_time_unix": leg_departure_time.get("value"),
            }
            
            total_realtime_duration = 0
            realtime_data_found = False
            
            for step in leg.get("steps", []):
                if step.get("travel_mode") == "TRANSIT":
                    transit_details = step.get("transit_details", {})
                    line = transit_details.get("line", {})
                    step_departure_time = transit_details.get("departure_time", {}) or {}
                    
                    step_info = {
                        "instruction": step.get("html_instructions", ""),
                        "duration": step.get("duration", {}).get("text", ""),
                        "duration_seconds": step.get("duration", {}).get("value", 0),
                        "vehicle_type": line.get("vehicle", {}).get("type", ""),
                        "line_name": line.get("name", ""),
                        "line_short_name": line.get("short_name", ""),
                        "departure_stop": transit_details.get("departure_stop", {}).get("name", ""),
                        "arrival_stop": transit_details.get("arrival_stop", {}).get("name", ""),
                        "num_stops": transit_details.get("num_stops", 0),
                        "realtime_data": None,
                        "departure_time_text": step_departure_time.get("text"),
                        "departure_time_unix": step_departure_time.get("value"),
                    }
                    
                    # Try to find real-time vehicle data
                    if vehicles and line.get("short_name"):
                        dep_stop = transit_details.get("departure_stop", {})
                        if dep_stop.get("location"):
                            stop_lat = dep_stop["location"]["lat"]
                            stop_lon = dep_stop["location"]["lng"]
                            
                            closest_vehicle = self.find_closest_vehicle(
                                line.get("short_name"),
                                stop_lat,
                                stop_lon,
                                vehicles
                            )
                            
                            if closest_vehicle:
                                estimated_arrival = self.estimate_arrival_time(
                                    closest_vehicle, stop_lat, stop_lon
                                )
                                
                                step_info["realtime_data"] = {
                                    "vehicle_id": closest_vehicle.get("vehicle_id"),
                                    "stop_id": closest_vehicle.get("stop_id"),
                                    "distance_to_stop_meters": round(
                                        closest_vehicle.get("distance_to_stop", 0), 1
                                    ),
                                    "estimated_arrival_minutes": round(estimated_arrival, 1)
                                    if estimated_arrival
                                    else None,
                                    "congestion_level": closest_vehicle.get("congestion_level"),
                                    "occupancy_status": closest_vehicle.get("occupancy_status"),
                                }
                                
                                if estimated_arrival:
                                    total_realtime_duration += estimated_arrival * 60  # Convert to seconds
                                    realtime_data_found = True
                    
                    route_info["steps"].append(step_info)
                    
                    if not realtime_data_found:
                        total_realtime_duration += step_info["duration_seconds"]
                else:
                    # Walking or other steps
                    route_info["steps"].append({
                        "instruction": step.get("html_instructions", ""),
                        "duration": step.get("duration", {}).get("text", ""),
                        "duration_seconds": step.get("duration", {}).get("value", 0),
                        "travel_mode": step.get("travel_mode", ""),
                        "distance": step.get("distance", {}).get("text", "")
                    })
                    total_realtime_duration += step.get("duration", {}).get("value", 0)
            
            if realtime_data_found:
                route_info["estimated_duration_with_realtime"] = round(total_realtime_duration / 60, 1)  # In minutes
                route_info["realtime_available"] = True
            
            analyzed_routes.append(route_info)
        
        # Sort routes by estimated duration (preferring real-time data)
        analyzed_routes.sort(key=lambda x: (
            x["estimated_duration_with_realtime"] if x["realtime_available"] 
            else x["duration_seconds"] / 60
        ))
        
        return {
            "routes": analyzed_routes,
            "best_route": analyzed_routes[0] if analyzed_routes else None,
            "realtime_data_available": any(r["realtime_available"] for r in analyzed_routes)
        }
    
    def format_route_summary(self, analysis: Dict) -> str:
        """
        Format the route analysis into a readable summary.
        """
        if "error" in analysis:
            return f"Error: {analysis['error']}"
        
        routes = analysis.get("routes", [])
        if not routes:
            return "No routes found."
        
        summary = []
        summary.append("🚌 Bus Route Options:\n")
        summary.append("=" * 60)
        
        for route in routes:
            route_num = route["route_number"]
            duration_text = route["duration_text"]
            
            summary.append(f"\n📍 Route {route_num}: {route['summary']}")
            summary.append(f"   From: {route['start_address']}")
            summary.append(f"   To: {route['end_address']}")
            summary.append(f"   Distance: {route['distance_text']}")

            # Recommended time to leave origin for this route
            if route.get("departure_time_text"):
                summary.append(
                    f"   Leave your origin at: {route['departure_time_text']} "
                    f"so you have time to walk to the first stop."
                )
            
            if route["realtime_available"]:
                summary.append(f"   ⏱️  Estimated Time (with real-time): {route['estimated_duration_with_realtime']} min")
                summary.append(f"   📊 Scheduled Time: {duration_text}")
            else:
                summary.append(f"   ⏱️  Estimated Time: {duration_text}")
            
            summary.append("\n   Steps:")
            for i, step in enumerate(route["steps"], 1):
                if step.get("vehicle_type"):
                    summary.append(f"   {i}. Take {step['line_name']} ({step['line_short_name']})")
                    summary.append(f"      From: {step['departure_stop']}")
                    summary.append(f"      To: {step['arrival_stop']}")
                    summary.append(f"      Duration: {step['duration']} ({step['num_stops']} stops)")
                    if step.get("departure_time_text"):
                        summary.append(f"      Scheduled departure: {step['departure_time_text']}")
                    
                    if step.get("realtime_data"):
                        rt = step["realtime_data"]
                        if rt.get("estimated_arrival_minutes"):
                            summary.append(f"      🔴 LIVE: Next bus in ~{rt['estimated_arrival_minutes']} min")
                            summary.append(f"      Vehicle: {rt['vehicle_id']} ({rt['distance_to_stop_meters']}m away)")
                        if rt.get("stop_id"):
                            summary.append(f"      Stop number: {rt['stop_id']}")
                else:
                    summary.append(f"   {i}. {step['instruction']} ({step['duration']})")
            
            summary.append("\n" + "-" * 60)
        
        if analysis.get("best_route"):
            best = analysis["best_route"]
            summary.append(f"\n✅ RECOMMENDED: Route {best['route_number']}")
            if best["realtime_available"]:
                summary.append(f"   Fastest option with real-time data: ~{best['estimated_duration_with_realtime']} min")
            else:
                summary.append(f"   Fastest option: {best['duration_text']}")

            # Highlight the first transit boarding stop number, if available
            first_transit_step = None
            for step in best.get("steps", []):
                if step.get("vehicle_type"):
                    first_transit_step = step
                    break
            if first_transit_step and first_transit_step.get("realtime_data"):
                rt = first_transit_step["realtime_data"]
                if rt.get("stop_id"):
                    summary.append(f"   Board at stop number: {rt['stop_id']}")

            # Add a clear, human-readable step-by-step description for the best route.
            summary.append("\nStep-by-step directions for the recommended route:")
            step_index = 1
            for step in best.get("steps", []):
                # Transit leg
                if step.get("vehicle_type"):
                    line_name = step.get("line_short_name") or step.get("line_name") or "the bus"
                    dep_stop = step.get("departure_stop") or "your nearest stop"
                    arr_stop = step.get("arrival_stop") or "your destination stop"
                    duration = step.get("duration") or ""
                    num_stops = step.get("num_stops")
                    num_stops_txt = f" over {num_stops} stops" if isinstance(num_stops, int) and num_stops > 0 else ""
                    dep_time_txt = step.get("departure_time_text")

                    if dep_time_txt:
                        summary.append(
                            f"  {step_index}) From {dep_stop}, take {line_name} at about {dep_time_txt} "
                            f"towards {arr_stop}{num_stops_txt}. This ride takes about {duration}."
                        )
                    else:
                        summary.append(
                            f"  {step_index}) From {dep_stop}, take {line_name} towards {arr_stop}{num_stops_txt}. "
                            f"This ride takes about {duration}."
                        )
                    step_index += 1
                else:
                    # Walking or other non-transit leg
                    duration = step.get("duration") or ""
                    distance = step.get("distance") or ""
                    # html_instructions can be noisy; keep it simple.
                    instruction = step.get("instruction") or "Walk to the next step."
                    summary.append(
                        f"  {step_index}) {instruction} This walk is about {duration} ({distance})."
                    )
                    step_index += 1

        return "\n".join(summary)


def get_bus_route(origin: str, destination: str, gtfs_feed_url: Optional[str] = None) -> str:
    """
    Main function to get bus routes with real-time vehicle position analysis.
    
    Args:
        origin: Starting location (address or "lat,lng")
        destination: Ending location (address or "lat,lng")
        gtfs_feed_url: Optional GTFS Realtime feed URL for your transit agency
        
    Returns:
        Formatted string with route recommendations
        
    Example:
        result = get_bus_route(
            "Times Square, New York", 
            "Central Park, New York",
            "https://api.511.org/transit/vehiclepositions?api_key=YOUR_KEY&agency=SF"
        )
    """
    router = BusRouter()
    
    # Get directions from Google Maps
    directions = router.get_transit_directions(origin, destination)
    
    # Analyze with real-time data if available
    analysis = router.analyze_routes_with_realtime(directions, gtfs_feed_url)
    
    # Format and return summary
    return router.format_route_summary(analysis)


if __name__ == "__main__":
    # Example usage
    print("Bus Router Tool - Example")
    print("=" * 60)
    
    # Test without real-time data
    result = get_bus_route(
        "Union Station, Los Angeles",
        "Santa Monica Pier, Santa Monica"
    )
    print(result)
    
    # To use with real-time data, provide your local GTFS feed:
    # result = get_bus_route(
    #     "Your Origin",
    #     "Your Destination",
    #     "https://your-transit-agency.com/gtfs-realtime/vehicle-positions"
    # )

