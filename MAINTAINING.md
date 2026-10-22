# Maintaining the AgencyZoom Python SDK

The working manual for whoever maintains this package: how the code is laid out, the routine tasks, and how to release.

---

## 1. One-time setup

```bash
brew install uv                  # or: curl -LsSf https://astral.sh/uv/install.sh | sh
git clone https://github.com/iamjatinyadav/agencyzoom-python-sdk && cd agencyzoom-python-sdk
uv sync                          # .venv with runtime + dev dependencies, pinned by uv.lock
make spec                        # download AgencyZoom's spec (it is deliberately not committed)
make check                       # lint + mypy --strict + tests + generated-code check
```

`make help` lists every target. Run `make test-all` before a release: it runs the suite on Python 3.8 through 3.14, and uv downloads any interpreter you don't have.

---

## 2. Architecture in one page

```
AgencyZoom's public docs ──► scripts/fetch_spec.py ──► openapi/agencyzoom.yaml (git-ignored)
                                                                   │  fingerprint pinned in
                                                                   │  openapi/agencyzoom.yaml.sha256
                                                                   ▼
                                            scripts/generate_models.py ──► src/agencyzoom/models/_generated.py
                                                                           (230+ Pydantic models, never edited by hand)

src/agencyzoom/_endpoints.py      ENDPOINTS registry: ID -> (method, version-relative path)
src/agencyzoom/_async/            HAND-WRITTEN async client  ──► scripts/unasync.py ──► src/agencyzoom/_sync/
                                                                                        (GENERATED sync client)
```

| Layer | Files | Responsibility |
| --- | --- | --- |
| Public API | `__init__.py`, `_async/client.py` | Client constructor, resource attributes, `with_options`, `request` |
| Resources | `_async/resources/*.py` | One method per endpoint: builds the body, calls `self._call("<id>", ...)` |
| Endpoint registry | `_endpoints.py` | **The only place API paths live.** Resolves ID, version and overrides to a URL path |
| Transport | `_async/_http.py` | Auth header, rate limit, retries, 401 recovery, decoding, cache |
| Auth | `_async/_auth.py`, `_tokens.py` | Login, refresh, expiry, single-flight lock |
| Pure logic | `_retry.py`, `_rate_limit.py`, `_utils.py`, `_config.py`, `_exceptions.py` | No I/O. Shared by sync and async |
| Models | `models/_base.py` (hand-written), `models/_generated.py` | Lenient Pydantic models |
| Concurrency shims | `_async/_compat.py`, `_sync/_compat.py` | Lock, sleep and blocking-call helpers; the only hand-written twins |

**Golden rules**

1. **Never edit `_sync/` or `models/_generated.py`.** Edit `_async/` or the spec/generator, then run `make generate`. CI fails if the generated files are stale.
2. **Never write a URL path in a resource.** Add it to `ENDPOINTS` and call it by ID.
3. **Keep runtime code Python 3.8-safe.** Annotations can use `X | None` and `list[int]` because every module has `from __future__ import annotations`. Expressions evaluated at runtime must use `typing.List`, `typing.Union` and so on: `cast_to=`, type aliases, and everything in Pydantic models. `make test-all` catches mistakes.
4. **Keep the pure core pure.** Backoff, rate-limit math, parsing and validation belong in the shared modules, where they can be unit-tested without HTTP.

---

## 3. Routine tasks

### 3.1 AgencyZoom updated its API spec

You'll usually find out from the **Spec drift** workflow, which checks the live spec every Monday and on every push, and fails (GitHub emails you) when it changes.

```bash
cp openapi/agencyzoom.yaml /tmp/old-spec.yaml   # if you have the previous copy
make spec-update                         # download the new spec and pin its fingerprint
diff /tmp/old-spec.yaml openapi/agencyzoom.yaml | less   # see what changed
make generate                            # regenerate models + sync client
make test
git add openapi/agencyzoom.yaml.sha256 src/  # commit the new pin and regenerated code, NOT the spec
```

`tests/test_endpoint_coverage.py` then tells you exactly what's left to do:

- **"Spec endpoints missing from the registry"**: a new endpoint. See §3.2.
- **"Registry endpoints not in the spec"**: an endpoint was removed or renamed. Keep it if it still works (deprecate it in the CHANGELOG), or remove the method and its registry entry in a major release.

Read the changelog at the top of the spec (`info.description`) for behaviour changes such as new rate limits. Update `DEFAULT_RATE_LIMIT_PER_MINUTE` in `_config.py` if the limit changed.

### 3.2 Adding an endpoint

1. **Registry.** Add it to `ENDPOINTS` in `_endpoints.py`. The ID is the attribute path users will call, and the path is relative to `/v1/api`:
   ```python
   "leads.archive": Endpoint("POST", "/leads/{lead_id}/archive"),
   ```
2. **Method.** Add the method in `_async/resources/<group>.py`, following the neighbouring methods:
   ```python
   async def archive(self, lead_id: int, body: LeadArchiveRequest | Body | None = None, /, **fields: Any) -> GenericSuccessResponse:
       """Archive a lead. ``POST /leads/{leadId}/archive``"""
       payload = build_body(LeadArchiveRequest, body, fields)
       return await self._call("leads.archive", path_params={"lead_id": lead_id}, body=payload, cast_to=GenericSuccessResponse)
   ```
   - The `path_params` keys must equal the `{placeholders}`; a test enforces this.
   - Use `List[Model]` (not `list[Model]`) for `cast_to`.
   - Paginated searches get a `paginate()` that calls `self._paginate("<same id>", ...)`.
3. **New resource group?** Create the class, export it from `_async/resources/__init__.py`, and add a `cached_property` on `AsyncAgencyZoom`.
4. Run `make generate && make check`.
5. Add a request-shaping test in `tests/test_resources.py`, and add the method to the README's API map and the CHANGELOG.

