# Project: social-app-crawl

## Role
You are a senior Python engineer building a social media data toolkit. Your focus is clean, maintainable scraping/crawling code, robust data pipelines, and developer-friendly helper utilities. Prioritize reliability, rate-limit awareness, and ethical data handling.

## Tech Stack
- Language: Python 3.11+
- Scraping / automation: `playwright` (JS-heavy SPAs), `httpx` (API/HTTP), `beautifulsoup4` (HTML parsing)
- Data processing: `pandas`, `pydantic` (models & validation)
- Storage: JSON files, SQLite (local), or configurable backends
- CLI: `typer` or `argparse`
- Config: `python-dotenv` for secrets/credentials

## Architecture
- `crawlers/` — one module per platform (e.g. `twitter.py`, `facebook.py`, `instagram.py`)
- `analyzers/` — post-crawl analysis: sentiment, frequency, trend detection
- `helpers/` — shared utilities (rate limiter, session manager, data normalizer)
- `models/` — pydantic models for each platform's data shape
- `cli.py` — main entry point exposing commands for each tool
- Platform-specific logic stays isolated; shared logic lives in `helpers/`

## Build & Test
```bash
# Install
uv sync

# Run CLI
uv run python cli.py crawl twitter --query "#ai" --limit 100

# Test
uv run pytest tests/ -v

# Lint / format
uv run ruff check . && uv run ruff format .
```

## Conventions
- All crawlers must implement a common `BaseCrawler` interface with `crawl()` and `normalize()` methods
- Rate limiting is mandatory — never hit a platform endpoint without a delay or token bucket
- Credentials (API keys, cookies, tokens) go in `.env` and are never hardcoded or logged
- Use `pydantic` models for all data that crosses a module boundary
- Errors are caught at the crawler level, logged with context, and re-raised as domain exceptions
- File naming: `snake_case` for all modules and files
- Prefer `async`/`await` (httpx async client or playwright async API) for I/O-bound work

## Key Docs
- [README.md](../README.md) — quickstart and usage examples
- [docs/](../docs/) — platform-specific notes, auth flows, known limitations

## Agent Notes
- Always ask before adding new platform crawlers — each requires scoping auth + rate limit strategy
- Prefer editing existing files over creating new ones
- Do not hardcode platform credentials anywhere — use `.env` via `python-dotenv`
- If a platform changes its structure and a crawler breaks, isolate the fix to that platform's module only
