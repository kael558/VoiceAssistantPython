import requests
from dotenv import load_dotenv
import os

# Load environment variables from a .env file
load_dotenv()



# Replace 'your_api_key' with your actual SERP API key
API_KEY = os.getenv('SERP_API_KEY')
SEARCH_ENGINE = 'google'
QUERY = 'Python programming'

# Endpoint for the SERP API
url = f'https://serpapi.com/search.json'

# Parameters for the API request
params = {
    'engine': SEARCH_ENGINE,
    'q': QUERY,
    'api_key': API_KEY,
}

# Make the request to the SERP API
response = requests.get(url, params=params)

# Check if the request was successful
if response.status_code == 200:
    results = response.json()
    # Print the results
    print(results)
    # Optionally, you can process the results further here
    for result in results.get('organic_results', []):
        print(f"Title: {result.get('title')}")
        print(f"Link: {result.get('link')}")
        print(f"Snippet: {result.get('snippet')}\n")
else:
    print(f"Error: {response.status_code}")
    print(response.json())

