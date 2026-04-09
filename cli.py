import asyncio
import logging
import re

import typer

from helpers.rate_limiter import RateLimiter

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

_HANDLE_RE = re.compile(r"^[A-Za-z0-9_]{1,50}$")

app = typer.Typer()
crawl_app = typer.Typer(help="Crawl posts from social media platforms.")
app.add_typer(crawl_app, name="crawl")


@crawl_app.command("twitter")
def crawl_twitter(
    account: str = typer.Option(..., "--account", "-a", help="Twitter/X username (without @)"),
    output: str = typer.Option(
        "",
        "--output",
        "-o",
        help="Output JSON file path (default: output/<account>_posts.json)",
    ),
    limit: int = typer.Option(
        0,
        "--limit",
        "-l",
        help="Max number of posts to crawl (0 = no limit)",
    ),
) -> None:
    """Crawl all posts and reposts from a public Twitter/X account."""
    from crawlers.twitter import LoginWallError, TwitterCrawler

    if not _HANDLE_RE.match(account):
        typer.echo(
            "Error: --account must be 1-50 alphanumeric characters or underscores (no @ prefix).",
            err=True,
        )
        raise typer.Exit(code=1)

    output_path = output or f"output/{account.lower()}_posts.json"
    crawler = TwitterCrawler(RateLimiter(rate=0.5))
    post_limit = limit if limit > 0 else None

    typer.echo(f"Crawling @{account} → {output_path}")
    try:
        posts = asyncio.run(crawler.crawl(account=account, output_path=output_path, limit=post_limit))
    except LoginWallError as exc:
        typer.echo(f"\nLogin wall detected: {exc}", err=True)
        raise typer.Exit(code=2)
    typer.echo(f"Done — {len(posts)} posts saved to {output_path}")


if __name__ == "__main__":
    app()
