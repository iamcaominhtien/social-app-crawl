import asyncio
import logging

import typer

from helpers.rate_limiter import RateLimiter

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

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
) -> None:
    """Crawl all posts and reposts from a public Twitter/X account."""
    from crawlers.twitter import TwitterCrawler

    output_path = output or f"output/{account.lower()}_posts.json"
    crawler = TwitterCrawler(RateLimiter(rate=0.5))

    typer.echo(f"Crawling @{account} → {output_path}")
    posts = asyncio.run(crawler.crawl(account=account, output_path=output_path))
    typer.echo(f"Done — {len(posts)} posts saved to {output_path}")


if __name__ == "__main__":
    app()
