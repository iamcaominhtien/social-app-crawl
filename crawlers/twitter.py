"""Twitter / X profile crawler using browser-context fetch + Playwright."""

import asyncio
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from playwright.async_api import async_playwright

load_dotenv()

from crawlers.base import BaseCrawler
from helpers.rate_limiter import RateLimiter
from models.twitter import PostType, TwitterPost

logger = logging.getLogger(__name__)

# Public bearer token — same across all X web clients, not a secret.
_BEARER_TOKEN = (
    "AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D"
    "1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA"
)

# Features captured from live browser request (April 2026).
_FEATURES: dict[str, bool] = {
    "rweb_video_screen_enabled": False,
    "profile_label_improvements_pcf_label_in_post_enabled": True,
    "responsive_web_profile_redirect_enabled": False,
    "rweb_tipjar_consumption_enabled": False,
    "verified_phone_label_enabled": False,
    "creator_subscriptions_tweet_preview_api_enabled": True,
    "responsive_web_graphql_timeline_navigation_enabled": True,
    "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
    "premium_content_api_read_enabled": False,
    "communities_web_enable_tweet_community_results_fetch": True,
    "c9s_tweet_anatomy_moderator_badge_enabled": True,
    "responsive_web_grok_analyze_button_fetch_trends_enabled": False,
    "responsive_web_grok_analyze_post_followups_enabled": True,
    "responsive_web_jetfuel_frame": True,
    "responsive_web_grok_share_attachment_enabled": True,
    "responsive_web_grok_annotations_enabled": True,
    "articles_preview_enabled": True,
    "responsive_web_edit_tweet_api_enabled": True,
    "graphql_is_translatable_rweb_tweet_is_translatable_enabled": True,
    "view_counts_everywhere_api_enabled": True,
    "longform_notetweets_consumption_enabled": True,
    "responsive_web_twitter_article_tweet_consumption_enabled": True,
    "content_disclosure_indicator_enabled": True,
    "content_disclosure_ai_generated_indicator_enabled": True,
    "responsive_web_grok_show_grok_translated_post": True,
    "responsive_web_grok_analysis_button_from_backend": True,
    "post_ctas_fetch_enabled": True,
    "freedom_of_speech_not_reach_fetch_enabled": True,
    "standardized_nudges_misinfo": True,
    "tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled": True,
    "longform_notetweets_rich_text_read_enabled": True,
    "longform_notetweets_inline_media_enabled": False,
    "responsive_web_grok_image_annotation_enabled": True,
    "responsive_web_grok_imagine_annotation_enabled": True,
    "responsive_web_grok_community_note_auto_translation_is_enabled": True,
    "responsive_web_enhance_cards_enabled": False,
}

_TWITTER_DATE_FORMAT = "%a %b %d %H:%M:%S +0000 %Y"
_MAX_TWEETS = 3_200  # X server-side limit
def _extract_user_id_from_url(url: str) -> str | None:
    """Parse the userId from a UserTweets request URL's variables query param."""
    import json as _json
    from urllib.parse import parse_qs, urlparse
    try:
        qs = parse_qs(urlparse(url).query)
        variables_str = qs.get("variables", [None])[0]
        if variables_str:
            return _json.loads(variables_str).get("userId")
    except Exception:
        pass
    return None


class LoginWallError(RuntimeError):
    """Raised when X redirects to the login page instead of showing the profile."""


def _parse_twitter_date(s: str | None) -> str | None:
    """Parse Twitter legacy date string → ISO-8601 UTC string."""
    if not s:
        return None
    try:
        return datetime.strptime(s, _TWITTER_DATE_FORMAT).isoformat() + "Z"
    except ValueError:
        return s


def _parse_response(data: dict) -> tuple[list[dict], str | None]:
    """Extract tweet legacies and next cursor from a UserTweets GraphQL response."""
    tweets: list[dict] = []
    cursor: str | None = None

    user_result = data.get("data", {}).get("user", {}).get("result", {})
    timeline_obj = user_result.get("timeline_v2") or user_result.get("timeline") or {}
    instructions = timeline_obj.get("timeline", {}).get("instructions", [])

    for instr in instructions:
        for entry in instr.get("entries", []):
            entry_id = entry.get("entryId", "")

            if "cursor-bottom" in entry_id:
                cursor = entry.get("content", {}).get("value")
                continue

            # Replies come as profile-conversation entries with an items array.
            if "profile-conversation-" in entry_id:
                for item in entry.get("content", {}).get("items", []):
                    item_content = item.get("item", {}).get("itemContent", {})
                    result = item_content.get("tweet_results", {}).get("result", {})
                    if not result:
                        continue
                    if result.get("__typename") == "TweetWithVisibilityResults":
                        result = result.get("tweet", {})
                    legacy = result.get("legacy", {})
                    if not legacy:
                        continue
                    _enrich_legacy(legacy, result)
                    tweets.append(legacy)
                continue

            if entry_id.startswith("tweet-"):
                result = (
                    entry.get("content", {})
                    .get("itemContent", {})
                    .get("tweet_results", {})
                    .get("result", {})
                )
                if result.get("__typename") == "TweetWithVisibilityResults":
                    result = result.get("tweet", {})

                legacy: dict = result.get("legacy", {})
                if not legacy:
                    continue

                _enrich_legacy(legacy, result)
                tweets.append(legacy)

    return tweets, cursor


