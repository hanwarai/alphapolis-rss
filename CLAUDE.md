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
- `main.py` - Single-file scraper and feed generator
- `feed.csv` - Comic IDs to track
- `templates/index.html` - Jinja2 template for feed listing page

**Deployment:**
- GitHub Actions workflow runs every 12 hours (`.github/workflows/gh-pages.yaml`)
- Output in `feeds/` is deployed to GitHub Pages
- Generated files (`feeds/*.xml`, `feeds/index.html`) are gitignored

## Environment

- Python 3.13 (managed via `uv`)

## Adding a Comic

Append the comic's numeric ID (from `alphapolis.co.jp/manga/official/{id}`) as a
new line in `feed.csv`. Non-digit IDs are silently skipped (main.py:19).

## Gotchas

- `main.py` runs imperatively at module scope (no functions); edits must
  preserve the top-level flow.
- HTML parsing depends on specific Alphapolis selectors (`h1`, `div.outline`,
  `div.manga-bigbanner`, `div.episode-unit`). If any required element is
  missing the comic is skipped with a log line — broken scrapes fail silently
  per-entry rather than aborting the run.
- Network errors get exactly one retry (main.py:28-29); no exponential backoff.
- Output URLs: `https://hanwarai.github.io/alphapolis-rss/{id}.xml`
