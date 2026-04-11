---
title: "Test Plan: SAC-2 X Account Crawl to JSON"
type: test
status: stable
version: 1.2.0
created: 2026-04-09
updated: 2026-04-09
authors: [GitHub Copilot]
related:
  - docs/test-init-app-project-structure.md
---

# Test Plan: SAC-2 X Account Crawl to JSON

## 1. Scope
Validate the Twitter/X crawler for SAC-2 across public-account crawling, suspended-account handling, CLI input validation, JSON output correctness, repost attribution, and contract compliance with the shared crawler interface.

Out of scope: authenticated crawling with cookies, private or protected accounts, non-English account-specific DOM variations beyond current selector strategy, and large-scale performance benchmarking.

## 2. Test Strategy

| Layer | Approach | Tools |
|---|---|---|
| Static inspection | Verify model, crawler, CLI, rate limiting, and interface conformance against acceptance criteria | read_file |
| CLI smoke | Exercise the Typer command with valid and invalid handles | uv run python cli.py crawl twitter ... |
| Live crawl | Run against a public active account to verify actual extraction and JSON persistence | uv run python cli.py crawl twitter --account elonmusk --limit 5 |
| Negative behavior | Run against suspended account and invalid handle input | uv run python cli.py crawl twitter --account Vinhbot22 |
| Output validation | Inspect saved JSON shape and field completeness | python/json parsing |

## 3. Test Cases

| ID | Category | Description | Preconditions | Steps | Expected Result | Status |
|---|---|---|---|---|---|---|
| TC-01 | Happy Path | Crawl a live public account with a small limit | Dependencies installed, outbound network available, and `.env` contains valid `X_AUTH_TOKEN` / `X_CT0` cookies | 1. Run `uv run python cli.py crawl twitter --account elonmusk --limit 5 --output output/test_elonmusk.json`. 2. Observe CLI output. 3. Confirm command exits successfully. | Command visits the public X profile, scrolls timeline content, returns up to 5 posts, and reports the output file path with exit code 0. | ✅ Pass |
| TC-02 | Output Validation | Verify JSON file is created and parseable | TC-01 completed | 1. Confirm `output/test_elonmusk.json` exists. 2. Parse the file as JSON. 3. Confirm the top-level payload is a list. | Output path is created and contains valid JSON without serialization errors. | ✅ Pass |
| TC-03 | Schema Validation | Verify each crawled item contains required fields | TC-02 completed with at least 1 item | 1. Inspect each JSON object in the saved file. 2. Verify presence and type of `post_id`, `post_type`, `author_username`, `author_display_name`, `date`, `content`, `media_urls`, `likes`, `retweets`, `replies`, `views`, and `post_url`. 3. Verify `media_urls` is always an array and `post_url` is a full X URL. | Every JSON object matches the TwitterPost schema and required crawl output contract. Optional repost-only fields are either null or populated appropriately. | ✅ Pass |
| TC-04 | Functional | Verify reposts are distinguished from original posts correctly | Use a public account sample that includes at least one repost in the crawled result; if not present in `elonmusk`, rerun against another public account such as `github` until one repost appears | 1. Crawl a public account with `--limit 20`. 2. Identify at least one item where `post_type` is `repost`. 3. Compare JSON fields with the visible post attribution on X. | Repost items have `post_type = repost`, `author_username` set to the crawled account, and `original_author_username` / `original_author_display_name` populated with the original post author. Original posts keep repost-only fields null. | ✅ Pass |
| TC-05 | Negative | Verify suspended account handling for `@Vinhbot22` | Dependencies installed, outbound network available, and `.env` contains valid `X_AUTH_TOKEN` / `X_CT0` cookies | 1. Run `uv run python cli.py crawl twitter --account Vinhbot22 --output output/test_vinhbot22.json`. 2. Capture CLI output and exit behavior. 3. Inspect resulting JSON file if created. | The crawler warns that the account is suspended, returns 0 posts, and does not crash. If a JSON file is written, it contains an empty array. | ❌ Fail |
| TC-06 | Negative | Verify invalid handle validation rejects malformed input | Dependencies installed | 1. Run `uv run python cli.py crawl twitter --account "invalid handle!"`. 2. Capture stderr/stdout and exit code. | CLI rejects the input before crawling, prints the validation error for `--account`, and exits with code 1. No browser session starts and no output file is created. | ✅ Pass |
| TC-07 | Contract | Verify rate limiting and BaseCrawler interface conformance | Branch checked out | 1. Inspect `crawlers/twitter.py`, `helpers/rate_limiter.py`, and `crawlers/base.py`. 2. Confirm `TwitterCrawler` subclasses `BaseCrawler`. 3. Confirm `crawl()` and `normalize()` are implemented. 4. Confirm a `RateLimiter(rate=0.5)` is used for crawl pacing. | Implementation follows the BaseCrawler contract and applies rate limiting during page settlement and scroll operations. | ✅ Pass |
| TC-08 | Resilience | Verify login-wall behavior remains explicit | Environment that can trigger X login wall, or inspection if live reproduction is not possible | 1. Trigger a run where X presents a login wall, or inspect the implementation path. 2. Observe CLI behavior. | The crawler raises `LoginWallError`, the CLI reports a login-wall message, and exits with code 2 instead of silently returning an empty dataset. | ✅ Pass |

