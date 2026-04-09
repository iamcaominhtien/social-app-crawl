"""Twitter / X profile crawler using Playwright async API."""

import json
import logging
import re
from pathlib import Path
from typing import Any

from playwright.async_api import async_playwright

from crawlers.base import BaseCrawler
from helpers.rate_limiter import RateLimiter
from models.twitter import PostType, TwitterPost

logger = logging.getLogger(__name__)


class LoginWallError(RuntimeError):
    """Raised when X redirects to the login page instead of showing the profile."""


def _parse_count(text: str | None) -> int | None:
    """Convert display strings like '6.2K', '1.3M', '24M' to int."""
    if not text:
        return None
    text = text.strip().replace(",", "")
    if not text or text == "0":
        return 0
    try:
        multipliers = {"K": 1_000, "M": 1_000_000, "B": 1_000_000_000}
        for suffix, mult in multipliers.items():
            if text.upper().endswith(suffix):
                return int(float(text[:-1]) * mult)
        return int(text)
    except (ValueError, AttributeError):
        return None


def _extract_post_id(url: str) -> str | None:
    """Pull the numeric status ID from a tweet URL. Returns None if not found."""
    match = re.search(r"/status/(\d+)", url or "")
    return match.group(1) if match else None


def _parse_username(url: str | None) -> str:
    """Extract @handle from a profile URL like https://x.com/username."""
    if not url:
        return ""
    match = re.match(r"https?://(?:x|twitter)\.com/([^/?#]+)", url)
    return match.group(1) if match else ""


async def _get_button_count(article: Any, testid: str) -> str | None:
    """Get the counter text from a specific action button by its data-testid."""
    el = await article.query_selector(
        f'[data-testid="{testid}"] [data-testid="app-text-transition-container"]'
    )
    if el:
        return (await el.inner_text()).strip()
    return None


async def _extract_articles(page: Any, account: str) -> list[dict[str, Any]]:
    """Extract all tweet articles from the current page using Playwright Python API."""
    articles = await page.query_selector_all('article[data-testid="tweet"]')
    results = []

    for article in articles:
        # Author name / handle — extract first so we can detect reposts structurally
        user_name_el = await article.query_selector('[data-testid="User-Name"]')
        user_name_text = (await user_name_el.inner_text()).strip() if user_name_el else ""
        # Typical format: "Display Name\n@handle\n·\nDate"
        parts = [p.strip() for p in re.split(r"[\n·]+", user_name_text) if p.strip()]
        display_name = parts[0] if parts else ""
        handle = next((p.lstrip("@") for p in parts if p.startswith("@")), "")

        # Repost detection: structural — if the article author differs from the crawled
        # account, the post was created by someone else (i.e. a repost). This is
        # locale-independent and does not rely on translated "reposted" text.
        social_el = await article.query_selector('[data-testid="socialContext"]')
        if handle:
            is_repost = handle.lower() != account.lower()
        else:
            # Fallback when handle could not be parsed: a non-empty socialContext
            # indicates a repost or pinned notice.
            social_text = (await social_el.inner_text()).strip() if social_el else ""
            is_repost = bool(social_text)

        # Tweet text
        text_el = await article.query_selector('[data-testid="tweetText"]')
        content = (await text_el.inner_text()).strip() if text_el else ""

        # Time + post URL
        time_el = await article.query_selector("time")
        dt = await time_el.get_attribute("datetime") if time_el else None

        post_url = None
        if time_el:
            time_link_el = await time_el.evaluate_handle("el => el.closest('a')")
            if time_link_el:
                try:
                    post_url = await time_link_el.get_attribute("href")
                    if post_url and not post_url.startswith("http"):
                        post_url = f"https://x.com{post_url}"
                except Exception:
                    pass

        # Engagement counters — identified by button data-testid to avoid fragile
        # positional ordering that breaks when X changes its DOM structure.
        replies_text = await _get_button_count(article, "reply")
        retweets_text = await _get_button_count(article, "retweet")
        likes_text = await _get_button_count(article, "like")
        views_el = await article.query_selector(
            '[data-testid="analyticsButton"] [data-testid="app-text-transition-container"]'
        )
        views_text = (await views_el.inner_text()).strip() if views_el else None

        # Media URLs
        photo_els = await article.query_selector_all('[data-testid="tweetPhoto"] img')
        video_els = await article.query_selector_all("video source")

        photo_urls = [await img.get_attribute("src") for img in photo_els]
        video_urls = [await vid.get_attribute("src") for vid in video_els]
        media_urls = [url for url in photo_urls + video_urls if url]

        results.append({
            "is_repost": is_repost,
            "display_name": display_name,
            "handle": handle,
            "datetime": dt,
            "post_url": post_url,
            "content": content,
            "replies_text": replies_text,
            "retweets_text": retweets_text,
            "likes_text": likes_text,
            "views_text": views_text,
            "media_urls": media_urls,
        })

    return results


