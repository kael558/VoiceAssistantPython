import json
import os
import re
from pprint import pprint
import requests
from dotenv import load_dotenv
from enum import Enum

# Load environment variables
load_dotenv()

# Add your Serper API key to your environment variables
api_key = os.getenv("SERPER_API_KEY")
endpoint = "https://google.serper.dev/search"


def search_bing(query):
    """Search using Serper API (formerly Bing Search)"""
    # Construct headers
    headers = {
        'X-API-KEY': api_key,
        'Content-Type': 'application/json'
    }
    
    # Construct request body
    payload = json.dumps({
        "q": query
    })

    # Call the API
    try:
        response = requests.post(endpoint, headers=headers, data=payload)
        response.raise_for_status()

        return handle_search_response(response.json())

    except Exception as ex:
        print(f"Error: {ex}")
        return "Search failed"


def handle_search_response(response):
    web_results = []
    
    # Serper returns organic results in 'organic' field
    for result in response.get('organic', [])[:3]:  # Limit to top 3 results
        title = result.get('title', '')
        snippet = result.get('snippet', '')
        if snippet:
            web_results.append(f"{title}: {snippet}")
    
    if not web_results:
        return "No search results found."
    
    # Return clean, structured data for the LLM to summarize
    return "Search results:\n" + "\n\n".join(web_results)


def handle_image_response(response):
    img_descs = []
    for value in response.get('value', []):
        news = {
            'url': value['hostPageDisplayUrl'],
            'image': value['thumbnailUrl'],
            'desc': value['name'],
            'full_image': value['contentUrl']
        }
        img_descs.append(value['name'])
        print(news)  # Simulate sending a message

    img_desc_str = "Image" + "\nImage: ".join(img_descs[:3])

    return img_desc_str


def handle_video_response(response):
    regex = r'src="([^"]+)"'
    match = re.search(regex, response.get('value', [])[0].get('embedHtml', ''))
    src_value = match.group(1) if match else ''
    value = src_value.split('?')[0] if src_value else ''
    news = {
        'value': value,
        'alt': response.get('value', [])[0].get('name')
    }

    return news


def handle_news_response(response):
    descs = []
    for value in response.get('value', []):
        news = {
            'url': value['url'],
            'title': value['name'],
            'author': value['provider'][0]['name'] if value.get('provider') else 'Unknown',
            'image': value.get('image', {}).get('thumbnail', {}).get('contentUrl'),
            'desc': value['description']
        }
        descs.append(value['description'])
        #print(news)  # Simulate sending a message

    desc_str = "Article" + "\nArticle: ".join(descs[:3])
    return desc_str


if __name__ == "__main__":
    query = "apple inc"

    response = search_bing(query)
    print(response)
