import csv
import os
from datetime import datetime

import feedgenerator
import requests
from bs4 import BeautifulSoup
from jinja2 import Environment, FileSystemLoader

SSL_VERIFY = os.getenv('SSL_VERIFY', 'True') == 'True'
feed_file = open('feed.csv')

rendered_feeds = []
for feed in csv.reader(feed_file):
    comics_url = "https://www.alphapolis.co.jp/manga/official/" + feed[0]
    print(comics_url)

    comics = requests.get(comics_url, verify=SSL_VERIFY).text
    if not comics:
        comics = requests.get(comics_url, verify=SSL_VERIFY).text

    if not comics:
        print(f"Failed to retrieve comics for {feed[0]}")
        break

    soup = BeautifulSoup(comics, 'html.parser')

    comic_title = soup.find('h1').text.strip()
    print(feed[0], comic_title)
    rendered_feeds.append({'id': feed[0], 'title': comic_title})

    rss = feedgenerator.Atom1Feed(
        title=comic_title,
        link=comics_url,
        description=soup.find('div', class_='outline').text.strip(),
        language="ja",
        image=soup.find('div', class_='manga-bigbanner').img.get('src')
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

    with open('feeds/' + feed[0] + '.xml', 'w') as fp:
        rss.write(fp, 'utf-8')

# Generate index.html
jinja_env = Environment(
    loader=FileSystemLoader('templates'),
    autoescape=True
)
jinja_template = jinja_env.get_template('index.html')
index = open('feeds/index.html', 'w')
index.write(jinja_template.render(feeds=rendered_feeds))
