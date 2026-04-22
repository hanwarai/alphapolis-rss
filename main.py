import csv
import json
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path

import feedgenerator
from bs4 import BeautifulSoup
from jinja2 import Environment, FileSystemLoader
from playwright.sync_api import Error as PlaywrightError, sync_playwright

ATOM_NS = {'atom': 'http://www.w3.org/2005/Atom'}

USER_AGENT = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
    '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
)
ALPHAPOLIS_BASE = "https://www.alphapolis.co.jp"
FEED_BASE_URL = f"{ALPHAPOLIS_BASE}/manga/official"
FEED_ID_RE = re.compile(r'\d+')
UPTIME_DATE_RE = re.compile(r'(\d{4})\.(\d{1,2})\.(\d{1,2})')
FEEDS_DIR = Path('feeds')
TEMPLATES_DIR = Path('templates')
JST = timezone(timedelta(hours=9))


def fetch_page(context, url):
    """Return the server-rendered HTML for url, WAF-cookie authorized.

    Alphapolis sits behind AWS WAF, which serves a JS challenge page to non-
    browser clients (requests, curl_cffi). A real headless Chromium executes
    the challenge JS and obtains the auth cookie; we then refetch through
    `context.request.get` to get raw HTML (the in-page JSON payload we need
    is consumed and removed from the DOM during SPA hydration, so
    `page.content()` is no good).

    One retry on timeout / nav error.
    """
    for attempt in (1, 2):
        page = context.new_page()
        try:
            page.goto(url, wait_until='domcontentloaded', timeout=30000)
            page.wait_for_selector('#app-official-manga-toc', timeout=30000)
        except PlaywrightError as exc:
            print(f"nav error on {url} (attempt {attempt}): {exc}")
            page.close()
            continue
        page.close()
        try:
            resp = context.request.get(url)
        except PlaywrightError as exc:
            print(f"request error on {url} (attempt {attempt}): {exc}")
            continue
        if resp.ok:
            return resp.text()
        print(f"{resp.status} for {url} (attempt {attempt})")
        if resp.status < 500:
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


def read_existing_feed_title(feed_id):
    """Return the <atom:title> of a pre-existing feeds/{feed_id}.xml, or None."""
    path = FEEDS_DIR / f'{feed_id}.xml'
    if not path.exists():
        return None
    try:
        tree = ET.parse(path)
    except ET.ParseError:
        return None
    title_el = tree.getroot().find('atom:title', ATOM_NS)
    if title_el is None or not title_el.text:
        return None
    return title_el.text.strip()


def render_index(feed_ids, rendered_feeds):
    """Render index.html from freshly-scraped feeds, filling gaps from existing XML.

    If a comic wasn't parsed this run (e.g. a WAF block) but a previously-deployed
    `feeds/{id}.xml` exists, we re-list it using that file's title so the index
    doesn't regress. Order follows feed.csv.
    """
    parsed_title = {f['id']: f['title'] for f in rendered_feeds}
    feeds = []
    for feed_id in feed_ids:
        title = parsed_title.get(feed_id) or read_existing_feed_title(feed_id)
        if title:
            feeds.append({'id': feed_id, 'title': title})
    env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)), autoescape=True)
    template = env.get_template('index.html')
    (FEEDS_DIR / 'index.html').write_text(
        template.render(feeds=feeds),
        encoding='utf-8',
    )


def main():
    FEEDS_DIR.mkdir(exist_ok=True)
    feed_ids = []
    rendered_feeds = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(user_agent=USER_AGENT, locale='ja-JP')
        try:
            with open('feed.csv', encoding='utf-8') as feed_file:
                for row in csv.reader(feed_file):
                    if not row:
                        continue
                    feed_id = row[0]
                    if not FEED_ID_RE.fullmatch(feed_id):
                        print(f"Invalid feed ID: {feed_id!r}, skipping")
                        continue
                    feed_ids.append(feed_id)

                    comics_url = f"{FEED_BASE_URL}/{feed_id}"
                    print(comics_url)

                    html = fetch_page(context, comics_url)
                    if html is None:
                        print(f"Failed to retrieve comics for {feed_id}")
                        continue

                    comic = parse_comic(feed_id, html)
                    if comic is None:
                        continue

                    print(feed_id, comic['title'])
                    rendered_feeds.append({'id': feed_id, 'title': comic['title']})

                    feed = build_atom_feed(comic, comics_url)
                    with open(FEEDS_DIR / f"{feed_id}.xml", 'w', encoding='utf-8') as fp:
                        feed.write(fp, 'utf-8')
        finally:
            browser.close()

    print(f"scraped {len(rendered_feeds)}/{len(feed_ids)} comics this run")
    render_index(feed_ids, rendered_feeds)


if __name__ == '__main__':
    main()
