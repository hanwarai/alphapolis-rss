import csv
import re
from datetime import datetime

import feedgenerator
import requests
from bs4 import BeautifulSoup
from jinja2 import Environment, FileSystemLoader

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

rendered_feeds = []
with open('feed.csv') as feed_file:
    for feed in csv.reader(feed_file):
        feed_id = feed[0]

        if not re.fullmatch(r'\d+', feed_id):
            print(f"Invalid feed ID: {feed_id!r}, skipping")
            continue

        comics_url = "https://www.alphapolis.co.jp/manga/official/" + feed_id
        print(comics_url)

        comics = requests.get(comics_url, headers=HEADERS, verify=True, timeout=10)
        if not comics.ok:
            print(f"{comics.status_code} for {feed_id}")
            comics = requests.get(comics_url, headers=HEADERS, verify=True, timeout=10)

        if not comics.ok:
            print(f"Failed to retrieve comics for {feed_id}")
            continue

        soup = BeautifulSoup(comics.text, 'html.parser')

        h1 = soup.find('h1')
        if h1 is None:
            print(f"Failed to parse page for {feed_id} (h1 not found, status={comics.status_code})")
            print(f"Response body (first 500 chars): {comics.text[:500]}")
            continue
        comic_title = h1.text.strip()

        outline = soup.find('div', class_='outline')
        if outline is None:
            print(f"Failed to parse page for {feed_id} (outline not found)")
            continue

        bigbanner = soup.find('div', class_='manga-bigbanner')
        image_url = bigbanner.img.get('src') if bigbanner and bigbanner.img else None

        print(feed_id, comic_title)
        rendered_feeds.append({'id': feed_id, 'title': comic_title})

        rss = feedgenerator.Atom1Feed(
            title=comic_title,
            link=comics_url,
            description=outline.text.strip(),
            language="ja",
            image=image_url
        )

        for episode in soup.find_all('div', class_="episode-unit"):
            if episode.find('div', class_="free") is None:
                continue

            unique_id = episode.get('data-order')
            uptime = episode.find('div', class_="up-time").text.strip()
            pubdate = datetime.strptime(uptime.replace('更新', ''), '%Y.%m.%d')

            rss.add_item(
                unique_id=unique_id,
                title=episode.find('div', class_="title").text.strip(),
                link=comics_url + "/" + unique_id,
                description="",
                pubdate=pubdate,
                content=""
            )

        with open('feeds/' + feed_id + '.xml', 'w') as fp:
            rss.write(fp, 'utf-8')

# Generate index.html
jinja_env = Environment(
    loader=FileSystemLoader('templates'),
    autoescape=True
)
jinja_template = jinja_env.get_template('index.html')
with open('feeds/index.html', 'w') as index:
    index.write(jinja_template.render(feeds=rendered_feeds))
