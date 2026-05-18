import os
import requests
from bs4 import BeautifulSoup
from markdownify import markdownify as md
import urllib.parse
import re

BASE_URL = 'https://help.sendit.ma'
START_URL = 'https://help.sendit.ma/fr/'

OUTPUT_DIR = 'sendit_docs'

def sanitize_filename(filename):
    return re.sub(r'[\\/*?:"<>|]', "", filename).strip()

def get_soup(url):
    response = requests.get(url)
    response.raise_for_status()
    return BeautifulSoup(response.content, 'html.parser')

def main():
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)

    print(f"Fetching main page: {START_URL}")
    main_soup = get_soup(START_URL)

    # Find categories
    categories = []
    for a_tag in main_soup.find_all('a', href=True):
        href = a_tag['href']
        if '/fr/collections/' in href:
            full_url = urllib.parse.urljoin(BASE_URL, href)
            if full_url not in categories:
                categories.append(full_url)
    
    print(f"Found {len(categories)} categories.")

    articles_visited = set()
    
    # We might also find standalone articles on the home page
    for a_tag in main_soup.find_all('a', href=True):
        href = a_tag['href']
        if '/fr/articles/' in href:
            full_url = urllib.parse.urljoin(BASE_URL, href)
            articles_visited.add(full_url)

    # Go through each category and find articles
    for i, cat_url in enumerate(categories):
        print(f"Fetching category {i+1}/{len(categories)}: {cat_url}")
        try:
            cat_soup = get_soup(cat_url)
            for a_tag in cat_soup.find_all('a', href=True):
                href = a_tag['href']
                if '/fr/articles/' in href:
                    full_url = urllib.parse.urljoin(BASE_URL, href)
                    articles_visited.add(full_url)
        except Exception as e:
            print(f"Error fetching category {cat_url}: {e}")

    print(f"Found {len(articles_visited)} unique articles.")

    # Scrape each article
    for j, art_url in enumerate(articles_visited):
        print(f"Fetching article {j+1}/{len(articles_visited)}: {art_url}")
        try:
            art_soup = get_soup(art_url)
            
            # Intercom articles typically have a main article body
            # Let's find the main content. Usually it's in a tag like <article> or a specific class.
            article_tag = art_soup.find('article')
            
            if not article_tag:
                # Fallback to some other container if <article> is not present
                print(f"No <article> tag found for {art_url}")
                # We'll try to get the whole body
                article_tag = art_soup.find('body')

            # Find title
            h1 = article_tag.find('h1')
            title = h1.get_text().strip() if h1 else f"article_{j}"

            # Convert to markdown
            # markdownify handles images and text well
            markdown_content = md(str(article_tag), strip=['script', 'style'])
            
            # Prepend URL for reference
            markdown_content = f"# {title}\n\nSource: {art_url}\n\n{markdown_content}"

            filename = f"{j+1:03d}_{sanitize_filename(title)}.md"
            filepath = os.path.join(OUTPUT_DIR, filename)

            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(markdown_content)
                
            print(f"Saved {filepath}")

        except Exception as e:
            print(f"Error processing article {art_url}: {e}")

if __name__ == '__main__':
    main()
