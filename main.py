import csv
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import feedgenerator
import requests
from bs4 import BeautifulSoup
from jinja2 import Environment, FileSystemLoader

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
    'Accept-Language': 'ja,en-US;q=0.7,en;q=0.3',
    'Accept-Encoding': 'gzip, deflate, br',
    'DNT': '1',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1',
    'Sec-Fetch-Dest': 'document',
    'Sec-Fetch-Mode': 'navigate',
    'Sec-Fetch-Site': 'none',
    'Sec-Fetch-User': '?1',
}
ALPHAPOLIS_BASE = "https://www.alphapolis.co.jp"
FEED_BASE_URL = f"{ALPHAPOLIS_BASE}/manga/official"
FEED_ID_RE = re.compile(r'\d+')
UPTIME_DATE_RE = re.compile(r'(\d{4})\.(\d{1,2})\.(\d{1,2})')
FEEDS_DIR = Path('feeds')
TEMPLATES_DIR = Path('templates')
JST = timezone(timedelta(hours=9))


def fetch_page(url):
    """GET url with one retry on 5xx / connection errors. Returns Response or None."""
    for attempt in (1, 2):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=10)
        except requests.RequestException as exc:
            print(f"request error on {url} (attempt {attempt}): {exc}")
            continue
        if resp.ok:
            return resp
        print(f"{resp.status_code} for {url} (attempt {attempt})")
        if resp.status_code < 500:
            return None
    return None


def parse_comic(feed_id, html):
    """Return comic dict or None if required page elements are missing."""
    soup = BeautifulSoup(html, 'html.parser')
    h1 = soup.find('h1')
    outline = soup.find('div', class_='outline')
    if h1 is None or outline is None:
        print(f"Failed to parse page for {feed_id} "
              f"(h1={h1 is not None}, outline={outline is not None}, "
              f"html_len={len(html)})")
        print(f"  body[:400]: {html[:400]!r}")
        return None

    bigbanner = soup.find('div', class_='manga-bigbanner')
    image_url = bigbanner.img.get('src') if bigbanner and bigbanner.img else None

    return {
        'title': h1.text.strip(),
        'description': outline.text.strip(),
        'image_url': image_url,
        'episodes': list(extract_free_episodes(soup)),
    }


def extract_free_episodes(soup):
    """Yield episode dicts from the embedded JSON payload.

    Alphapolis renders the episode list client-side; the full list is shipped
    as JSON inside `<div id="app-official-manga-toc"><script type="application/json">`.
    """
    container = soup.find('div', id='app-official-manga-toc')
    if container is None:
        return
    script = container.find('script', type='application/json')
    if script is None or not script.string:
        return
    try:
        data = json.loads(script.string)
    except json.JSONDecodeError as exc:
        print(f"episode JSON decode failed: {exc}")
        return

    for ep in data.get('episodes', []):
        rental = ep.get('rental') or {}
        if not rental.get('isFree'):
            continue

        episode_no = ep.get('episodeNo')
        title = ep.get('mainTitle') or ep.get('shortTitle')
        up_time = ep.get('upTime', '') or ''
        url_path = ep.get('url')
        if episode_no is None or not title or not url_path:
            continue

        date_match = UPTIME_DATE_RE.search(up_time)
        if date_match is None:
            continue
        try:
            pubdate = datetime(
                int(date_match.group(1)),
                int(date_match.group(2)),
                int(date_match.group(3)),
                tzinfo=JST,
            )
        except ValueError:
            continue

        yield {
            'unique_id': str(episode_no),
            'title': title,
            'pubdate': pubdate,
            'link': f"{ALPHAPOLIS_BASE}{url_path}",
        }


def build_atom_feed(comic, comics_url):
    feed = feedgenerator.Atom1Feed(
        title=comic['title'],
        link=comics_url,
        description=comic['description'],
        language='ja',
        image=comic['image_url'],
    )
    for ep in comic['episodes']:
        feed.add_item(
            unique_id=ep['unique_id'],
            title=ep['title'],
            link=ep['link'],
            description="",
            pubdate=ep['pubdate'],
            content="",
        )
    return feed


def render_index(rendered_feeds):
    env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)), autoescape=True)
    template = env.get_template('index.html')
    (FEEDS_DIR / 'index.html').write_text(
        template.render(feeds=rendered_feeds),
        encoding='utf-8',
    )


def main():
    FEEDS_DIR.mkdir(exist_ok=True)
    rendered_feeds = []

    with open('feed.csv', encoding='utf-8') as feed_file:
        for row in csv.reader(feed_file):
            if not row:
                continue
            feed_id = row[0]
            if not FEED_ID_RE.fullmatch(feed_id):
                print(f"Invalid feed ID: {feed_id!r}, skipping")
                continue

            comics_url = f"{FEED_BASE_URL}/{feed_id}"
            print(comics_url)

            resp = fetch_page(comics_url)
            if resp is None:
                print(f"Failed to retrieve comics for {feed_id}")
                continue

            comic = parse_comic(feed_id, resp.text)
            if comic is None:
                continue

            print(feed_id, comic['title'])
            rendered_feeds.append({'id': feed_id, 'title': comic['title']})

            feed = build_atom_feed(comic, comics_url)
            with open(FEEDS_DIR / f"{feed_id}.xml", 'w', encoding='utf-8') as fp:
                feed.write(fp, 'utf-8')

    render_index(rendered_feeds)


if __name__ == '__main__':
    main()