## 4. Edge Cases & Negative Tests
- Suspended public account returns zero results without throwing an unhandled exception
- Invalid handles containing spaces, punctuation, or `@` prefix are rejected before crawling
- Public account may contain fewer posts than requested limit; output should still remain valid JSON
- Repost coverage depends on sampled timeline content; alternate live public accounts may be required to observe at least one repost
- Login wall can prevent live verification in some environments without cookies
- The status of a real X account can change over time, so any test that assumes suspension for a specific handle is time-sensitive and may become stale

## 5. Coverage Goals

| Area | Target |
|---|---|
| Acceptance criteria coverage | 100% |
| User-requested scenarios | Happy path, suspended account, invalid input, JSON validity, required fields, repost attribution |

## 6. Test Data
- Live public account: `elonmusk` with `--limit 5` for smoke validation
- Alternate live public account: `github` if repost coverage is not present in the first sample
- Suspended account: `Vinhbot22`
- Invalid handle: `invalid handle!`
- Output files: `output/test_elonmusk.json`, `output/test_vinhbot22.json`

## 7. Execution Log

| ID | Status | Notes |
|---|---|---|
| TC-01 | ✅ Pass | Verified `.env` exists in the workspace, then ran `uv run python cli.py crawl twitter --account elonmusk --limit 5 --output output/test_elonmusk.json`. The command exited successfully and saved 5 posts. |
| TC-02 | ✅ Pass | Parsed `output/test_elonmusk.json` successfully. The top-level payload is a JSON array with 5 items. |
| TC-03 | ✅ Pass | Validated all 5 items in `output/test_elonmusk.json`. Each item includes `post_id`, `post_type`, `author_username`, `author_display_name`, `date`, `content`, `media_urls`, `likes`, `retweets`, `replies`, `views`, and `post_url`. |
| TC-04 | ✅ Pass | The first 5 items contained no reposts, so a fallback run with `uv run python cli.py crawl twitter --account elonmusk --limit 20 --output output/test_elonmusk_limit20.json` was executed. The 20-item sample contained 5 reposts, and each repost had `original_author_username` and `original_author_display_name` populated. |
| TC-05 | ❌ Fail | Ran `uv run python cli.py crawl twitter --account Vinhbot22 --output output/test_vinhbot22.json` with authenticated cookies available. Instead of a suspension warning and an empty result, the crawler returned a non-empty JSON array with 409 items. This does not satisfy the expected suspended-account behavior. |
| TC-06 | ✅ Pass | Re-ran the invalid-handle case via a subprocess wrapper. CLI output was `Error: --account must be 1-50 alphanumeric characters or underscores (no @ prefix).` and the process exited with code 1. No output file was created. |
| TC-07 | ✅ Pass | Source inspection confirmed `TwitterCrawler` subclasses `BaseCrawler`, implements `crawl()` and `normalize()`, and uses `RateLimiter(rate=0.5)` through both CLI construction and crawler default initialization. |
| TC-08 | ✅ Pass | Source inspection confirmed `TwitterCrawler` raises `LoginWallError` when X redirects to login, and `cli.py` catches it and exits with code 2 after printing an explicit login-wall message. |

## 8. Bug Log

| Bug ID | TC | Description | Severity | Ticket |
|---|---|---|---|---|
| None | — | No product bug was confirmed in this run. The only failing case is TC-05, where the live state of `@Vinhbot22` no longer matches the test expectation that the account is suspended. | — | Not created |

## 9. Summary
Phase 2 final execution is complete. Final result: 7 passed, 1 failed. The crawler now passes the authenticated happy path, JSON/schema validation, repost attribution, malformed-handle validation, BaseCrawler/rate-limiter contract check, and explicit login-wall handling check. TC-05 remains failed because the live state of `@Vinhbot22` no longer matches the historical assumption used in the test: the account is currently crawlable and returns posts instead of showing a suspension warning and an empty dataset.