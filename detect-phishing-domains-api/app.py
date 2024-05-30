from flask import jsonify, request, Flask
from flask_cors import CORS
import pandas as pd
from thefuzz import fuzz
import requests
from sklearn.feature_extraction.text import TfidfVectorizer
from PIL import Image
from io import BytesIO
from bs4 import BeautifulSoup
import favicon
import numpy as np

app = Flask(__name__)
CORS(app)

def ensure_http(url):
    if not url.startswith(('http://', 'https://')):
        url = 'http://' + url
    return url

def extract_website_content(url):
    url = ensure_http(url)
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            return response.text
        else:
            print(f"Failed to fetch content from {url}. Status code: {response.status_code}")
            return ''
    except requests.RequestException as e:
        print(f"Error fetching content from {url}: {e}")
        return ''

def calculate_similarity(paragraph1, paragraph2):
    if not paragraph1 or not paragraph2:
        return 0.0
    sentences = [paragraph1, paragraph2]
    vectorizer = TfidfVectorizer()
    try:
        tfidf_matrix = vectorizer.fit_transform(sentences)
        cosine_sim = (tfidf_matrix * tfidf_matrix.T).A
        similarity_percentage = cosine_sim[0, 1] * 100
    except ValueError as e:
        print(f"Error calculating similarity: {e}")
        similarity_percentage = 0.0
    return similarity_percentage

def get_favicon(url):
    url = ensure_http(url)
    try:
        icons = favicon.get(url)
        if not icons:
            return None
        return icons[0].url
    except Exception as e:
        print(f"Error fetching favicon from {url}: {e}")
        return None

def fetch_image(url):
    try:
        response = requests.get(url, stream=True)
        response.raise_for_status()
        return Image.open(BytesIO(response.content))
    except Exception as e:
        print(f"Error fetching image from {url}: {e}")
        return None

def compare_images(image1, image2):
    try:
        image1 = image1.convert('RGB')
        image2 = image2.convert('RGB')
        if image1.size != image2.size:
            image2 = image2.resize(image1.size, Image.ANTIALIAS)
        arr1 = np.array(image1)
        arr2 = np.array(image2)
        mse = np.mean((arr1 - arr2) ** 2)
        max_pixel_value = 255.0
        similarity = 100 - (mse / max_pixel_value * 100)
        return max(0, similarity)
    except Exception as e:
        print(f"Error comparing images: {e}")
        return 0.0

def get_title(url):
    url = ensure_http(url)
    try:
        response = requests.get(url)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
        return soup.title.string.strip() if soup.title else 'No title found'
    except Exception as e:
        print(f"Error fetching title from {url}: {e}")
        return 'No title found'

def compare_titles(title1, title2):
    similarity = fuzz.ratio(title1, title2)
    return similarity

@app.route('/', methods=['POST'])
def detect_phishing():
    file = request.files['file']
    child_domains = file.read().decode('utf-8').splitlines()
    
    parent_data = pd.read_csv("whitelist.csv")
    parent_domains = parent_data['domain'].values

    threshold_ratio = 70
    parent_child_dict = {}

    for parent in parent_domains:
        matching_children = []
        for child in child_domains:
            ratio = fuzz.ratio(parent, child)
            if ratio >= threshold_ratio:
                # Fetch content from parent and child domains
                parent_content = extract_website_content(parent)
                child_content = extract_website_content(child)

                # Calculate text similarity
                content_similarity = calculate_similarity(parent_content, child_content) if parent_content and child_content else 0.0

                # Fetch and compare favicons
                parent_favicon_url = get_favicon(parent)
                child_favicon_url = get_favicon(child)
                favicon_similarity = 0.0
                if parent_favicon_url and child_favicon_url:
                    parent_image = fetch_image(parent_favicon_url)
                    child_image = fetch_image(child_favicon_url)
                    if parent_image and child_image:
                        favicon_similarity = compare_images(parent_image, child_image)

                # Fetch and compare titles
                parent_title = get_title(parent)
                child_title = get_title(child)
                title_similarity = compare_titles(parent_title, child_title) if parent_title and child_title else 0.0

                overall_similarity = (content_similarity + favicon_similarity + title_similarity) / 3

                matching_children.append((child, {
                    'content_similarity': content_similarity,
                    'favicon_similarity': favicon_similarity,
                    'title_similarity': title_similarity,
                    'overall_similarity': overall_similarity
                }))
        
        if matching_children:
            parent_child_dict[parent] = matching_children

    return jsonify(parent_child_dict)

if __name__ == "__main__":
    app.run()