---
title: "Test Plan: Init App & Build Project Structure"
type: test
status: stable
version: 1.0.1
created: 2026-04-09
updated: 2026-04-09
authors: [GitHub Copilot]
related: []
---

# Test Plan: Init App & Build Project Structure

## 1. Scope
Validate SAC-1 repository bootstrap outputs: packaging metadata, required module layout, base interfaces, storage implementation, models, CLI wiring, environment documentation, repository quickstart, and lint status.

Out of scope: platform-specific crawler behavior, real API authentication, persistence backends beyond JSON, and runtime crawling logic.

## 2. Test Strategy

| Layer | Approach | Tools |
|---|---|---|
| Static inspection | Verify file presence and implementation shape against acceptance criteria | read_file, rg |
| CLI smoke | Confirm the entrypoint is runnable and exposes help output | uv run python cli.py --help |
| Lint | Verify repository passes configured Ruff checks | uv run ruff check . |
| Test discovery | Run pytest to confirm the bootstrap state does not introduce test failures | uv run pytest tests/ -v |

## 3. Test Cases

| ID | Description | Preconditions | Steps | Expected Result |
|---|---|---|---|---|
| TC-01 | Verify package manifest dependencies | Branch checked out | Open pyproject.toml and inspect dependency lists | Required runtime and dev dependencies are declared |
| TC-02 | Verify required package folders | Branch checked out | Confirm crawlers, analyzers, helpers, models, storage, and tests each contain __init__.py | All required folders exist and are importable packages |
| TC-03 | Verify crawler interface | Branch checked out | Inspect crawlers/base.py | BaseCrawler is abstract and declares crawl() and normalize() |
| TC-04 | Verify rate limiter implementation | Branch checked out | Inspect helpers/rate_limiter.py | A token bucket limiter with refill and wait behavior exists |
| TC-05 | Verify storage abstractions | Branch checked out | Inspect storage/base.py and storage/json_store.py | StorageBackend interface exists and JsonStore implements async save/load |
| TC-06 | Verify Pydantic models | Branch checked out | Inspect models/post.py and models/profile.py | Both models inherit from BaseModel and define base fields |
| TC-07 | Verify CLI smoke test | Dependencies installed | Run uv run python cli.py --help | Command exits successfully and shows Typer help |
| TC-08 | Verify environment documentation | Branch checked out | Inspect .env.example | Expected environment variables are documented |
| TC-09 | Verify README quickstart | Branch checked out | Inspect README.md | Quickstart-style install/run guidance is present |
| TC-10 | Verify lint health | Dependencies installed | Run uv run ruff check . | Ruff exits 0 with no errors |
| TC-11 | Verify pytest bootstrap | Dependencies installed | Run uv run pytest tests/ -v | Pytest completes without failing tests |

## 4. Edge Cases & Negative Tests
- [x] Missing docs index in a fresh bootstrap repo
- [ ] Dependency installation absent or broken in local environment
- [ ] Invalid storage key path traversal attempt in JsonStore
- [ ] Rate limiter acquire with more tokens than current bucket balance

## 5. Coverage Goals

| Area | Target |
|---|---|
| Acceptance criteria coverage | 100% |
| Executable smoke checks | CLI, lint, and pytest all exercised |

## 6. Test Data
No persistent test data required. QC uses repository files and command output only.

## 7. Execution Log

| ID | Status | Notes |
|---|---|---|
| TC-01 | ✅ Pass | pyproject.toml declares required runtime dependencies and dev extras include ruff and pytest |
| TC-02 | ✅ Pass | Required package folders exist and each contains __init__.py |
| TC-03 | ✅ Pass | BaseCrawler is abstract and defines crawl() and normalize() |
| TC-04 | ✅ Pass | RateLimiter implements async token bucket refill and wait behavior |
| TC-05 | ✅ Pass | StorageBackend defines async save/load and JsonStore implements both |
| TC-06 | ✅ Pass | Post and Profile inherit from pydantic BaseModel and define base fields |
| TC-07 | ✅ Pass | uv run python cli.py --help renders Typer help successfully |
| TC-08 | ✅ Pass | .env.example documents storage and platform credential variables currently expected by the repo |
| TC-09 | ✅ Pass | README includes install, run, test, lint, and configuration quickstart guidance |
| TC-10 | ✅ Pass | uv run ruff check . exits successfully with "All checks passed!" |
| TC-11 | ✅ Pass | uv run pytest tests/ -v completes successfully with 0 collected tests and no failures |

## 8. Bug Log

| Bug ID | TC | Description | Severity | Ticket |
|---|---|---|---|---|
| — | — | None confirmed yet | — | — |

## 9. Summary
All SAC-1 acceptance criteria passed on branch feat/SAC-1-init-project-structure. No product bugs were confirmed during this QC run.