"""Twitter / X profile crawler using Playwright async API."""

import asyncio
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


def _extract_post_id(url: str) -> str:
    """Pull the numeric status ID from a tweet URL."""
    match = re.search(r"/status/(\d+)", url or "")
    return match.group(1) if match else url


def _parse_username(url: str | None) -> str:
    """Extract @handle from a profile URL like https://x.com/username."""
    if not url:
        return ""
    match = re.match(r"https?://(?:x|twitter)\.com/([^/?#]+)", url)
    return match.group(1) if match else ""


async def _extract_articles(page: Any) -> list[dict[str, Any]]:
    """Extract all tweet articles from the current page using Playwright Python API."""
    articles = await page.query_selector_all('article[data-testid="tweet"]')
    results = []

    for article in articles:
        # Social context (Pinned / reposted)
        social_el = await article.query_selector('[data-testid="socialContext"]')
        social_text = (await social_el.inner_text()).strip() if social_el else ""
        is_repost = "repost" in social_text.lower()

        # Author name / handle
        user_name_el = await article.query_selector('[data-testid="User-Name"]')
        user_name_text = (await user_name_el.inner_text()).strip() if user_name_el else ""
        # Typical format: "Display Name\n@handle\n·\nDate"
        lines = [l.strip() for l in re.split(r"[\n·]+", user_name_text) if l.strip()]
        display_name = lines[0] if lines else ""
        handle = next((l.lstrip("@") for l in lines if l.startswith("@")), "")

        # Tweet text
        text_el = await article.query_selector('[data-testid="tweetText"]')
        content = (await text_el.inner_text()).strip() if text_el else ""

        # Time + post URL
        time_el = await article.query_selector("time")
        dt = await time_el.get_attribute("datetime") if time_el else None
        time_link_el = await time_el.evaluate_handle("el => el.closest('a')") if time_el else None
        post_url = None
        if time_link_el:
            try:
                post_url = await time_link_el.get_attribute("href")
                if post_url and not post_url.startswith("http"):
                    post_url = "https://x.com" + post_url
            except Exception:
                pass

        # Engagement counters (reply, retweet, like, views — in DOM order)
        counter_els = await article.query_selector_all('[data-testid="app-text-transition-container"]')
        counters = []
        for cel in counter_els:
            txt = (await cel.inner_text()).strip()
            counters.append(txt)

        # Media URLs
        photo_els = await article.query_selector_all('[data-testid="tweetPhoto"] img')
        video_els = await article.query_selector_all("video source")
        media_urls = []
        for img in photo_els:
            src = await img.get_attribute("src")
            if src:
                media_urls.append(src)
        for vid in video_els:
            src = await vid.get_attribute("src")
            if src:
                media_urls.append(src)

        results.append({
            "socialContext": social_text,
            "isRepost": is_repost,
            "displayName": display_name,
            "handle": handle,
            "datetime": dt,
            "postUrl": post_url,
            "content": content,
            "counters": counters,
            "mediaUrls": media_urls,
        })

    return results


class TwitterCrawler(BaseCrawler[TwitterPost]):
    """Crawls all posts and reposts from a public X/Twitter profile."""

    def __init__(self, rate_limiter: RateLimiter | None = None) -> None:
        super().__init__(rate_limiter or RateLimiter(rate=0.5))  # ~1 action per 2s

    async def crawl(self, account: str, output_path: str | None = None, **kwargs) -> list[TwitterPost]:  # type: ignore[override]
        """
        Scroll through the full timeline of *account* and return all posts.

        Args:
            account: Twitter/X username (without @).
            output_path: If provided, save JSON to this path.
        """
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

            # Dismiss cookie/login banners if present
            await asyncio.sleep(2)

            # Check for suspension or empty profile
            page_text = await page.inner_text("body")
            if "Account suspended" in page_text:
                logger.warning("Account @%s is suspended — no posts available.", account)
                await browser.close()
                return []

            stall_count = 0
            max_stalls = 5  # stop if 5 consecutive scrolls yield nothing new

            while stall_count < max_stalls:
                await self.rate_limiter.acquire()

                items: list[dict] = await _extract_articles(page)

                new_count = 0
                for item in items:
                    key = item.get("postUrl") or item.get("content", "")[:80]
                    if key and key not in seen_urls:
                        seen_urls.add(key)
                        item["_crawled_account"] = account
                        raw_items.append(item)
                        new_count += 1

                logger.info("Scroll: +%d new (total %d)", new_count, len(raw_items))

                if new_count == 0:
                    stall_count += 1
                else:
                    stall_count = 0

                # Scroll down
                await page.evaluate("window.scrollBy(0, window.innerHeight * 2)")
                await asyncio.sleep(1.5)

            await browser.close()

        posts = [self.normalize(r) for r in raw_items]

        if output_path:
            self._save_json(posts, output_path)

        return posts

    def normalize(self, raw: dict[str, Any]) -> TwitterPost:  # type: ignore[override]
        account = raw.get("_crawled_account", "")
        is_repost = raw.get("isRepost", False)
        post_url = raw.get("postUrl") or ""
        post_id = _extract_post_id(post_url)

        # Counters: [reply, retweet, like, views]
        counters: list[str] = raw.get("counters", [])

        if is_repost:
            # Card shows the original author; profile owner is the reposter
            original_handle = raw.get("handle", "")
            original_display = raw.get("displayName", "")
            author_username = account
            author_display = account
        else:
            original_handle = None
            original_display = None
            author_username = raw.get("handle", "") or account
            author_display = raw.get("displayName", "") or account

        return TwitterPost(
            post_id=post_id,
            post_type=PostType.repost if is_repost else PostType.original,
            author_username=author_username,
            author_display_name=author_display,
            date=raw.get("datetime"),
            content=raw.get("content", ""),
            media_urls=raw.get("mediaUrls", []),
            replies=_parse_count(counters[0]) if len(counters) > 0 else None,
            retweets=_parse_count(counters[1]) if len(counters) > 1 else None,
            likes=_parse_count(counters[2]) if len(counters) > 2 else None,
            views=_parse_count(counters[3]) if len(counters) > 3 else None,
            post_url=post_url,
            original_author_username=original_handle,
            original_author_display_name=original_display,
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