class TwitterCrawler(BaseCrawler[TwitterPost]):
    """Crawls all posts and reposts from a public X/Twitter profile."""

    def __init__(self, rate_limiter: RateLimiter | None = None) -> None:
        super().__init__(rate_limiter or RateLimiter(rate=0.5))  # ~1 action per 2s

    async def crawl(self, **kwargs: Any) -> list[TwitterPost]:
        """
        Scroll through the full timeline of *account* and return all posts.

        Kwargs:
            account: Twitter/X username (without @).
            output_path: If provided, save JSON to this path.
            limit: Max number of posts to collect (None = no limit).

        Raises:
            LoginWallError: If X shows a login wall instead of the profile.
        """
        account: str = str(kwargs.get("account", ""))
        output_path: str | None = kwargs.get("output_path")
        limit: int | None = kwargs.get("limit")
        url = f"https://x.com/{account}"
        raw_items: list[dict[str, Any]] = []
        seen_urls: set[str] = set()


        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/122.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1280, "height": 900},
            )
            page = await context.new_page()

            logger.info("Navigating to %s", url)
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            except Exception as exc:
                logger.warning("Navigation error (continuing): %s", exc)

            # Wait for page to settle before inspecting its state
            await self.rate_limiter.acquire()

            # Detect login wall: check both URL redirect and login form presence.
            # This is locale-independent — does not rely on translated page text.
            current_url = page.url
            login_form = await page.query_selector(
                '[data-testid="LoginForm"], [data-testid="login"]'
            )
            if "login" in current_url or login_form is not None:
                await browser.close()
                raise LoginWallError(
                    f"X requires login to view @{account}. "
                    "Try setting X_COOKIES in your .env file and loading them into the browser context."
                )

            # Check for suspension or empty profile
            page_text = await page.inner_text("body")
            if "Account suspended" in page_text:
                logger.warning("Account @%s is suspended — no posts available.", account)
                await browser.close()
                return []

            stall_count = 0
            max_stalls = 5  # stop after 5 consecutive scrolls with no new posts

            while stall_count < max_stalls:
                items: list[dict[str, Any]] = await _extract_articles(page, account)

                new_count = 0
                for item in items:
                    key = item.get("post_url") or item.get("content", "")[:80]
                    if key and key not in seen_urls:
                        seen_urls.add(key)
                        item["_crawled_account"] = account
                        raw_items.append(item)
                        new_count += 1
                        if limit is not None and len(raw_items) >= limit:
                            break

                logger.info("Scroll: +%d new (total %d)", new_count, len(raw_items))

                if new_count == 0:
                    stall_count += 1
                else:
                    stall_count = 0

                if limit is not None and len(raw_items) >= limit:
                    break

                # Scroll down; rate limiter handles timing between scroll actions
                await page.evaluate("window.scrollBy(0, window.innerHeight * 2)")
                await self.rate_limiter.acquire()

            await browser.close()

        posts = [self.normalize(r) for r in raw_items]
        # Drop any posts where a valid numeric post_id could not be extracted
        posts = [p for p in posts if p.post_id is not None]

        if output_path:
            self._save_json(posts, output_path)

        return posts

    def normalize(self, raw: dict[str, Any]) -> TwitterPost:
        account = raw.get("_crawled_account", "")
        is_repost = raw.get("is_repost", False)
        post_url = raw.get("post_url") or ""

        replies = _parse_count(raw.get("replies_text"))
        retweets = _parse_count(raw.get("retweets_text"))
        likes = _parse_count(raw.get("likes_text"))
        views = _parse_count(raw.get("views_text"))

        orig_handle = orig_display = None
        if is_repost:
            # For reposts the crawled account is the reposter; the article shows the original author
            author_username = author_display = account
            orig_handle = raw.get("handle")
            orig_display = raw.get("display_name")
        else:
            author_username = raw.get("handle") or account
            author_display = raw.get("display_name") or account

        return TwitterPost(
            post_id=_extract_post_id(post_url),
            post_type=PostType.repost if is_repost else PostType.original,
            author_username=author_username,
            author_display_name=author_display,
            date=raw.get("datetime"),
            content=raw.get("content", ""),
            media_urls=raw.get("media_urls", []),
            replies=replies,
            retweets=retweets,
            likes=likes,
            views=views,
            post_url=post_url,
            original_author_username=orig_handle,
            original_author_display_name=orig_display,
        )

    @staticmethod
    def _save_json(posts: list[TwitterPost], path: str) -> None:
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", encoding="utf-8") as f:
            json.dump(
                [p.model_dump(mode="json") for p in posts],
                f,
                indent=2,
                ensure_ascii=False,
            )
        logger.info("Saved %d posts to %s", len(posts), out)
