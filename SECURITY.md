# Security and Python compatibility

## Supported environments

The SDK retains Python 3.8 through 3.14 support. Functional compatibility and
dependency security are separate: passing the SDK test suite does not mean every
dependency version is free of known advisories.

Python 3.8 and 3.9 remain supported for compatibility with existing applications.
They have the accepted dependency limitations below. For new deployments, use
Python 3.10 or newer with current dependencies. AnyIO 4.14.2 contains both fixes
and [requires Python 3.10 or newer](https://pypi.org/pypi/anyio/4.14.2/json).
The SDK does not override package metadata to install that release on older Python.

## Accepted legacy AnyIO advisories

Reviewed on 2026-10-27. The committed lock file selects AnyIO 4.5.2 on Python 3.8
and 4.12.1 on Python 3.9. Both versions are affected by these upstream advisories:

| Advisory | Upstream impact | Relevance to this SDK |
| --- | --- | --- |
| [PYSEC-2026-4025 / CVE-2026-63374 / GHSA-82r6-8w77-94w6](https://github.com/agronholm/anyio/security/advisories/GHSA-82r6-8w77-94w6) | Incorrect handling of internationalized TLS hostnames can allow certificate spoofing when a connection is redirected through other means. | The default API host is ASCII. The checked HTTPX 0.28.1 / HTTPCore 1.0.9 path passes ASCII IDNA hostnames to AnyIO. Custom transports, TLS/SNI hooks, or direct AnyIO use need a separate assessment. |
| [PYSEC-2026-4024 / CVE-2026-64847 / GHSA-5p39-cfhj-2xmp](https://github.com/agronholm/anyio/security/advisories/GHSA-5p39-cfhj-2xmp) | AnyIO process-pool workers can deadlock when their undrained stderr pipe fills. | The SDK does not use AnyIO process pools. File preparation uses an asyncio thread executor. Applications using AnyIO process pools independently remain subject to the advisory. |

These are accepted compatibility exceptions, not patches to the affected AnyIO
versions. This assessment is limited to the SDK's inspected paths and dependency
versions; it does not establish that an entire application is unaffected.

## Dependency audit policy

The dependency-security workflow runs on pull requests, main-branch pushes and
weekly. It audits the actual installed runtime dependencies on each supported
Python version using public advisories.

- Every matrix job preserves a complete, unfiltered `audit.json` and the exact
  `runtime-requirements.txt` as a downloadable artifact, including accepted findings.
- Only the two advisory IDs listed above are waived on Python 3.8 and 3.9. These
  jobs emit an explicit warning about the retained dependency risk.
- Other advisories, dependency collection failures and audit service failures
  still block the enforcement step. Python 3.10 and newer have no advisory waivers.
- No security fixes are disabled, TLS verification remains enabled by default,
  and CI does not install a newer dependency while ignoring its Python requirements.

Reassess these exceptions when AnyIO publishes a compatible security backport,
the lock file changes its legacy AnyIO versions, an SDK networking path changes,
or Python support is reconsidered. Do not add blanket audit exclusions or mark
the whole legacy audit job as allowed to fail.

## Handling credentials

SDK authentication models hide known password and token fields in `repr()` and
`str()`, including supported token aliases returned as extra fields. Explicit
model dumps and exception response bodies can still contain credentials or
customer information. Review application logging and custom HTTP hooks separately.

Redirects are rejected before forwarding credentials to a new location. Configure
the intended API host explicitly. Clients created with `with_options()` share the
session and credentials, so a changed `base_url` must remain trusted.
