import json
import os
from datetime import datetime
from typing import List
from tools.wifi_controller import toggle_wifi  # Assuming tools.wifi_controller exists and has toggle_wifi

# Define the base directory for all data files
BASE_DIR = "./data"

# Ensure the base directory exists
os.makedirs(BASE_DIR, exist_ok=True)

# Common file paths
WIFI_STATUS_FILE = os.path.join(BASE_DIR, "wifi_status.json")
NAMES_STATUS_FILE = os.path.join(BASE_DIR, "names_status.json")
LOCATION_FILE = os.path.join(BASE_DIR, "location.json")
ALLOWED_NUMBERS_FILE = os.path.join(BASE_DIR, "allowed_numbers.json")


# --- Common functions for status files ---
def write_status(status):
    """Writes the current WiFi toggle status to a JSON file."""
    try:
        data = {"wifi_toggle_status": status}
        with open(WIFI_STATUS_FILE, "w") as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        print(f"Error writing WiFi status to {WIFI_STATUS_FILE}: {e}")


def read_status():
    """Reads the current WiFi toggle status from a JSON file."""
    try:
        with open(WIFI_STATUS_FILE, "r") as f:
            data = json.load(f)
        return data.get("wifi_toggle_status", "idle")
    except FileNotFoundError:
        write_status("idle")  # Initialize if not found
        return "idle"
    except json.JSONDecodeError as e:
        print(f"JSON decode error in {WIFI_STATUS_FILE}: {e}")
        write_status("idle")  # Reset to default if JSON is corrupt
        return "idle"
    except Exception as e:
        print(f"Error reading WiFi status from {WIFI_STATUS_FILE}: {e}")
        return "idle"


def read_names_status():
    """Reads the authorized names and their toggle states from a JSON file."""
    try:
        with open(NAMES_STATUS_FILE, "r") as f:
            data = json.load(f)
        return data
    except FileNotFoundError:
        # Default names if file not found
        default_data = {
            "names": ["Alice", "Bob", "Charlie", "Diana"],
            "toggles": {"Alice": False, "Bob": False, "Charlie": False, "Diana": False},
        }
        write_names_status(default_data)  # Initialize if not found
        return default_data
    except json.JSONDecodeError as e:
        print(f"JSON decode error in {NAMES_STATUS_FILE}: {e}")
        # Reset to default if JSON is corrupt
        default_data = {
            "names": ["Alice", "Bob", "Charlie", "Diana"],
            "toggles": {"Alice": False, "Bob": False, "Charlie": False, "Diana": False},
        }
        write_names_status(default_data)
        return default_data
    except Exception as e:
        print(f"Error reading names status from {NAMES_STATUS_FILE}: {e}")
        # Return default or empty if other error occurs
        return {
            "names": [],
            "toggles": {},
        }


def write_names_status(data):
    """Writes the authorized names and their toggle states to a JSON file."""
    try:
        with open(NAMES_STATUS_FILE, "w") as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        print(f"Error writing names status to {NAMES_STATUS_FILE}: {e}")


def write_location(location):
    """
    Persist the user's default location to location.json.

    `location` can be a plain string address or a dict. The stored structure is:
      {"address": "<string>", "updated_at": "<ISO8601 UTC>"}
    If a dict is provided, its keys are merged over this base structure.
    """
    try:
        if isinstance(location, str):
            data = {"address": location}
        elif isinstance(location, dict):
            data = dict(location)
        else:
            raise ValueError("location must be a string address or a dict")

        # Always track when we last updated the location
        if "updated_at" not in data:
            data["updated_at"] = datetime.utcnow().isoformat() + "Z"

        with open(LOCATION_FILE, "w") as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        print(f"Error writing location to {LOCATION_FILE}: {e}")


def read_location():
    """
    Read the user's default location from location.json.

    Returns a dict like {"address": "...", "updated_at": "..."} or {} if unavailable.
    """
    try:
        with open(LOCATION_FILE, "r") as f:
            data = json.load(f)
        # Normalize to at least have 'address' key if it's a plain string
        if isinstance(data, str):
            return {"address": data}
        if isinstance(data, dict):
            return data
        return {}
    except FileNotFoundError:
        # No location set yet
        return {}
    except json.JSONDecodeError as e:
        print(f"JSON decode error in {LOCATION_FILE}: {e}")
        return {}
    except Exception as e:
        print(f"Error reading location from {LOCATION_FILE}: {e}")
        return {}


async def handle_wifi_background_task():
    """Background task to toggle WiFi and update status."""
    print("Starting WiFi toggle background task...")
    write_status("toggling")
    try:
        toggle_wifi()  # This function is blocking, so it runs in the background task
        print("WiFi toggle command executed.")
    except Exception as e:
        print(f"Error during WiFi toggle: {e}")
    finally:
        write_status("idle")
        print("WiFi toggle background task finished. Status set to idle.")


def load_allowed_numbers() -> List[str]:
    """Load the list of allowed numbers from the JSON file, seeding with defaults if needed."""
    default_numbers = ['+16138626109', '+16138570911', '+16138570912', '+16139834757', '+16138798396']
    try:
        with open(ALLOWED_NUMBERS_FILE, "r") as f:
            data = json.load(f)
        if isinstance(data, dict):
            numbers = data.get("allowed_numbers", default_numbers)
        elif isinstance(data, list):
            numbers = data
        else:
            numbers = default_numbers
    except FileNotFoundError:
        numbers = default_numbers
        save_allowed_numbers(numbers)
    except json.JSONDecodeError:
        numbers = default_numbers
        save_allowed_numbers(numbers)
    except Exception as e:
        print(f"Error reading allowed numbers from {ALLOWED_NUMBERS_FILE}: {e}")
        numbers = default_numbers
    return numbers


def save_allowed_numbers(numbers: List[str]) -> None:
    """Persist the list of allowed numbers to the JSON file."""
    try:
        data = {"allowed_numbers": sorted(set(numbers))}
        with open(ALLOWED_NUMBERS_FILE, "w") as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        print(f"Error writing allowed numbers to {ALLOWED_NUMBERS_FILE}: {e}")

