# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is an RSS feed generator for Alphapolis manga. It scrapes comic information from alphapolis.co.jp and generates Atom feeds that are published to GitHub Pages.

## Commands

```bash
# Install dependencies
uv sync --all-extras

# Run the feed generator
uv run main.py
```

## Architecture

**Data Flow:**
1. `feed.csv` contains comic IDs (one per line)
2. `main.py` fetches each comic's page from `https://www.alphapolis.co.jp/manga/official/{id}`
3. Parses HTML with BeautifulSoup to extract title, description, and free episodes
4. Generates Atom XML feeds using feedgenerator into `feeds/{id}.xml`
5. Renders `templates/index.html` with Jinja2 to create `feeds/index.html`

**Key Files:**
- `main.py` — Scraper + feed generator. Entry point `main()`; helpers
  `fetch_page`, `parse_comic`, `extract_free_episodes`, `build_atom_feed`,
  `render_index`.
- `feed.csv` — Comic IDs to track
- `templates/index.html` — Jinja2 template for feed listing page

**Deployment:**
- GitHub Actions workflow runs every 12 hours (`.github/workflows/gh-pages.yaml`)
- Output in `feeds/` is deployed to GitHub Pages
- Generated files (`feeds/*.xml`, `feeds/index.html`) are gitignored

## Environment

- Python 3.13 (managed via `uv`)

## Adding a Comic

Append the comic's numeric ID (from `alphapolis.co.jp/manga/official/{id}`) as a
new line in `feed.csv`. Non-digit IDs are skipped with a log line.

## Gotchas

- HTML parsing depends on specific Alphapolis selectors (`h1`, `div.outline`,
  `div.manga-bigbanner`, `div.episode-unit`, `div.free`, `div.title`,
  `div.up-time`). If required elements are missing, the affected comic/episode
  is skipped with a log line — scrapes fail silently per-entry rather than
  aborting the whole run.
- `fetch_page` retries once on 5xx / connection errors; 4xx short-circuits
  (no retry). No exponential backoff.
- Episode timestamps are interpreted as JST (`Asia/Tokyo`, UTC+9).
- Output URLs: `https://hanwarai.github.io/alphapolis-rss/{id}.xml`