### 3.3 AgencyZoom ships a v2 API

Users can move without a release: `api_version="v2"`, `api_root=...`, or `endpoint_overrides=...`. To make v2 the SDK's default:

- **Everything moved:** change `DEFAULT_API_VERSION` in `_config.py`. That's a **major** release, because default behaviour changes.
- **Some endpoints moved:** registry paths are relative, so for an endpoint that lives only under v2, store an **absolute** path in the registry entry and teach `EndpointResolver.resolve` to skip prefixing paths that start with the version (or add a `version` field to `Endpoint`). Add a test in `tests/test_edge_cases.py::TestVersioning`.
- **Request or response shapes changed:** teach `scripts/fetch_spec.py` to download the v2 spec as `openapi/agencyzoom-v2.yaml` (git-ignored like v1, with its own `.sha256` pin), generate its models into a separate module (e.g. `models/v2.py`), and keep the v1 models for compatibility.

### 3.4 A model field has the wrong type

AgencyZoom sometimes returns data that contradicts its spec. The SDK already copes by setting the field to `None` and logging a warning, but if a field is *consistently* different, fix it at the source:

- Prefer fixing the generator, e.g. a mapping of schema field → corrected type in `scripts/generate_models.py`, so the fix survives regeneration.
- Don't patch `openapi/agencyzoom.yaml`: it isn't committed, so a patch would be lost on the next download.

### 3.5 Updating dependencies

```bash
uv lock --upgrade          # refresh uv.lock within the pyproject ranges
make test-all
```

- The runtime ranges in `pyproject.toml` are deliberately wide (`httpx>=0.24`, `pydantic>=2.7`). CI's **lowest-deps** job tests the oldest allowed versions on Python 3.8, so raise a lower bound only if you need a newer feature.
- Dropping a Python version is a minor release at the earliest. Update `requires-python`, the classifiers, the CI matrix, the `PYTHONS` list in the Makefile, the README badge, and ruff's `target-version`.

---

## 4. Testing

| Suite | What it guarantees |
| --- | --- |
| `test_endpoint_coverage.py` | Registry == spec (117 endpoints); every ID is used; path params match placeholders; every ID maps to a public method |
| `test_auth.py` | Lazy login, refresh, 401 recovery, fallback to login, single-flight under concurrency |
| `test_transport.py` | Retry rules, backoff, `Retry-After`, error mapping, cache, headers |
| `test_resources.py` | Request shaping (snake/camel, model/dict), pagination, uploads, nested resources |
| `test_edge_cases.py` | Versioning and overrides, config validation, malformed responses, lifecycle, threads, event loops, rate limiting |

- HTTP is mocked with [respx](https://lundberg.github.io/respx/). Nothing touches the real API.
- Sleeps are patched (`conftest._no_sleep`), so the whole suite runs in about a second, and tests assert on the requested delays.

**Smoke-testing against the real API** before a release:

```bash
AGENCYZOOM_USERNAME=... AGENCYZOOM_PASSWORD=... uv run python examples/quickstart.py
```

Use a sandbox or test agency, because the quickstart writes a note to a lead.

---

## 5. Releasing

Versioning follows [SemVer](https://semver.org/):

- **Patch**: bug fixes.
- **Minor**: new endpoints or options.
- **Major**: removed methods, changed defaults, dropped Python versions.

1. Move the CHANGELOG's *Unreleased* items under the new version.
2. Bump `src/agencyzoom/_version.py`.
3. Run `make test-all && make check && make build`, then check that `dist/` contains one sdist and one wheel.
4. Commit and tag:
   ```bash
   git commit -am "Release v0.2.0"
   git tag v0.2.0 && git push origin main v0.2.0
   ```
5. `.github/workflows/release.yml` checks that the tag matches `_version.py`, runs the tests, builds, publishes to PyPI with **trusted publishing**, and creates a GitHub release.

**First-time PyPI setup**, once:

1. On PyPI, go to *Account settings* → *Publishing* → *Add a new pending publisher*. Enter PyPI project name `agencyzoom-sdk`, owner `iamjatinyadav`, repository `agencyzoom-python-sdk`, workflow `release.yml`, environment `pypi`. A pending publisher creates the project on the first successful upload.
2. In GitHub → *Settings* → *Environments*, create `pypi`. Optionally require a reviewer.

Without CI, `uv build && uv publish` also works (it asks for a PyPI token).

---

## 6. Legal hygiene (keep doing this)

This is an unofficial client for a proprietary product, so:

- **Never commit AgencyZoom's spec or other docs.** `.gitignore` blocks `openapi/*.yaml|yml|json`. Commit only the `.sha256` fingerprint. The spec is marked "Propriety license", and the repo history was rewritten once to remove a copy.
- **Keep "unofficial" and the "not affiliated with or endorsed by AgencyZoom or Vertafore" notice** at the top of the README, which is also the PyPI page.
- **Don't use their logos**, and don't word anything as if it came from AgencyZoom.
- **The governing terms** are the Vertafore Standard Terms (https://www.vertafore.com/terms, linked from agencyzoom.com). The `termsOfService` link inside the spec (`agencyzoom.com/tos`) returned 404 when checked on 2026-10-22.
- If AgencyZoom or Vertafore ever asks for a change (a rename, a takedown, or adopting the project), act on it promptly. The package can be renamed, or yanked on PyPI.

## 7. Sister SDKs

`agencyzoom-go-sdk/` and `agencyzoom-rust-sdk/` implement the same design: the same endpoint IDs, the same versioning options, and the same retry and auth rules.

When you change behaviour here, such as a retry rule or a new option, open matching issues in the other two so they stay in step. Each SDK vendors its own copy of the spec. Update all three together.
