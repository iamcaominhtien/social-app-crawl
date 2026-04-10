"""Twitter / X profile crawler using httpx GraphQL + Playwright for bootstrap."""

import asyncio
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
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

_FEATURES: dict[str, bool] = {
    "rweb_lists_timeline_redesign_enabled": True,
    "responsive_web_graphql_exclude_directive_enabled": True,
    "verified_phone_label_enabled": False,
    "creator_subscriptions_tweet_preview_api_enabled": True,
    "responsive_web_graphql_timeline_navigation_enabled": True,
    "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
    "tweetypie_unmention_optimization_enabled": True,
    "responsive_web_edit_tweet_api_enabled": True,
    "graphql_is_translatable_rweb_tweet_is_translatable_enabled": True,
    "view_counts_everywhere_api_enabled": True,
    "longform_notetweets_consumption_enabled": True,
    "responsive_web_twitter_article_tweet_consumption_enabled": False,
    "tweet_awards_web_tipping_enabled": False,
    "freedom_of_speech_not_reach_the_voters": True,
    "standardized_nudges_misinfo": True,
    "tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled": True,
    "longform_notetweets_rich_text_read_enabled": True,
    "longform_notetweets_inline_media_enabled": True,
    "responsive_web_media_download_video_enabled": False,
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
    # Support both timeline_v2 (withV2Timeline=true) and legacy timeline
    timeline_obj = user_result.get("timeline_v2") or user_result.get("timeline") or {}
    instructions = timeline_obj.get("timeline", {}).get("instructions", [])

    for instr in instructions:
        for entry in instr.get("entries", []):
            entry_id = entry.get("entryId", "")

            if "cursor-bottom" in entry_id:
                cursor = entry.get("content", {}).get("value")
                continue

            # Replies in UserTweetsAndReplies come as profile-conversation entries
            # containing an items array of tweets in the thread.
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
                    core = result.get("core", {})
                    author_legacy = (
                        core.get("user_results", {})
                        .get("result", {})
                        .get("legacy", {})
                    )
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
                    tweets.append(legacy)
                continue

            if entry_id.startswith("tweet-"):
                result = (
                    entry.get("content", {})
                    .get("itemContent", {})
                    .get("tweet_results", {})
                    .get("result", {})
                )
                # Unwrap visibility wrapper
                if result.get("__typename") == "TweetWithVisibilityResults":
                    result = result.get("tweet", {})

                legacy: dict = result.get("legacy", {})
                if not legacy:
                    continue

                core = result.get("core", {})
                author_legacy = (
                    core.get("user_results", {})
                    .get("result", {})
                    .get("legacy", {})
                )
                legacy["_author"] = author_legacy

                # Views
                views_count = result.get("views", {}).get("count")
                legacy["_views"] = int(views_count) if views_count else None

                # Detect repost: retweeted_status_result present in legacy
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

                tweets.append(legacy)

    return tweets, cursor


def _build_headers(ct0: str, cookie_override: str | None = None) -> dict[str, str]:
    auth_token = os.getenv("X_AUTH_TOKEN", "")
    cookie = cookie_override or f"ct0={ct0}; auth_token={auth_token}"
    return {
        "authorization": f"Bearer {_BEARER_TOKEN}",
        "cookie": cookie,
        "x-csrf-token": ct0,
        "x-twitter-active-user": "yes",
        "x-twitter-auth-type": "OAuth2Session",
        "content-type": "application/json",
        "user-agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36"
        ),
    }


async def _fetch_page(
    client: httpx.AsyncClient,
    op_id: str,
    user_id: str,
    ct0: str,
    cursor: str | None = None,
    endpoint_name: str = "UserTweetsAndReplies",
    features_json: str | None = None,
    api_base_url: str = "https://api.x.com/graphql/",
    variables_template: dict | None = None,
    cookie_override: str | None = None,
) -> tuple[list[dict], str | None]:
    """Single paginated httpx call to a UserTweets* GraphQL endpoint."""
    if variables_template:
        variables = dict(variables_template)
        variables["count"] = 40
    else:
        variables = {
            "userId": user_id,
            "count": 40,
            "includePromotedContent": True,
            "withQuickPromoteEligibilityTweetFields": True,
            "withVoice": True,
            "withV2Timeline": True,
        }
    if cursor:
        variables["cursor"] = cursor
    else:
        variables.pop("cursor", None)

    params = {
        "variables": json.dumps(variables, separators=(",", ":")),
        "features": features_json or json.dumps(_FEATURES, separators=(",", ":")),
        "fieldToggles": json.dumps({"withArticlePlainText": False}, separators=(",", ":")),
    }

    url = f"{api_base_url}{op_id}/{endpoint_name}"
    response = await client.get(url, params=params, headers=_build_headers(ct0, cookie_override))
    response.raise_for_status()
    return _parse_response(response.json())


