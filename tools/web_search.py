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

class ResponseType(Enum):
    VIDEO = "Videos"
    SEARCHRESPONSE = "SearchResponse"
    IMAGE = "Images"
    NEWS = "News"

def search_bing(query):
    # Construct a request
    mkt = 'en-US'
    params = {'q': query, 'mkt': mkt}
    headers = {'Ocp-Apim-Subscription-Key': subscription_key}

    # Call the API
    try:
        response = requests.get(endpoint, headers=headers, params=params)
        response.raise_for_status()
        return response.json()
    except Exception as ex:
        raise ex
def handle_response(response, response_type):
    if response_type == ResponseType.SEARCHRESPONSE.value:
        handle_search_response(response)
    elif response_type == ResponseType.IMAGE.value:
        handle_image_response(response)
    elif response_type == ResponseType.VIDEO.value:
        handle_video_response(response)
    elif response_type == ResponseType.NEWS.value:
        handle_news_response(response)
    else:
        print("Unknown result type in web search")

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
        print(news)  # Simulate sending a message
    print(f"Role play that you found these results by searching the web:\nPage 1:{web_descs[0]}\nPage 2:{web_descs[1]}\nPage 3:{web_descs[2]}")

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
    print(f"Role play that you found these images by searching the web and comment on them:\nImage 1:{img_descs[0]}\nImage 2:{img_descs[1]}\nImage 3:{img_descs[2]}")

def handle_video_response(response):
    regex = r'src="([^"]+)"'
    match = re.search(regex, response.get('value', [])[0].get('embedHtml', ''))
    src_value = match.group(1) if match else ''
    value = src_value.split('?')[0] if src_value else ''
    news = {
        'value': value,
        'alt': response.get('value', [])[0].get('name')
    }
    print(news)  # Simulate sending a message
    print(f"Role play that you searched and found this web video on your own: ({news['alt']})")

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
        print(news)  # Simulate sending a message
    print(f"Role play that you found these news articles by searching the web:\nArticle 1:{descs[0]}\nArticle 2:{descs[1]}\nArticle 3:{descs[2]}")

if __name__ == "__main__":
    query = "Microsoft Cognitive Services"
    response_type = ResponseType.SEARCHRESPONSE
    response = search_bing(query, response_type)
    handle_response(response, response_type.value)
