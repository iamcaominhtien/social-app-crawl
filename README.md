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
