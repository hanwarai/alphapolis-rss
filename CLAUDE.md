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
- Generated files under `feeds/` are **checked into git** and deployed as-is by
  `.github/workflows/gh-pages.yaml` (push, 12h cron, or `workflow_dispatch`).
- The workflow also runs `uv run main.py` on a best-effort basis, which
  overwrites any feed it can successfully scrape. Failures leave the committed
  feed in place (see the Gotcha on WAF).
- To refresh feeds **manually** (preferred: reliable, uses your residential IP):
  run `uv run main.py` locally and commit + push the updated `feeds/*.xml` and
  `feeds/index.html`.

## Environment

- Python 3.13 (managed via `uv`)

## Adding a Comic

Append the comic's numeric ID (from `alphapolis.co.jp/manga/official/{id}`) as a
new line in `feed.csv`. Non-digit IDs are skipped with a log line.

## Workflow

Single-maintainer project — push directly to `main`. No PR review process.
After editing `main.py`, smoke-test with `uv run python -c "import main"`
before pushing.

## Gotchas

- Comic metadata (`h1`, `div.outline`, `div.manga-bigbanner`) is scraped from
  server-rendered HTML.
- The **episode list is not in the HTML** — Alphapolis ships it as JSON
  inside `<div id="app-official-manga-toc"><script type="application/json">`.
  `extract_free_episodes` parses that payload and filters on
  `rental.isFree == true`. If Alphapolis changes the container id or the
  JSON schema (`episodes[].episodeNo / mainTitle / upTime / url / rental.isFree`),
  all feeds silently emit zero entries.
- If required HTML or JSON elements are missing, the affected comic/episode is
  skipped with a log line — scrapes fail silently per-entry rather than
  aborting the whole run.
- `fetch_page` retries once on 5xx / connection errors; 4xx short-circuits
  (no retry). No exponential backoff.
- Episode timestamps are interpreted as JST (`Asia/Tokyo`, UTC+9).
- Output URLs: `https://hanwarai.github.io/alphapolis-rss/{id}.xml`
- **AWS WAF + Playwright**: Alphapolis sits behind AWS WAF, which serves a
  JS-challenge shell (look for `window.awsWafCookieDomainList` / `gokuProps`)
  to non-browser clients. We bypass it with headless Chromium (Playwright):
  navigate once to let the browser execute the challenge JS and pick up the
  auth cookie, then refetch raw HTML via `context.request.get()` because the
  in-page JSON payload is consumed and removed during SPA hydration (so
  `page.content()` is no good).
- The CI workflow installs Chromium with `uv run playwright install
  --with-deps chromium`. If that ever fails or WAF changes, `main.py` skips
  comics that fail to parse rather than overwriting the committed XML, and
  `render_index` fills the index from committed feed titles.
