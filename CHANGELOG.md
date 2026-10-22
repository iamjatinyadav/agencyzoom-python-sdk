# Changelog

All notable changes are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

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