class TwitterCrawler(BaseCrawler[TwitterPost]):
    """Crawls all posts from a public X/Twitter profile via GraphQL cursor pagination."""

    def __init__(self, rate_limiter: RateLimiter | None = None) -> None:
        super().__init__(rate_limiter or RateLimiter(rate=1.0))  # 1 req/sec

    async def crawl(self, **kwargs: Any) -> list[TwitterPost]:
        """
        Fetch the full timeline of *account* using httpx GraphQL pagination.

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
                "X_AUTH_TOKEN and X_CT0 not set in .env — crawl may fail due to login wall"
            )

        # ------------------------------------------------------------------ #
        # Phase 1: Playwright bootstrap
        #   - Navigate to /with_replies (triggers UserTweetsAndReplies)
        #   - Intercept first response to extract op_id, user_id, first batch
        # ------------------------------------------------------------------ #
        op_id: str | None = None
        user_id: str | None = None
        endpoint_name: str = "UserTweetsAndReplies"
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

            # Inject session cookies before navigating
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

            seen_graphql_urls: list[str] = []

            async def _log_graphql(response: Any) -> None:
                if "graphql" in response.url.lower():
                    seen_graphql_urls.append(response.url)

            page.on("response", _log_graphql)

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
                tweets, _ = _parse_response(data)

                parts = resp.url.split("/graphql/")
                if len(parts) == 2:
                    op_id = parts[1].split("/")[0]
                    endpoint_name = parts[1].split("/")[1].split("?")[0]

                uid = (
                    data.get("data", {})
                    .get("user", {})
                    .get("result", {})
                    .get("rest_id")
                )
                if not uid:
                    uid = _extract_user_id_from_url(resp.url)
                if uid:
                    user_id = uid

                bootstrap_tweets = tweets
                logger.info("Intercepted %s response: op_id=%s user_id=%s", endpoint_name, op_id, user_id)

            except Exception as exc:
                logger.warning("expect_response failed: %s", exc)
                try:
                    await page.goto(
                        f"https://x.com/{account}/with_replies",
                        wait_until="domcontentloaded",
                        timeout=30_000,
                    )
                except Exception as nav_exc:
                    logger.warning("Navigation error (fallback): %s", nav_exc)

                captured: list[dict] = []
                captured_url: list[str] = []

                async def _capture(response: Any) -> None:
                    if ("UserTweetsAndReplies" in response.url or "UserTweets" in response.url) and not captured:
                        try:
                            body = await response.text()
                            import json as _json
                            captured.append(_json.loads(body))
                            captured_url.append(response.url)
                        except Exception:
                            pass

                page.on("response", _capture)
                await page.evaluate("window.scrollBy(0, 600)")
                await page.wait_for_timeout(8_000)

                if captured:
                    data = captured[0]
                    tweets, _ = _parse_response(data)
                    parts = captured_url[0].split("/graphql/")
                    if len(parts) == 2:
                        op_id = parts[1].split("/")[0]
                        endpoint_name = parts[1].split("/")[1].split("?")[0]
                    uid = (
                        data.get("data", {})
                        .get("user", {})
                        .get("result", {})
                        .get("rest_id")
                    ) or _extract_user_id_from_url(captured_url[0])
                    if uid:
                        user_id = uid
                    bootstrap_tweets = tweets
                else:
                    logger.error(
                        "No UserTweetsAndReplies/UserTweets intercepted. Seen graphql URLs: %s",
                        seen_graphql_urls[:10],
                    )

            # Detect login wall after navigation
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
                    "Failed to extract UserTweetsAndReplies operation ID or user ID from "
                    "Playwright intercept. Check your cookies in .env."
                )

            logger.info(
                "Bootstrap complete — endpoint=%s op_id=%s user_id=%s tweets_in_first_batch=%d",
                endpoint_name,
                op_id,
                user_id,
                len(bootstrap_tweets),
            )

            # ------------------------------------------------------------------ #
            # Phase 2: scroll-based interception
            # Scroll the page to trigger X's infinite-scroll; intercept each new
            # UserTweetsAndReplies response via a queue. This avoids all manual
            # HTTP calls, which fail due to X's bot/TLS fingerprinting.
            # ------------------------------------------------------------------ #
            all_raw: list[dict] = list(bootstrap_tweets)
            seen_ids: set[str] = {t.get("id_str", "") for t in bootstrap_tweets}

            response_queue: asyncio.Queue = asyncio.Queue()

            async def _enqueue_timeline(response: Any) -> None:
                if "UserTweetsAndReplies" in response.url or "UserTweets" in response.url:
                    try:
                        body_data = await response.json()
                        await response_queue.put(body_data)
                    except Exception:
                        pass

            page.on("response", _enqueue_timeline)

            consecutive_empty = 0
            page_num = 1

            while len(all_raw) < effective_limit:
                await self.rate_limiter.acquire()
                logger.info(
                    "Scroll %d — collected %d so far", page_num, len(all_raw)
                )
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")

                try:
                    body_data = await asyncio.wait_for(response_queue.get(), timeout=15.0)
                except asyncio.TimeoutError:
                    logger.info("No new timeline response after scroll — stopping")
                    break

                tweets, _ = _parse_response(body_data)
                new_count = 0
                for tweet in tweets:
                    tid = tweet.get("id_str", "")
                    if tid and tid not in seen_ids:
                        seen_ids.add(tid)
                        all_raw.append(tweet)
                        new_count += 1

                logger.info("Scroll %d: +%d new tweets (total %d)", page_num, new_count, len(all_raw))

                if new_count == 0:
                    consecutive_empty += 1
                    if consecutive_empty >= 3:
                        logger.info("No new tweets after 3 consecutive scrolls — stopping")
                        break
                else:
                    consecutive_empty = 0

                page_num += 1

            await browser.close()

        logger.info("Crawl complete — %d raw tweets fetched for @%s", len(all_raw), account)

        posts = [self.normalize(r, crawled_account=account) for r in all_raw]
        posts = [p for p in posts if p.post_id is not None]
        # Drop tweets from other users that appeared as thread context
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
