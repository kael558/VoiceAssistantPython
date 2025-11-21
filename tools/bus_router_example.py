"""
Example usage of the Bus Router Tool

This script demonstrates how to use the bus router to find optimal routes
using both Google Maps and GTFS Realtime data.
"""

from bus_router import get_bus_route


def example_basic_routing():
    """Basic example without real-time data"""
    print("=" * 70)
    print("EXAMPLE 1: Basic Bus Routing (Google Maps only)")
    print("=" * 70)
    
    result = get_bus_route(
         origin="3371 Chilliwack Way, Ottawa, ON",
        destination="Bayview Yards, Ottawa, ON",
    )
    
    print(result)
    print("\n")


def example_with_realtime():
    """Example with GTFS Realtime vehicle positions"""
    print("=" * 70)
    print("EXAMPLE 2: Bus Routing with Real-time Vehicle Positions")
    print("=" * 70)
    
    # Example with LA Metro GTFS feed
    # Note: Replace with your local transit agency's feed URL
    result = get_bus_route(
        origin="3371 Chilliwack Way, Ottawa, ON",
        destination="Bayview Yards, Ottawa, ON",
        gtfs_feed_url="https://nextrip-public-api.azure-api.net/octranspo/gtfs-rt-vp/beta/v1/VehiclePositions"
    )
    
    print(result)
    print("\n")


def example_with_coordinates():
    """Example using GPS coordinates instead of addresses"""
    print("=" * 70)
    print("EXAMPLE 3: Using GPS Coordinates")
    print("=" * 70)
    
    # Downtown LA to Santa Monica
    result = get_bus_route(
        origin="34.0522,-118.2437",
        destination="34.0195,-118.4912"
    )
    
    print(result)
    print("\n")


def example_short_distance():
    """Example for a short distance trip"""
    print("=" * 70)
    print("EXAMPLE 4: Short Distance Trip")
    print("=" * 70)
    
    result = get_bus_route(
        origin="Times Square, New York, NY",
        destination="Central Park, New York, NY"
    )
    
    print(result)
    print("\n")


if __name__ == "__main__":
    print("\n")
    print("🚌 BUS ROUTER TOOL - EXAMPLES 🚌")
    print("\n")
    
    # Run examples
    # Uncomment the examples you want to run
    
    example_basic_routing()
    
    # Uncomment to test with real-time data (requires valid GTFS feed)
    # example_with_realtime()
    
    # example_with_coordinates()
    
    # example_short_distance()
    

