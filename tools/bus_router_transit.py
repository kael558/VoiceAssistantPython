import os
import json
import requests
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY")
TRANSIT_API_KEY = os.getenv("TRANSIT_API_KEY")
TRANSIT_API_BASE_URL = os.getenv("TRANSIT_API_BASE_URL", "https://api.transit.app")


class TransitRouter:
    """
    Advanced bus routing tool using the Transit API.
    Provides real-time transit directions with built-in real-time updates.
    """
    
    def __init__(self):
        self.google_api_key = GOOGLE_MAPS_API_KEY
        self.transit_api_key = TRANSIT_API_KEY
        self.transit_base_url = TRANSIT_API_BASE_URL
    
    def geocode_address(self, address: str) -> Optional[Tuple[float, float]]:
        """
        Convert an address to lat/lon coordinates using Google Maps Geocoding API.
        
        Args:
            address: Address string to geocode
            
        Returns:
            Tuple of (latitude, longitude) or None if geocoding fails
        """
        # If it's already coordinates, parse and return
        if "," in address:
            try:
                parts = address.split(",")
                if len(parts) == 2:
                    lat = float(parts[0].strip())
                    lon = float(parts[1].strip())
                    return (lat, lon)
            except ValueError:
                pass
        
        # Use Google Maps Geocoding API
        if not self.google_api_key:
            return None
        
        url = "https://maps.googleapis.com/maps/api/geocode/json"
        params = {
            "address": address,
            "key": self.google_api_key
        }
        
        try:


            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            if data.get("status") == "OK" and data.get("results"):
                location = data["results"][0]["geometry"]["location"]
                return (location["lat"], location["lng"])
            
            return None
        except Exception as e:
            print(f"Geocoding error: {str(e)}")
            return None
    
    def get_transit_plan(
        self,
        from_lat: float,
        from_lon: float,
        to_lat: float,
        to_lon: float,
        mode: str = "transit",
        secondary_mode: Optional[str] = None,
        leave_time: Optional[int] = None,
        arrival_time: Optional[int] = None,
        accessibility_need: str = "none",
        walk_reluctance: float = 1.1,
        walk_speed: float = 1.4,
        should_include_directions: bool = True,
        should_update_realtime: bool = True,
        consider_downtimes: bool = True,
        num_result: int = 3,
        max_num_legs: int = 3,
        allowed_modes: Optional[List[str]] = None,
        excluded_modes: Optional[List[str]] = None,
        avoid_routes: Optional[List[str]] = None,
        avoid_stops: Optional[List[str]] = None
    ) -> Dict:
        """
        Get transit directions from the Transit API.
        
        Args:
            from_lat: Starting latitude
            from_lon: Starting longitude
            to_lat: Destination latitude
            to_lon: Destination longitude
            mode: Primary mode (transit, microtransit, personal_bike, walk, shared_mobility)
            secondary_mode: Secondary mode for multimodal trips
            leave_time: UNIX timestamp for departure time
            arrival_time: UNIX timestamp for arrival time
            accessibility_need: none, strict, or prioritize_step_free
            walk_reluctance: How costly walking is vs transit (default 1.1)
            walk_speed: Walking speed in m/s (default 1.4)
            should_include_directions: Include step-by-step directions
            should_update_realtime: Update with real-time data
            consider_downtimes: Avoid known downtimes from service alerts
            num_result: Number of results to return (default 3)
            max_num_legs: Maximum number of transit legs/transfers (default 3)
            allowed_modes: List of allowed mode names (e.g., ["Bus", "Metro"])
            excluded_modes: List of excluded mode names (e.g., ["Ferry"])
            avoid_routes: List of route IDs to avoid (format: "feed_code:global_route_id")
            avoid_stops: List of stop IDs to avoid (format: "feed_code:stable_stop_id")
            
        Returns:
            Dictionary containing trip plan information
        """
        if not self.transit_api_key:
            return {"error": "Transit API key not found in environment variables"}
        
        url = f"{self.transit_base_url}/public/plan"
        
        params = {
            "from_lat": from_lat,
            "from_lon": from_lon,
            "to_lat": to_lat,
            "to_lon": to_lon,
            "mode": mode,
            "accessibility_need": accessibility_need,
            "walk_reluctance": walk_reluctance,
            "walk_speed": walk_speed,
            "should_include_directions": should_include_directions,
            "should_update_realtime": should_update_realtime,
            "consider_downtimes": consider_downtimes,
            "num_result": num_result,
            "max_num_legs": max_num_legs
        }
        
        # Add optional parameters
        if secondary_mode:
            params["secondary_mode"] = secondary_mode
        if leave_time:
            params["leave_time"] = leave_time
        if arrival_time:
            params["arrival_time"] = arrival_time
        if allowed_modes:
            params["allowed_modes"] = ",".join(allowed_modes)
        if excluded_modes:
            params["excluded_modes"] = ",".join(excluded_modes)
        if avoid_routes:
            params["avoid_routes"] = ",".join(avoid_routes)
        if avoid_stops:
            params["avoid_stops"] = ",".join(avoid_stops)
        
        headers = {
            "apiKey": self.transit_api_key
        }
        
        try:


            response = requests.get(url, params=params, headers=headers, timeout=15)
            response.raise_for_status()
            data = response.json()
            
            return data
        except requests.exceptions.HTTPError as e:
            return {"error": f"Transit API HTTP error: {e.response.status_code} - {e.response.text}"}
        except Exception as e:
            return {"error": f"Failed to get transit plan: {str(e)}"}
    
    def format_time(self, unix_timestamp: int) -> str:
        """Format UNIX timestamp to readable time."""
        dt = datetime.fromtimestamp(unix_timestamp)
        return dt.strftime("%I:%M %p")
    
    def format_duration(self, seconds: int) -> str:
        """Format duration in seconds to readable format."""
        if seconds < 60:
            return f"{seconds} sec"
        minutes = seconds // 60
        if minutes < 60:
            return f"{minutes} min"
        hours = minutes // 60
        remaining_mins = minutes % 60
        if remaining_mins > 0:
            return f"{hours}h {remaining_mins}min"
        return f"{hours}h"
    
    def format_distance(self, meters: int) -> str:
        """Format distance in meters to readable format."""
        if meters < 1000:
            return f"{meters}m"
        km = meters / 1000
        return f"{km:.1f}km"
    
    def get_accessibility_emoji(self, accessibility: str) -> str:
        """Get emoji for accessibility status."""
        if accessibility == "WheelchairStrict":
            return "♿ Fully Accessible"
        elif accessibility == "WheelchairTripsWithUnknownStops":
            return "♿⚠️ Mostly Accessible (some stops unknown)"
        return "❌ Not Accessible"
    
    def format_transit_plan_summary(self, plan_data: Dict) -> str:
        """
        Format the transit plan into a concise, bus-focused summary with only the
        most important information for the user.
        """
        if "error" in plan_data:
            return f"Error: {plan_data['error']}"
        
        results = plan_data.get("results", [])
        if not results:
            return "No routes found."
        
        # Always use the first result as the recommended one
        best = results[0]
        legs = best.get("legs", [])
        if not legs:
            return "No legs found in the trip."

        start_time = best.get("start_time")
        end_time = best.get("end_time")
        duration = best.get("duration", 0)

        summary = []
        summary.append("🚌 Transit plan (recommended route)\n")
        summary.append("=" * 70)

        # 1) When to leave home, based on LIVE time for the first bus
        # Find the first/last transit legs and any walking leg before it
        first_transit_idx = None
        last_transit_idx = None
        for i, leg in enumerate(legs):
            if leg.get("leg_mode") == "transit":
                if first_transit_idx is None:
                    first_transit_idx = i
                last_transit_idx = i

        leave_time_unix: Optional[int] = None
        walk_to_first_stop_duration = 0
        first_transit_leg = None
        prev_leg_for_first_transit = None
        recommended_arrival_at_first_stop: Optional[int] = None

        if first_transit_idx is not None:
            first_transit_leg = legs[first_transit_idx]
            if first_transit_idx > 0:
                prev_leg_for_first_transit = legs[first_transit_idx - 1]

        if prev_leg_for_first_transit and prev_leg_for_first_transit.get("leg_mode") in ("walk", "personal_bike"):
            # Use the walking leg's duration so we can compute a better leave time
            leave_time_unix = prev_leg_for_first_transit.get("start_time") or start_time
            walk_to_first_stop_duration = prev_leg_for_first_transit.get("duration", 0)
        else:
            # No explicit walking leg; start from the trip start time
            leave_time_unix = start_time

        # Compute first transit leg live departure info
        first_dep_time = None
        first_vehicle_type = None
        first_line_label = None
        first_headsign = None
        first_dep_stop_name = "Unknown stop"
        first_dep_stop_code = ""
        
        if first_transit_leg:
            vehicle_type, line_label, headsign = self._get_service_label(first_transit_leg)
            first_vehicle_type = vehicle_type
            first_line_label = line_label
            first_headsign = headsign or None

            departures = first_transit_leg.get("departures", [])
            first_departure = departures[0] if departures else {}

            first_dep_time = first_departure.get("departure_time")
            plan_details = first_departure.get("plan_details", {}) if first_departure else {}
            stop_schedule_items = plan_details.get("stop_schedule_items", []) or []
            directions = first_transit_leg.get("directions", [])
            stop_lookup = self._build_stop_lookup(first_transit_leg)
            if stop_schedule_items:
                dep_stop_id = stop_schedule_items[0].get("global_stop_id", "")
                name_code = stop_lookup.get(dep_stop_id)
                if name_code:
                    first_dep_stop_name, first_dep_stop_code = name_code
                else:
                    first_dep_stop_name, first_dep_stop_code = self._extract_stop_info(
                        dep_stop_id, directions, is_departure=True
                    )

            # If we know the live departure time and walking duration, adjust the
            # recommended leave time so you don't wait too long at the stop.
            if first_dep_time and walk_to_first_stop_duration:
                buffer_seconds = 2 * 60  # arrive ~2 minutes before departure
                leave_time_unix = max(
                    start_time or first_dep_time,
                    first_dep_time - walk_to_first_stop_duration - buffer_seconds,
                )
                recommended_arrival_at_first_stop = leave_time_unix + walk_to_first_stop_duration

        # Build "leave home" line
        if leave_time_unix:
            leave_time_str = self.format_time(leave_time_unix)
            walk_txt = ""
            if walk_to_first_stop_duration > 0:
                walk_txt = f" (~{self.format_duration(walk_to_first_stop_duration)})"

            if first_vehicle_type and first_line_label:
                service_label = f"{first_vehicle_type} {first_line_label}"
                if first_headsign:
                    service_label = f"{service_label} | {first_headsign}"
            else:
                service_label = "the transit service"

            stop_label = first_dep_stop_name
            if first_dep_stop_code:
                stop_label = f"{first_dep_stop_name} (stop #{first_dep_stop_code})"

            summary.append(
                f"\n• Leave at {leave_time_str}{walk_txt} to reach {stop_label} "
                f"for {service_label}."
            )

        # 2–4) Sequential trip steps (walking + transit) as a simple numbered list
        summary.append("\n• Trip steps:")
        step_index = 1

        for idx, leg in enumerate(legs):
            leg_mode = leg.get("leg_mode")

            # Walking segments
            if leg_mode == "walk":
                distance_m = int(leg.get("distance") or 0)
                duration_sec = int(leg.get("duration") or 0)
                distance_txt = self.format_distance(distance_m) if distance_m > 0 else ""
                duration_txt = self.format_duration(duration_sec) if duration_sec > 0 else ""

                directions = leg.get("directions") or []

                # Collect all simple walking instructions within this leg
                walk_chunks: List[str] = []
                for step in directions:
                    instr = (step.get("instruction") or "").strip()
                    if instr:
                        walk_chunks.append(instr)

                if not walk_chunks:
                    walk_text = "Walk to the next stop"
                else:
                    # Join sub-directions into a compact phrase
                    walk_text = ", ".join(walk_chunks)

                extra_bits = []
                if distance_txt:
                    extra_bits.append(distance_txt)
                if duration_txt:
                    extra_bits.append(duration_txt)

                if extra_bits:
                    summary.append(f"  {step_index}. {walk_text} (~{', '.join(extra_bits)}).")
                else:
                    summary.append(f"  {step_index}. {walk_text}.")

                step_index += 1

                continue

            # Transit segments
            if leg_mode != "transit":
                continue

            routes = leg.get("routes", [])
            route = routes[0] if routes else {}

            # Build stop lookup for this leg
            stop_lookup = self._build_stop_lookup(leg)

            # Departure information and real-time
            departures = leg.get("departures", [])
            first_departure = departures[0] if departures else {}
            dep_time_live = first_departure.get("departure_time")
            is_realtime = first_departure.get("is_real_time", False)

            # Stops along this leg
            plan_details = first_departure.get("plan_details", {}) if first_departure else {}
            stop_schedule_items = plan_details.get("stop_schedule_items", []) or []
            directions = leg.get("directions", [])

            dep_stop_name = "Unknown stop"
            dep_stop_code = ""
            arr_stop_name = "Unknown stop"
            arr_stop_code = ""
            prev_arr_stop_name = "Unknown stop"
            prev_arr_stop_code = ""

            if stop_schedule_items:
                dep_stop_id = stop_schedule_items[0].get("global_stop_id", "")
                arr_stop_id = stop_schedule_items[-1].get("global_stop_id", "")

                # Use stops list first, then fall back to directions-based extraction
                name_code = stop_lookup.get(dep_stop_id)
                if name_code:
                    dep_stop_name, dep_stop_code = name_code
                else:
                    dep_stop_name, dep_stop_code = self._extract_stop_info(
                        dep_stop_id, directions, is_departure=True
                    )

                name_code = stop_lookup.get(arr_stop_id)
                if name_code:
                    arr_stop_name, arr_stop_code = name_code
                else:
                    arr_stop_name, arr_stop_code = self._extract_stop_info(
                        arr_stop_id, directions, is_departure=False
                    )

                # Prior stop before alighting (if exists)
                if len(stop_schedule_items) >= 2:
                    prev_arr_stop_id = stop_schedule_items[-2].get("global_stop_id", "")
                    name_code = stop_lookup.get(prev_arr_stop_id)
                    if name_code:
                        prev_arr_stop_name, prev_arr_stop_code = name_code
                    else:
                        prev_arr_stop_name, prev_arr_stop_code = self._extract_stop_info(
                            prev_arr_stop_id, directions, is_departure=False
                        )

            # Compute waiting time at boarding stop
            # Find the leg immediately before this transit leg
            prev_leg = None
            for j in range(len(legs)):
                if legs[j] is leg and j > 0:
                    prev_leg = legs[j - 1]
                    break

            arrival_at_stop_time = None
            if prev_leg:
                arrival_at_stop_time = prev_leg.get("end_time")
            if arrival_at_stop_time is None:
                arrival_at_stop_time = start_time

            # For the very first transit leg, base the wait time on the
            # *recommended* leave time rather than the raw planner timing so
            # you don't see a long idle wait at the first stop.
            if idx == first_transit_idx and recommended_arrival_at_first_stop:
                arrival_at_stop_time = recommended_arrival_at_first_stop

            wait_seconds = 0
            if dep_time_live and arrival_at_stop_time:
                wait_seconds = max(0, dep_time_live - arrival_at_stop_time)

            wait_minutes = int(round(wait_seconds / 60)) if wait_seconds else 0
            if wait_minutes <= 0 and wait_seconds > 0:
                wait_str = "<1 min"
            elif wait_minutes > 0:
                wait_str = f"{wait_minutes} min"
            else:
                wait_str = "no wait"

            # Build display strings
            vehicle_type, line_label, headsign = self._get_service_label(leg)
            if vehicle_type and line_label:
                service_label = f"{vehicle_type} {line_label}"
            else:
                service_label = line_label or "transit"
            if headsign:
                service_label = f"{service_label} | {headsign}"

            dep_display = dep_stop_name
            if dep_stop_code:
                dep_display = f"{dep_stop_name} (stop #{dep_stop_code})"

            arr_display = arr_stop_name
            if arr_stop_code:
                arr_display = f"{arr_stop_name}"

            prev_arr_display = prev_arr_stop_name
            if prev_arr_stop_code:
                prev_arr_display = f"{prev_arr_stop_name}"

            dep_time_str = self.format_time(dep_time_live) if dep_time_live else "unknown time"

            # First numbered step for this transit leg: boarding
            summary.append(
                f"  {step_index}. Take {service_label} from {dep_display} "
                f"at {dep_time_str} (wait ~{wait_str})."
            )
            step_index += 1

            # Second numbered step: getting off
            line = f"  {step_index}. Get off at {arr_display}"
            if prev_arr_display != "Unknown stop":
                line += f". Previous stop is {prev_arr_display}"
            line += "."
            summary.append(line)
            step_index += 1

 
        if start_time and end_time:
       

            # Also add a clear "Arrive by" line using the trip end time
            summary.append(f"Arrive by {self.format_time(end_time)}")

        return "\n".join(summary)
    
    def _get_vehicle_emoji(self, mode_name: str) -> str:
        """Get emoji for vehicle type."""
        mode_lower = mode_name.lower()
        if "bus" in mode_lower:
            return "🚌"
        elif "metro" in mode_lower or "subway" in mode_lower:
            return "🚇"
        elif "train" in mode_lower or "rail" in mode_lower:
            return "🚆"
        elif "tram" in mode_lower or "streetcar" in mode_lower:
            return "🚊"
        elif "ferry" in mode_lower:
            return "⛴️"
        elif "cable" in mode_lower:
            return "🚡"
        else:
            return "🚌"
    
    def _get_vehicle_type_label(self, route: Dict) -> str:
        """
        Get a human-friendly vehicle type label like 'bus' or 'O-Train'
        using mode_name / vehicle metadata.
        """
        mode_name = (route.get("mode_name") or "").lower()
        vehicle = route.get("vehicle") or {}
        vehicle_name = (vehicle.get("name") or "").lower()
        text = f"{mode_name} {vehicle_name}"
        
        if "o-train" in text:
            return "O-Train"
        if "train" in text or "rail" in text or "metro" in text or "subway" in text:
            return "train"
        if "tram" in text or "streetcar" in text:
            return "tram"
        if "ferry" in text:
            return "ferry"
        return "bus"
    
    def _build_stop_lookup(self, leg: Dict) -> Dict[str, Tuple[str, str]]:
        """
        Build a lookup from global_stop_id -> (stop_name, stop_code) for a leg
        using the itinerary's stops list.
        """
        lookup: Dict[str, Tuple[str, str]] = {}
        routes = leg.get("routes") or []
        if not routes:
            return lookup
        
        route = routes[0]
        itineraries = route.get("itineraries") or []
        if not itineraries:
            return lookup
        
        itinerary = itineraries[0]
        stops = itinerary.get("stops") or []
        for stop in stops:
            stop_id = stop.get("global_stop_id")
            if not stop_id:
                continue
            name = stop.get("stop_name") or ""
            code = stop.get("stop_code") or ""
            if stop_id not in lookup:
                lookup[stop_id] = (name, code)
        return lookup
    
    def _get_service_label(self, leg: Dict) -> Tuple[str, str, str]:
        """
        Return (vehicle_type, line_label, headsign) for a transit leg.
        
        Example: ("bus", "40", "Greenboro") or ("O-Train", "2", "Bayview")
        """
        routes = leg.get("routes") or []
        route = routes[0] if routes else {}
        
        route_short = route.get("route_short_name")
        route_long = route.get("route_long_name") or route_short or "Transit"
        
        itineraries = route.get("itineraries") or []
        itinerary = itineraries[0] if itineraries else {}
        itin_plan_details = itinerary.get("plan_details") or {}
        
        headsign = (
            itinerary.get("headsign")
            or itinerary.get("direction_headsign")
            or itin_plan_details.get("merged_headsign")
            or itin_plan_details.get("headsign")
        )
        
        vehicle_type = self._get_vehicle_type_label(route)
        line_label = route_short or route_long
        return vehicle_type, line_label, headsign or ""
    
    def _extract_stop_info(self, global_stop_id: str, directions: List[Dict] = None, 
                          is_departure: bool = True) -> Tuple[str, str]:
        """
        Extract stop name and stop code from various sources.
        
        Args:
            global_stop_id: The global stop ID string
            directions: Optional directions array that might contain entrance/exit info
            is_departure: Whether this is a departure stop (True) or arrival stop (False)
            
        Returns:
            Tuple of (stop_name, stop_code)
        """
        stop_name = None
        stop_code = None
        
        # Try to extract from global_stop_id
        # Format is typically "feed_code:stop_id" or "feed_code:stop_id:stop_name"
        if global_stop_id:
            parts = global_stop_id.split(":")
            if len(parts) >= 2:
                stop_code = parts[1]
            if len(parts) >= 3:
                # Some feeds include stop name in global_stop_id
                stop_name = parts[2]
        
        # Try to extract from directions entrance/exit
        if directions:
            for direction in directions:
                if is_departure and "entrance" in direction:
                    entrance = direction["entrance"]
                    if entrance.get("stop_name"):
                        stop_name = entrance["stop_name"]
                    if not stop_code and entrance.get("stop_code"):
                        stop_code = entrance["stop_code"]
                    break
                elif not is_departure and "exit" in direction:
                    exit_info = direction["exit"]
                    if exit_info.get("stop_name"):
                        stop_name = exit_info["stop_name"]
                    if not stop_code and exit_info.get("stop_code"):
                        stop_code = exit_info["stop_code"]
                    break
        
        # Build display name
        if stop_name and stop_code:
            return (stop_name, stop_code)
        elif stop_name:
            return (stop_name, stop_code or "")
        elif stop_code:
            return (f"Stop {stop_code}", stop_code)
        else:
            return ("Unknown stop", "")



