# AgencyZoom Python SDK

[![Python](https://img.shields.io/badge/python-3.8%20%E2%80%93%203.14-blue)](#requirements)
[![Typed](https://img.shields.io/badge/typing-strict-brightgreen)](#)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

An **unofficial**, fully-typed Python client for the [AgencyZoom REST API](https://app.agencyzoom.com/openapi/), with both sync and async interfaces.

> Not affiliated with or endorsed by AgencyZoom or Vertafore.

- **All 117 endpoints** across 16 API groups. A test checks this against the OpenAPI spec.
- **Ready for API versions**: move to `v2` with one argument, or move single endpoints without a new SDK release.
- **Sync and async** clients with an identical API (`AgencyZoom` / `AsyncAgencyZoom`).
- **Typed models** for all 230+ schemas (Pydantic v2), with snake_case attributes and full editor autocomplete.
- **Hands-off auth**: logs in lazily, refreshes the token before it expires, recovers from a `401` once, and makes concurrent requests share a single refresh.
- **Rate limit aware**: a client-side token bucket keeps you under AgencyZoom's 120 calls/minute.
- **Resilient**: exponential backoff with jitter, `Retry-After` support, and no duplicate writes (non-idempotent requests are only retried when it's safe).
- **Auto-pagination** that fetches pages lazily and stops safely even when the server misbehaves.
- **Lenient parsing**: a malformed field in a response logs a warning instead of crashing your job.
- **Python 3.8 to 3.14**, on Linux, macOS and Windows.

---

## Contents

1. [Installation](#installation)
2. [Quick start](#quick-start)
3. [Authentication](#authentication)
4. [Making requests](#making-requests)
5. [Pagination](#pagination)
6. [API versions & custom endpoints](#api-versions--custom-endpoints)
7. [Configuration](#configuration)
8. [Errors](#errors)
9. [Edge-case behaviour](#edge-case-behaviour)
10. [API map](#api-map)
11. [Logging](#logging)
12. [Contributing](#contributing)

---

## Installation

The package is published as **`agencyzoom-sdk`**. You import it as **`agencyzoom`**.

| Tool | Command |
| --- | --- |
| **uv** (project) | `uv add agencyzoom-sdk` |
| **uv** (pip interface) | `uv pip install agencyzoom-sdk` |
| **pip** | `pip install agencyzoom-sdk` |
| **Poetry** | `poetry add agencyzoom-sdk` |
| **PDM** | `pdm add agencyzoom-sdk` |
| **Pipenv** | `pipenv install agencyzoom-sdk` |
| **Hatch** | add `"agencyzoom-sdk"` to `dependencies` in `pyproject.toml` |
| **conda / mamba** | `pip install agencyzoom-sdk` inside the environment |

Optional HTTP/2 support:

```bash
uv add "agencyzoom-sdk[http2]"      # or: pip install "agencyzoom-sdk[http2]"
```

Straight from GitHub, before a release or to pin a commit:

```bash
uv add "agencyzoom-sdk @ git+https://github.com/jatinyadav/agencyzoom-python-sdk"
pip install "git+https://github.com/jatinyadav/agencyzoom-python-sdk"
```

### Requirements

- Python **3.8+** (tested on 3.8 through 3.14)
- Dependencies, installed automatically: `httpx`, `pydantic` v2, `typing-extensions`

Check the install:

```bash
python -c "import agencyzoom; print(agencyzoom.__version__)"
```

---

## Quick start

**1. Provide credentials.** Use the agency owner's login: the API grants the same permissions as the user you log in with.

```bash
export AGENCYZOOM_USERNAME="owner@youragency.com"
export AGENCYZOOM_PASSWORD="your-password"
```

**2. Make calls.**

```python
from agencyzoom import AgencyZoom

with AgencyZoom() as client:                       # reads credentials from the environment
    # One page of results
    page = client.leads.search(status=0, page_size=50)
    print(f"{page.total_count} new leads")

    # Every matching record; pages are fetched as you iterate
    for lead in client.leads.paginate(status=0):
        print(lead.id, lead.firstname, lead.lastname)

    # Read, write, nested resources
    lead = client.leads.get(12345)
    client.leads.notes.create(12345, "Left a voicemail")
    client.tasks.create(title="Call back", customer_id=lead.customer_id)
```

**Async**, with the same API plus `await` and `async for`:

```python
import asyncio
from agencyzoom import AsyncAgencyZoom

async def main() -> None:
    async with AsyncAgencyZoom() as client:
        lead, tasks = await asyncio.gather(client.leads.get(1), client.leads.list_tasks(1))
        async for customer in client.customers.paginate(state="TX"):
            print(customer.id)

asyncio.run(main())
```

More in [`examples/`](examples/): a quick start, a streaming CSV export, and a concurrent async dashboard.

---

## Authentication

Pick one way to authenticate:

```python
AgencyZoom(username="owner@agency.com", password="...")   # logs in on first use
AgencyZoom(token="eyJ...", refresh_token="eyJ...")        # reuse an existing session
AgencyZoom()                                              # from environment variables
```

| Environment variable | Purpose |
| --- | --- |
| `AGENCYZOOM_USERNAME` / `AGENCYZOOM_PASSWORD` | Login credentials |
| `AGENCYZOOM_TOKEN` | Existing JWT, instead of username/password |
| `AGENCYZOOM_API_TOKEN` | `X-Api-Token`, needed only by `client.policies.create` |
| `AGENCYZOOM_BASE_URL` | API host (default `https://api.agencyzoom.com`) |
| `AGENCYZOOM_API_VERSION` | API version (default `v1`) |

Explicit arguments win over environment variables, and blank variables count as unset.

You never manage tokens yourself. The client:

- logs in with `version=2` on the first request, which gets a refresh token and expiry;
- refreshes about 60 seconds **before** the token expires;
- on a `401`, renews the session once (refresh, or a fresh login if the refresh fails) and retries the request;
- makes concurrent threads and tasks wait for **one** shared login or refresh.

For explicit control, use `client.auth.login()`, `client.auth.refresh()` and `client.auth.logout()`. V4 SSO is under `client.v4sso`.

---

## Making requests

### Request bodies

Every endpoint that takes a body accepts it in any of three forms, and they're equivalent:

```python
from agencyzoom.models import LeadCreateRequest

client.leads.create(firstname="Ada", email="ada@example.com", lead_source_id=1,      # 1. keyword
                    assign_to=7, country="US", pipeline_id=3, stage_id=9)             #    arguments
client.leads.create({"firstname": "Ada", "leadSourceId": 1, ...})                     # 2. dict
client.leads.create(LeadCreateRequest(firstname="Ada", ...))                          # 3. model
```

- Field names work as **snake_case** (`lead_source_id`) or the API's **camelCase** (`leadSourceId`).
- When you mix a body and keyword arguments, the keyword arguments win.
- **Required fields are checked before sending.** A missing one raises `pydantic.ValidationError` without making an HTTP call.
- **Unknown fields are passed through**, so new API fields work without an SDK update.
- `date`/`datetime` values are sent as ISO-8601 strings, and numbers are accepted for string fields such as phone numbers and ZIP codes.
- Passing `None` explicitly sends `null`, which you can use to clear a field. Omitted fields aren't sent.

### Responses

Responses are Pydantic models with snake_case attributes:

```python
lead = client.leads.get(1)
lead.firstname, lead.lead_source_id
lead["leadSourceId"]                # dict-style access by API name works too
lead["someBrandNewField"]           # fields the SDK doesn't know about are kept
lead.model_dump(by_alias=True)      # back to the raw API shape
```

### Uploading files

```python
client.leads.files.upload(lead_id, [
    "dec-page.pdf",                         # a path
    open("license.png", "rb"),              # an open file
    ("notes.txt", b"raw bytes"),            # (filename, content)
    ("data.csv", "a,b", "text/csv"),        # (filename, content, content type)
])
```

Content types are inferred from file names. Uploads are buffered, so they're safely retried after a `429`.

### Reference data and caching

```python
client = AgencyZoom(cache_ttl=600)          # cache reference lists for 10 minutes
client.settings.carriers()                  # network
client.settings.carriers()                  # memory
client.clear_cache()
```

Only `client.settings.*` and `client.pipelines.*` are cached, and only when `cache_ttl` is set.

---

## Pagination

`search(...)` returns one page. `paginate(...)` yields **every** matching item and fetches pages only as you consume them:

```python
for task in client.tasks.paginate(status=0, assignee_id=42):
    ...

import itertools
first_250 = list(itertools.islice(client.leads.paginate(status=1), 250))   # stops fetching early
```

- Uses the largest page size each endpoint allows (leads 100, tasks 200, life 500...), so it makes fewer calls under the rate limit. You can override it with `page_size=`.
- Starts from `page=` if you give one.
- Stops at `totalCount`, on a short or empty page, or when the server returns the **same page twice** (some servers ignore the page parameter). This guards against infinite loops.

Paginated endpoints: `leads`, `customers`, `tasks`, `service_tickets`, `life_health`.

---

## API versions & custom endpoints

Every endpoint is defined once in an **endpoint registry** (`agencyzoom.ENDPOINTS`). Paths there are *relative to the API root*, so the API version is a configuration value rather than a code change.

```python
# Move every endpoint to /v2/api/...
AgencyZoom(api_version="v2")                       # or AGENCYZOOM_API_VERSION=v2

# A different URL layout entirely, e.g. /api/v2/leads/list
AgencyZoom(api_root="/api/v2")

# A gradual rollout: move only some endpoints, by ID (= the SDK attribute path)
AgencyZoom(endpoint_overrides={
    "leads.search": "POST /v2/api/leads/search",    # new method and path
    "leads.get":    "/v2/api/leads/{lead_id}",      # new path, same method
})

# Behind a proxy or gateway that adds a path prefix
AgencyZoom(base_url="https://gateway.example.com/agencyzoom")
```

Overrides are validated when the client is created:

- An unknown ID is an error with a "did you mean" suggestion.
- The override must use the same `{placeholders}` as the original.
- Paths must be absolute.

Each endpoint's ID matches how you call it, so `client.leads.notes.create` is `"leads.notes.create"`:

```python
from agencyzoom import ENDPOINTS
ENDPOINTS["leads.notes.create"]      # Endpoint(method='POST', path='/leads/{lead_id}/notes')
```

**Per-call options.** `with_options()` returns a lightweight copy that shares the connection pool, session, rate limiter and cache:

```python
client.with_options(timeout=120, max_retries=0).leads.batch_create(...)
beta = client.with_options(api_version="v2", default_headers={"X-Beta": "1"})
```

**Endpoints the SDK doesn't have yet.** `client.request` goes through the same auth, retry and rate-limit pipeline:

```python
client.request("POST", "/v2/api/some/new-endpoint", json={"foo": 1})
client.request("GET", "/v1/api/leads/1", cast_to=agencyzoom.models.LeadDetail)
```

---

## Configuration

```python
from agencyzoom import AgencyZoom, RetryConfig

client = AgencyZoom(
    timeout=30,                       # seconds, or an httpx.Timeout (default 60s, 10s connect)
    max_retries=RetryConfig(          # or just an int (default 3)
        max_retries=5,
        backoff_factor=1.0,           # exponential: 1s, 2s, 4s... with jitter
        max_backoff=60,               # also caps the server's Retry-After
    ),
    rate_limit_per_minute=100,        # default 120; None disables the client-side limit
    cache_ttl=600,                    # cache reference data; default off
    default_headers={"X-Request-Source": "nightly-sync"},
    http2=True,                       # needs the [http2] extra
)
```

**Proxies, custom TLS, event hooks.** Pass your own `httpx.Client` (sync) or `httpx.AsyncClient` (async) as `http_client=`. The SDK won't close it. The standard `HTTPS_PROXY`/`HTTP_PROXY` environment variables are honoured by default.

**Sharing one rate budget.** AgencyZoom's limit is per account. Use `with_options()` copies rather than several separate clients, so they share one limiter.

### Retry rules

| Failure | Retried? |
| --- | --- |
| `429 Too Many Requests` | Always (honours `Retry-After`, capped at `max_backoff`) |
| Connection could not be established | Always |
| `5xx`, read timeouts | Only for `GET` / `PUT` / `DELETE` (a failed `POST` may already have been applied) |
| `401` | Once, after renewing the session |
| Other `4xx` | Never |

---

## Errors

```python
from agencyzoom import AgencyZoomError, BadRequestError, NotFoundError, RateLimitError

try:
    client.leads.create(...)
except BadRequestError as e:
    print(e.status_code, e.message)
    for fe in e.field_errors:
        print(f"  {fe.field}: {fe.error}")
except NotFoundError:
    ...
except AgencyZoomError as e:          # catches everything the SDK raises
    ...
```

```
AgencyZoomError
├── ConfigurationError              bad arguments / missing credentials
├── APIConnectionError              network failure (after retries)
│   └── APITimeoutError
├── APIResponseError                2xx but unusable, e.g. an HTML maintenance page
└── APIStatusError                  .status_code .message .field_errors .body .response
    ├── BadRequestError (400)        ├── ConflictError (409)
    ├── AuthenticationError (401)    ├── UnprocessableEntityError (422)
    ├── PermissionDeniedError (403)  ├── RateLimitError (429)
    ├── NotFoundError (404)          └── InternalServerError (5xx)
```

Two other exceptions are raised before any request is sent: `pydantic.ValidationError` for invalid request data, and `ValueError` for invalid IDs.

---

## Edge-case behaviour

| Situation | What happens |
| --- | --- |
| Response field has the wrong type (`"abc"` for a number) | Field becomes `None`, a warning is logged, and the rest of the response is kept |
| `""` returned for a number or boolean | Treated as `None` |
| Response shape doesn't match the spec at all | The raw JSON is returned, with a warning |
| `200` with HTML or other non-JSON body | `APIResponseError` (includes a snippet of the body) |
| Empty body or `204` | Returns `None` |
| Error page that isn't JSON (proxy `502` HTML) | `InternalServerError` with the text as its message |
| ID is `None`, `True`, or blank | `ValueError` before any request is sent |
| ID contains `/`, spaces, etc. | URL-encoded |
| Login succeeds but returns no token | `APIResponseError` with the server's message |
| `expiresIn` missing, garbage, or negative | Falls back to the JWT's `exp` claim, then to "valid until a 401" |
| Huge `Retry-After` | Capped at `RetryConfig.max_backoff` |
| Redirects | Followed (credentials are dropped on cross-host redirects) |
| Server ignores the `page` parameter | Pagination stops after the repeated page, with a warning |
| `totalCount` sent as a string | Understood |
| Using a client after `close()` | `AgencyZoomError("...has been closed...")` |
| Many threads or tasks hitting an expired token | One refresh. Everyone else waits for it |
| Async client reused across `asyncio.run()` calls | Supported (internal locks bind to the current event loop) |
| Text-mode file handle uploaded | Encoded as UTF-8 |
| Blank env vars or blank arguments | Treated as unset |
| Secrets in `repr()` or logs | Never shown (`Authorization` and `X-Api-Token` are redacted) |

---

## API map

| Attribute | Methods |
| --- | --- |
| `client.auth` | `login`, `sso_login`, `refresh`, `logout` |
| `client.v4sso` | `get_auth_params`, `login` |
| `client.leads` | `search`, `paginate`, `count`, `get`, `create`, `batch_create`, `update`, `delete`, `create_commercial`, `update_commercial`, `change_status`, `change_stage`, `mark_sold`, `list_tasks`, `recycle_events` |
| `client.leads.notes` | `list`, `create` |
| `client.leads.quotes` | `list`, `create`, `update`, `delete` |
| `client.leads.opportunities` | `list`, `create`, `update`, `delete` |
| `client.leads.files` | `list`, `upload`, `rename`, `delete` |
| `client.customers` | `search`, `paginate`, `get`, `create`, `update`, `delete`, `list_tasks`, `add_note`, `delete_file`, `list_policies`, `list_ams_policies`, `delete_policy` |
| `client.policies` | `create`, `update`, `update_tags`, `update_status`, `endorse` |
| `client.opportunities` | `get`, `create`, `update`, `delete` |
| `client.opportunities.drivers` / `.vehicles` | `list`, `get`, `create`, `update`, `delete`, `link`, `unlink` |
| `client.tasks` | `search`, `paginate`, `get`, `create`, `update`, `delete`, `batch_delete`, `complete`, `reopen` |
| `client.service_tickets` | `search`, `paginate`, `create`, `update`, `complete`, `list_policies`, `list_ams_policies` |
| `client.email_threads` | `search`, `get_messages`, `mark_unread`, `delete`, `delete_message` |
| `client.text_threads` | `search`, `get_messages`, `list_producers`, `mark_unread`, `delete` |
| `client.life_health` | `search`, `paginate` |
| `client.contacts` | `batch_create` |
| `client.dashboard` | `sales_data` |
| `client.profile` | `update` |
| `client.settings` | `employees`, `carriers`, `lead_sources`, `lead_source_categories`, `product_lines`, `product_categories`, `locations`, `loss_reasons`, `custom_fields`, `csrs`, `tags`, `assign_groups`, `life_professionals`, `service_categories`, `service_priorities`, `service_resolutions` |
| `client.pipelines` | `list`, `list_with_stages`, `end_stages` |
| `client.departments` | `list` |
| `client.business_classifications` | `search` |

Every method has a docstring with its HTTP method and path, and every model field has a docstring from the API spec. Hover in your editor to see them.

---

## Logging

The SDK logs to the `agencyzoom` logger:

- `DEBUG`: every request, with its status and latency
- `INFO`: retries
- `WARNING`: responses that didn't match the spec

Credentials and tokens are never logged.

```python
import logging
logging.basicConfig()
logging.getLogger("agencyzoom").setLevel(logging.DEBUG)
```

---

## Contributing

```bash
git clone https://github.com/jatinyadav/agencyzoom-python-sdk && cd agencyzoom-python-sdk
uv sync            # creates .venv with every dev tool
make check         # lint + types + tests
```

See **[MAINTAINING.md](MAINTAINING.md)** for the architecture, how to handle AgencyZoom API changes, and how to cut a release.

## License

MIT. See [LICENSE](LICENSE).
