# Changelog

All notable changes are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Fixed
- Lenient parsing now repairs every off-spec field in one pass. Previously it fixed one field per
  pass and could give up, returning a raw `dict` (seen on service tickets). Each response now logs
  one concise warning naming each field and the reason.
- Corrected field types that contradict AgencyZoom's spec, verified on a live account:
  service ticket `createdBy`/`modifiedBy` (names), `dueDate`/`enterStageTS` (date strings);
  dashboard `monthlyItems`/`monthlyPolicies` (fractional); life lead `status` (single int);
  note `attr` (may be `[]`); policy `tagNames` (list).

### Added
- `make smoke`: a read-only check against a real account. `ARGS=--diagnose` reports the masked shape of
  off-spec fields without exposing data.

### Changed
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
