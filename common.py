import json
import os
from tools.wifi_controller import toggle_wifi # Assuming tools.wifi_controller exists and has toggle_wifi

# Define the base directory for all data files
BASE_DIR = "/home/rahel/Desktop/VoiceAssistantPython"

# Ensure the base directory exists
os.makedirs(BASE_DIR, exist_ok=True)

# --- Common functions for status files ---
def write_status(status):
    """Writes the current WiFi toggle status to a JSON file."""
    try:
        file_path = os.path.join(BASE_DIR, "wifi_status.json")
        data = {"wifi_toggle_status": status}
        with open(file_path, "w") as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        print(f"Error writing WiFi status to {file_path}: {e}")

def read_status():
    """Reads the current WiFi toggle status from a JSON file."""
    file_path = os.path.join(BASE_DIR, "wifi_status.json")
    try:
        with open(file_path, "r") as f:
            data = json.load(f)
        return data.get("wifi_toggle_status", "idle")
    except FileNotFoundError:
        write_status("idle") # Initialize if not found
        return "idle"
    except json.JSONDecodeError as e:
        print(f"JSON decode error in {file_path}: {e}")
        write_status("idle") # Reset to default if JSON is corrupt
        return "idle"
    except Exception as e:
        print(f"Error reading WiFi status from {file_path}: {e}")
        return "idle"

def read_names_status():
    """Reads the authorized names and their toggle states from a JSON file."""
    file_path = os.path.join(BASE_DIR, "names_status.json")
    try:
        with open(file_path, "r") as f:
            data = json.load(f)
        return data
    except FileNotFoundError:
        # Default names if file not found
        default_data = {
            "names": ["Alice", "Bob", "Charlie", "Diana"],
            "toggles": {"Alice": False, "Bob": False, "Charlie": False, "Diana": False}
        }
        write_names_status(default_data) # Initialize if not found
        return default_data
    except json.JSONDecodeError as e:
        print(f"JSON decode error in {file_path}: {e}")
        # Reset to default if JSON is corrupt
        default_data = {
            "names": ["Alice", "Bob", "Charlie", "Diana"],
            "toggles": {"Alice": False, "Bob": False, "Charlie": False, "Diana": False}
        }
        write_names_status(default_data)
        return default_data
    except Exception as e:
        print(f"Error reading names status from {file_path}: {e}")
        # Return default or empty if other error occurs
        return {
            "names": [],
            "toggles": {}
        }

def write_names_status(data):
    """Writes the authorized names and their toggle states to a JSON file."""
    try:
        file_path = os.path.join(BASE_DIR, "names_status.json")
        with open(file_path, "w") as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        print(f"Error writing names status to {file_path}: {e}")

async def handle_wifi_background_task():
    """Background task to toggle WiFi and update status."""
    print("Starting WiFi toggle background task...")
    write_status("toggling")
    try:
        toggle_wifi() # This function is blocking, so it runs in the background task
        print("WiFi toggle command executed.")
    except Exception as e:
        print(f"Error during WiFi toggle: {e}")
    finally:
        write_status("idle")
        print("WiFi toggle background task finished. Status set to idle.")