def _enrich_legacy(legacy: dict, result: dict) -> None:
    """Attach author info, views, and repost metadata to a tweet legacy dict."""
    core = result.get("core", {})
    author_legacy = core.get("user_results", {}).get("result", {}).get("legacy", {})
    legacy["_author"] = author_legacy

    views_count = result.get("views", {}).get("count")
    legacy["_views"] = int(views_count) if views_count else None

    rt_result = legacy.get("retweeted_status_result", {})
    if rt_result:
        legacy["_is_repost"] = True
        rt_inner = rt_result.get("result", {})
        if rt_inner.get("__typename") == "TweetWithVisibilityResults":
            rt_inner = rt_inner.get("tweet", {})
        rt_author = (
            rt_inner.get("core", {})
            .get("user_results", {})
            .get("result", {})
            .get("legacy", {})
        )
        legacy["_original_author"] = rt_author
    else:
        legacy["_is_repost"] = False
        legacy["_original_author"] = {}


# JavaScript template executed in the Playwright page context via page.evaluate().
# Uses browser's native fetch so all session cookies and TLS fingerprinting are handled
# -----------------------------------------------------------------------

class TwitterCrawler(BaseCrawler[TwitterPost]):
    """Crawls all posts from a public X/Twitter profile via GraphQL cursor pagination."""

    def __init__(self, rate_limiter: RateLimiter | None = None) -> None:
        super().__init__(rate_limiter or RateLimiter(rate=1.0))  # 1 req/sec

    async def crawl(self, **kwargs: Any) -> list[TwitterPost]:
        """
        Fetch the full timeline of *account* using cursor-paginated GraphQL calls.

        Kwargs:
            account: Twitter/X username (without @).
            output_path: If provided, save JSON to this path.
            limit: Max number of posts to collect (None = no limit).

        Raises:
            LoginWallError: If X shows a login wall.
        """
        account: str = str(kwargs.get("account", ""))
        output_path: str | None = kwargs.get("output_path")
        limit: int | None = kwargs.get("limit")
        effective_limit = min(limit, _MAX_TWEETS) if limit else _MAX_TWEETS

        ct0 = os.getenv("X_CT0", "")
        if not ct0 or not os.getenv("X_AUTH_TOKEN"):
            logger.warning(
                "X_AUTH_TOKEN and X_CT0 not set in .env — crawl will fail"
            )

        # ------------------------------------------------------------------ #
        # Phase A: Bootstrap — navigate to /with_replies, intercept the first
        #   UserTweetsAndReplies XHR to confirm the account exists and grab
        #   the first batch of tweets.
        # Phase B: Scroll-based XHR interception — keep the browser alive,
        #   scroll to the bottom to trigger cursor-paginated XHR calls, and
        #   collect every response until the timeline is exhausted.
        #   The browser sends genuine headers (TLS fingerprint, session cookies,
        #   x-client-transaction-id) — X cannot tell this from normal browsing.
        # ------------------------------------------------------------------ #
        op_id: str | None = None
        user_id: str | None = None
        bootstrap_tweets: list[dict] = []

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            context = await browser.new_context(
                service_workers="block",
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/122.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1280, "height": 900},
            )
            page = await context.new_page()

            auth_token = os.getenv("X_AUTH_TOKEN")
            if auth_token and ct0:
                await context.add_cookies([
                    {
                        "name": "auth_token",
                        "value": auth_token,
                        "domain": ".x.com",
                        "path": "/",
                    },
                    {"name": "ct0", "value": ct0, "domain": ".x.com", "path": "/"},
                ])

            logger.info("Navigating to https://x.com/%s/with_replies (Playwright bootstrap)", account)

            try:
                async with page.expect_response(
                    lambda r: "UserTweetsAndReplies" in r.url or "UserTweets" in r.url,
                    timeout=30_000,
                ) as resp_info:
                    try:
                        await page.goto(
                            f"https://x.com/{account}/with_replies",
                            wait_until="domcontentloaded",
                            timeout=30_000,
                        )
                    except Exception as exc:
                        logger.warning("Navigation error (continuing): %s", exc)

                resp = await resp_info.value
                data = await resp.json()
                bootstrap_tweets, _ = _parse_response(data)

                parts = resp.url.split("/graphql/")
                if len(parts) == 2:
                    op_id = parts[1].split("/")[0]

                uid = (
                    data.get("data", {})
                    .get("user", {})
                    .get("result", {})
                    .get("rest_id")
                ) or _extract_user_id_from_url(resp.url)
                if uid:
                    user_id = uid

                logger.info(
                    "Bootstrap: op_id=%s user_id=%s first_batch=%d",
                    op_id, user_id, len(bootstrap_tweets),
                )

            except Exception as exc:
                logger.error("Playwright bootstrap failed: %s", exc)

            # Detect login wall
            current_url = page.url
            login_form = await page.query_selector(
                '[data-testid="LoginForm"], [data-testid="login"]'
            )
            if "login" in current_url or login_form is not None:
                await browser.close()
                raise LoginWallError(
                    f"X requires authentication to view @{account}. "
                    "Set X_AUTH_TOKEN and X_CT0 in .env "
                    "(export from browser DevTools → Application → Cookies → x.com)"
                )

            if not op_id or not user_id:
                await browser.close()
                raise RuntimeError(
                    "Failed to extract UserTweetsAndReplies operation ID or user ID. "
                    "Check X_AUTH_TOKEN and X_CT0 in .env."
                )

            logger.info(
                "Bootstrap complete — op_id=%s user_id=%s bootstrap_tweets=%d",
                op_id, user_id, len(bootstrap_tweets),
            )

            # ------------------------------------------------------------------ #
            # Phase B: scroll-based XHR interception.
            #
            #   We scroll the page so the real X webapp makes cursor-paginated
            #   XHR calls.  Each call goes through the browser stack (real TLS
            #   fingerprint, fresh x-client-transaction-id) so X cannot tell it
            #   apart from normal browsing.  We intercept every
            #   UserTweetsAndReplies JSON response and collect tweets from it.
            # ------------------------------------------------------------------ #
            all_raw: list[dict] = list(bootstrap_tweets)
            seen_ids: set[str] = {t.get("id_str", "") for t in bootstrap_tweets if t.get("id_str")}
            consecutive_empty = 0
            page_num = 1

            xhr_queue: asyncio.Queue = asyncio.Queue()

            async def _on_xhr_response(response: Any) -> None:
                if "UserTweetsAndReplies" not in response.url and "UserTweets" not in response.url:
                    return
                try:
                    data = await response.json()
                    xhr_queue.put_nowait(data)
                except Exception:
                    pass

            page.on("response", _on_xhr_response)

            while len(all_raw) < effective_limit:
                await self.rate_limiter.acquire()
                logger.info(
                    "Page %d — scrolling (collected=%d)", page_num, len(all_raw)
                )
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")

                try:
                    data = await asyncio.wait_for(xhr_queue.get(), timeout=15.0)
                except asyncio.TimeoutError:
                    logger.info("No XHR after scroll — timeline exhausted")
                    break

                tweets, _ = _parse_response(data)

                new_count = 0
                for tweet in tweets:
                    tid = tweet.get("id_str", "")
                    if tid and tid not in seen_ids:
                        seen_ids.add(tid)
                        all_raw.append(tweet)
                        new_count += 1

                logger.info(
                    "Page %d: +%d new tweets (total=%d)",
                    page_num, new_count, len(all_raw),
                )

                if new_count == 0:
                    consecutive_empty += 1
                    if consecutive_empty >= 3:
                        logger.info("No new tweets after 3 consecutive pages — stopping")
                        break
                else:
                    consecutive_empty = 0

                page_num += 1
                page_num += 1

            await browser.close()

        logger.info("Crawl complete — %d raw tweets fetched for @%s", len(all_raw), account)

        posts = [self.normalize(r, crawled_account=account) for r in all_raw]
        posts = [p for p in posts if p.post_id is not None]
        # Drop tweets from other users that appear as thread context
        posts = [p for p in posts if p.author_username.lower() == account.lower()]

        if output_path:
            self._save_json(posts, output_path)

        return posts

    def normalize(self, raw: dict[str, Any], crawled_account: str = "") -> TwitterPost:  # type: ignore[override]
        is_repost = raw.get("_is_repost", False)
        author_legacy = raw.get("_author", {})
        original_author = raw.get("_original_author", {})

        author_username = author_legacy.get("screen_name") or crawled_account
        author_display_name = author_legacy.get("name") or crawled_account

        orig_handle: str | None = None
        orig_display: str | None = None
        reply_to: str | None = None

        if is_repost:
            orig_handle = original_author.get("screen_name")
            orig_display = original_author.get("name")
        else:
            reply_to = raw.get("in_reply_to_screen_name") or None

        if is_repost:
            post_type = PostType.repost
        elif reply_to:
            post_type = PostType.reply
        else:
            post_type = PostType.original

        id_str = raw.get("id_str")
        post_url = (
            f"https://x.com/{author_username}/status/{id_str}"
            if author_username and id_str
            else ""
        )

        media: list[str] = []
        for m in raw.get("extended_entities", {}).get("media", []):
            url = m.get("media_url_https") or m.get("media_url")
            if url:
                media.append(url)

        date_str = _parse_twitter_date(raw.get("created_at"))

        return TwitterPost(
            post_id=id_str,
            post_type=post_type,
            author_username=author_username,
            author_display_name=author_display_name,
            date=date_str,
            content=raw.get("full_text", ""),
            media_urls=media,
            likes=raw.get("favorite_count"),
            retweets=raw.get("retweet_count"),
            replies=raw.get("reply_count"),
            views=raw.get("_views"),
            post_url=post_url,
            original_author_username=orig_handle,
            original_author_display_name=orig_display,
            reply_to=reply_to,
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
