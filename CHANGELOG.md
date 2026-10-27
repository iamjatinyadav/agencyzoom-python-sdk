# Changelog

All notable changes are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.2.0] - 2026-10-27

### Fixed
- Reject all HTTP redirects, including with injected clients, to prevent forwarding login bodies
  and custom API-token headers.
- Synchronize explicit and automatic authentication, retain the active account's renewal credentials,
  prevent retries under a switched identity, and use each copied client's authentication routes.
- Isolate cached responses by host, headers and session revision; reject cached reads after close
  and avoid caching responses from an account that changed while the request was in flight.
- Preserve original JSON when lenient response repair cannot validate the payload.
- Hide credential fields in generated-model and token-state representations and validation error text.
- Keep ordinary classification codes visible in model representations; redact authorization codes
  only in their authentication schema.
- Preserve cached reference data across routine token refreshes while still invalidating it after
  explicit session changes, token rejection and fresh login.
- Reject nonfinite numeric configuration, fractional retry counts, malformed base URLs, and nonnumeric
  path IDs (including dot segments). Bound backoff for very large retry counts.
- Lenient parsing now repairs every off-spec field in one pass. Previously it fixed one field per
  pass and could give up, returning a raw `dict` (seen on service tickets). Each response now logs
  one concise warning naming each field and the reason.
- Corrected field types that contradict AgencyZoom's spec, verified on a live account:
  service ticket `createdBy`/`modifiedBy` (names), `dueDate`/`enterStageTS` (date strings);
  dashboard `monthlyItems`/`monthlyPolicies` (fractional); life lead `status` (single int);
  note `attr` (may be `[]`); policy `tagNames` (list).

### Added
- Optional `strict_response_validation=True`, also available on `with_options()` copies.
- Security and concurrency regression tests, real HTTP connection-pool tests, and OpenAPI wire-contract
  checks exercising all 117 public endpoints in both sync and async clients.
- Weekly and pull-request dependency advisory checks for runtime environments on Python 3.8–3.14.
- Security policy documenting the two accepted legacy AnyIO advisories on Python 3.8/3.9,
  their SDK exposure assessment, and narrowly scoped CI exceptions with unfiltered audit artifacts.
- `make smoke`: a read-only check against a real account. `ARGS=--diagnose` reports the masked shape of
  off-spec fields without exposing data.

### Changed
- Path IDs now accept only non-negative integers or digit strings; other values raise `ValueError`
  before a request is sent. This changes the previous permissive handling of arbitrary string IDs.
- Retain Python 3.8/3.9 support with documented dependency limitations; recommend Python 3.10+
  and current dependencies for new deployments.
- Async clients and their copies must be used and closed within one event loop. Cross-loop use raises
  `AgencyZoomError` before accessing connections or cached data.
- Pagination raises `APIResponseError` for malformed pages, prematurely empty pages, repeated pages,
  and exhaustion of its page limit, rather than silently returning incomplete exports.
- AgencyZoom's OpenAPI spec is no longer stored in the repository. `make spec` downloads it,
  and a weekly *Spec drift* workflow detects API changes.

## [0.1.0] - 2026-10-22

Initial release.

### Added
- Sync (`AgencyZoom`) and async (`AsyncAgencyZoom`) clients covering all 117
  endpoints of the AgencyZoom API spec (2026.08.17).
- Endpoint registry (`agencyzoom.ENDPOINTS`) with `api_version`, `api_root`,
  `endpoint_overrides` and `with_options()` for API-version changes without an SDK release.
- Generated Pydantic v2 models for every schema, with lenient response parsing.
- Automatic login, proactive token refresh, single-flight 401 recovery.
- Client-side rate limiting (120/min default); retries with backoff, jitter and `Retry-After`.
- Lazy auto-pagination with protection against servers that ignore `page`.
- Multipart uploads (paths, bytes, binary or text file handles), optional reference-data cache.
- Python 3.8 – 3.14 support; installable with uv, pip, Poetry, PDM and Pipenv.
