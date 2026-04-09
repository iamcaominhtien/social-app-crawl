import typer

app = typer.Typer()


@app.command()
def crawl(
    platform: str = typer.Argument(..., help="Platform to crawl (e.g. twitter, instagram)"),
    query: str = typer.Option("", "--query", "-q", help="Search query or hashtag"),
    limit: int = typer.Option(100, "--limit", "-n", help="Max number of items to fetch"),
) -> None:
    """Crawl posts from a social media platform."""
    typer.echo("Not implemented yet")


if __name__ == "__main__":
    app()
