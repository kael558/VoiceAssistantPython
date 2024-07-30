import json
import os
import re
from pprint import pprint
import requests
from dotenv import load_dotenv
from enum import Enum

# Load environment variables
load_dotenv()

# Add your Bing Search V7 subscription key and endpoint to your environment variables.
subscription_key = os.getenv("AZURE_BING_API_KEY")
endpoint = "https://api.bing.microsoft.com/v7.0/search"


def search_bing(query):
    # Construct a request
    mkt = 'en-US'
    params = {'q': query, 'mkt': mkt}
    headers = {'Ocp-Apim-Subscription-Key': subscription_key}

    # Call the API
    try:
        response = requests.get(endpoint, headers=headers, params=params)
        response.raise_for_status()

        return handle_search_response(response.json())

    except Exception as ex:
        print(f"Error: {ex}")
        return "Search failed"


def handle_search_response(response):
    web_descs = []
    for value in response.get('webPages', {}).get('value', []):
        news = {
            'url': value['url'],
            'title': value['name'],
            'author': value['displayUrl'],
            'image': value.get('thumbnailUrl'),
            'desc': value['snippet']
        }
        web_descs.append(value['snippet'])
        #print(news)  # Simulate sending a message

    web_desc_str = "WebPage Snippet:" + "\nWebPage Snippet: ".join(web_descs[:5])
    return web_desc_str


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
    query = "Microsoft Cognitive Services"

    response = search_bing(query)
    print(response)