def get_transit_route(
    origin: str,
    destination: str,
    mode: str = "transit",
    secondary_mode: Optional[str] = None,
    leave_time: Optional[int] = None,
    arrival_time: Optional[int] = None,
    arrive_by: Optional[str] = None,
    accessibility_need: str = "none",
    minimize_walking: bool = False,
    include_realtime: bool = True,
    avoid_modes: Optional[List[str]] = None,
    only_modes: Optional[List[str]] = None,
    num_results: int = 3
) -> str:
    """
    Main function to get transit routes using the Transit API.
    
    Args:
        origin: Starting location (address or "lat,lng")
        destination: Ending location (address or "lat,lng")
        mode: Primary mode (transit, microtransit, personal_bike, walk, shared_mobility)
        secondary_mode: Secondary mode for multimodal trips
        leave_time: UNIX timestamp for departure time
        arrival_time: UNIX timestamp for arrival time
        arrive_by: Optional arrival time in local time (e.g. "5:30 pm" or "17:30").
        accessibility_need: "none", "strict", or "prioritize_step_free"
        minimize_walking: If True, increases walk reluctance to minimize walking
        include_realtime: If True, includes real-time transit updates
        avoid_modes: List of mode names to avoid (e.g., ["Bus", "Ferry"])
        only_modes: List of mode names to allow (e.g., ["Bus", "Metro"])
        num_results: Number of route alternatives to return
        
    Returns:
        Formatted string with route recommendations
        
    Example:
        result = get_transit_route(
            "Union Station, Ottawa", 
            "Parliament Hill, Ottawa",
            accessibility_need="strict",
            minimize_walking=True
        )
    """
    router = TransitRouter()
    
    # Geocode addresses to coordinates
    origin_coords = router.geocode_address(origin)
    dest_coords = router.geocode_address(destination)
    
    if not origin_coords:
        return f"Error: Could not geocode origin address: {origin}"
    if not dest_coords:
        return f"Error: Could not geocode destination address: {destination}"
    
    from_lat, from_lon = origin_coords
    to_lat, to_lon = dest_coords
    
    # If arrive_by is supplied and arrival_time is not, convert it into a UNIX timestamp.
    if arrival_time is None and arrive_by:
        try:
            now = datetime.now()
            text = arrive_by.strip().lower()
            parsed_time = None
            for fmt in ["%H:%M", "%I:%M %p", "%I %p"]:
                try:
                    parsed_time = datetime.strptime(text, fmt).time()
                    break
                except ValueError:
                    continue
            if parsed_time is not None:
                target = datetime.combine(now.date(), parsed_time)
                if target <= now:
                    target = target + timedelta(days=1)
                arrival_time = int(target.timestamp())
        except Exception:
            pass
    
    # Set walk reluctance based on minimize_walking preference
    walk_reluctance = 2.1 if minimize_walking else 1.1
    
    # Get transit plan
    plan = router.get_transit_plan(
        from_lat=from_lat,
        from_lon=from_lon,
        to_lat=to_lat,
        to_lon=to_lon,
        mode=mode,
        secondary_mode=secondary_mode,
        leave_time=leave_time,
        arrival_time=arrival_time,
        accessibility_need=accessibility_need,
        walk_reluctance=walk_reluctance,
        should_update_realtime=include_realtime,
        num_result=num_results,
        excluded_modes=avoid_modes,
        allowed_modes=only_modes
    )
    
    # Format and return summary
    return router.format_transit_plan_summary(plan)


if __name__ == "__main__":
    # Example usage
    print("Transit Router Tool - Example")
    print("=" * 70)
    
    # Test with basic transit route
    result = get_transit_route(
        "3371 Chilliwack Way, Ottawa, ON",
        "Bayview Yards, Ottawa, ON",
 
    )
    print(result)
    
    # Example with accessibility needs
    # result = get_transit_route(
    #     "Your Origin",
    #     "Your Destination",
    #     accessibility_need="strict",
    #     minimize_walking=True
    # )
    # print(result)
    
    # Example with multimodal (transit + bike)
    # result = get_transit_route(
    #     "Your Origin",
    #     "Your Destination",
    #     mode="transit",
    #     secondary_mode="personal_bike"
    # )
    # print(result)

