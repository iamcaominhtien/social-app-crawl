# social-app-crawl

A social media data toolkit for scraping, crawling, and analyzing posts and profiles across platforms.

## Install

```bash
uv sync
```

## Run

```bash
uv run python cli.py
```

Example:

```bash
uv run python cli.py crawl twitter --query "#ai" --limit 100
```

## Test

```bash
uv run pytest tests/ -v
```

## Lint

```bash
uv run ruff check .
```

## Project Structure

```
crawlers/      — one module per platform
analyzers/     — post-crawl analysis (sentiment, trends)
helpers/       — shared utilities (rate limiter, session manager)
models/        — pydantic models for each platform's data
storage/       — pluggable storage backends (JSON, SQLite)
tests/         — test suite
cli.py         — main entry point
```

## Configuration

Copy `.env.example` to `.env` and fill in your credentials:

```bash
cp .env.example .env
```

## X (Twitter) Authentication

X requires login to view profiles. You must export your session cookies from a browser where you are logged in to x.com.

**How to get your X session cookies:**

1. Open Chrome and log in to [x.com](https://x.com)
2. Open DevTools (`F12` or `Cmd+Option+I`)
3. Go to **Application → Storage → Cookies → https://x.com**
4. Find and copy these two cookie values:
   - `auth_token` → set as `X_AUTH_TOKEN` in your `.env`
   - `ct0` → set as `X_CT0` in your `.env`

```env
X_AUTH_TOKEN=your_auth_token_here
X_CT0=your_ct0_token_here
```

> **Never share or commit your cookie values.** They grant full access to your X account.
