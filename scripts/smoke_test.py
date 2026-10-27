#!/usr/bin/env python3
"""Read-only smoke test against a real AgencyZoom account.

It never creates, updates or deletes anything; every call is a read or a search.
It prints counts and field names only (no customer names, emails or other
personal data), so the output is safe to share when reporting a problem.

Usage::

    uv run python scripts/smoke_test.py              # pass/fail per endpoint
    uv run python scripts/smoke_test.py --diagnose   # + the *shape* of every off-spec field

``--diagnose`` reports each mismatched field's JSON type and a masked pattern
(digits -> 9, letters -> a/A, e.g. ``"9999-99-99 99:99:99"``) so the right type
can be chosen without exposing real values.

Credentials come from AGENCYZOOM_USERNAME / AGENCYZOOM_PASSWORD if set,
otherwise you are prompted (the password is not echoed). Exit code 0 = all
checks passed and every response matched the models.
"""

from __future__ import annotations

import argparse
import collections
import getpass
import itertools
import logging
import os
import re
import sys
import time
from typing import Any, Callable

from agencyzoom import AgencyZoom, AgencyZoomError, __version__


class _Collect(logging.Handler):
    """Collects the SDK's 'response did not match the model' warnings."""

    def __init__(self) -> None:
        super().__init__(logging.WARNING)
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.messages.append(record.getMessage())


def _count(value: Any) -> str:
    if value is None:
        return "empty"
    if isinstance(value, list):
        return f"{len(value)} items"
    for attr in ("total_count", "totalCount"):
        total = getattr(value, attr, None)
        if total is not None:
            return f"total {total}"
    return "ok"


def _first_id(items: list[Any] | None) -> int | None:
    for item in items or []:
        if getattr(item, "id", None) is not None:
            return int(item.id)
    return None


def _shape(value: Any) -> str:
    """Describe a JSON value without revealing it."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float (whole)" if value.is_integer() else "float (fractional)"
    if isinstance(value, str):
        if not value.strip():
            return 'str ""'
        masked = re.sub(r"[A-Z]", "A", re.sub(r"[a-z]", "a", re.sub(r"[0-9]", "9", value)))
        masked = re.sub(r"(a)a{3,}", r"\1a…", re.sub(r"(A)a{3,}", r"\1a…", masked))
        return f'str "{masked[:32]}{"…" if len(masked) > 32 else ""}"'
    if isinstance(value, list):
        inner = sorted({_kind(v) for v in value[:20]})
        return f"array[{len(value)}] of {'/'.join(inner) or 'nothing'}"
    if isinstance(value, dict):
        keys = ", ".join(sorted(value)[:8])
        return f"object{{{keys}{', …' if len(value) > 8 else ''}}}"
    return type(value).__name__


def _kind(value: Any) -> str:
    """Just the JSON type: object, array, str, int, float, bool or null."""
    if isinstance(value, dict):
        return "object"
    if isinstance(value, list):
        return "array"
    return _shape(value).split(" ")[0]


def _install_diagnostics() -> dict:
    """Wrap the SDK's response parser to record off-spec fields and their shapes."""
    import agencyzoom._sync._http as http_mod
    import agencyzoom._sync._resource as resource_mod
    import agencyzoom._sync.resources.auth as auth_mod
    from agencyzoom._utils import invalid_fields, parse_response

    seen: dict = collections.defaultdict(lambda: {"error": "", "shapes": collections.Counter()})

    def recording_parse(cast_to: Any, data: Any, *, strict: bool = False) -> Any:
        if cast_to is not None and data is not None:
            for path, kind, message, value in invalid_fields(cast_to, data):
                entry = seen[(_type_label(cast_to), path)]
                entry["error"] = f"{kind}: {message}"
                entry["shapes"][_shape(value)] += 1
        return parse_response(cast_to, data, strict=strict)

    for module in (http_mod, resource_mod, auth_mod):
        module.parse_response = recording_parse  # type: ignore[attr-defined]
    return seen


def _type_label(tp: Any) -> str:
    from agencyzoom._utils import _type_name

    return _type_name(tp)


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only AgencyZoom smoke test")
    parser.add_argument(
        "--diagnose",
        action="store_true",
        help="also report the masked JSON shape of every field that didn't match the spec",
    )
    args = parser.parse_args()
    diagnostics = _install_diagnostics() if args.diagnose else None

    username = os.environ.get("AGENCYZOOM_USERNAME") or input("AgencyZoom email: ").strip()
    password = os.environ.get("AGENCYZOOM_PASSWORD") or getpass.getpass("AgencyZoom password: ")
    if not username or not password:
        print("Username and password are required.")
        return 2

    collector = _Collect()
    logging.getLogger("agencyzoom").addHandler(collector)
    logging.getLogger("agencyzoom").setLevel(logging.WARNING)

    print(f"agencyzoom-sdk {__version__} | Python {sys.version.split()[0]} | read-only checks\n")
    results: list[tuple[str, bool, str]] = []
    ids: dict = {}

    def check(name: str, call: Callable[[], Any], remember: str | None = None) -> Any:
        before = len(collector.messages)
        started = time.perf_counter()
        try:
            value = call()
        except AgencyZoomError as exc:
            results.append((name, False, f"{type(exc).__name__}: {exc}"))
            print(f"  ✗ {name:<38} {type(exc).__name__}: {exc}")
            return None
        except Exception as exc:  # report SDK bugs instead of crashing the whole run
            results.append((name, False, f"{type(exc).__name__}: {exc}"))
            print(f"  ✗ {name:<38} UNEXPECTED {type(exc).__name__}: {exc}")
            return None
        ms = (time.perf_counter() - started) * 1000
        mismatched = len(collector.messages) > before
        note = " (fields didn't match the model, see warnings)" if mismatched else ""
        results.append((name, True, note))
        print(f"  ✓ {name:<38} {_count(value):<14} {ms:6.0f} ms{note}")
        if remember:
            items = value if isinstance(value, list) else getattr(value, remember, None)
            ids[remember] = _first_id(items)
        return value

    with AgencyZoom(username, password, rate_limit_per_minute=60) as client:
        print("Authentication")
        if check("auth.login", client.auth.login) is None:
            print("\nLogin failed, so nothing else can be checked. Verify your email and password.")
            return 1

        print("\nReference data (client.settings / client.pipelines)")
        for name in (
            "employees", "lead_sources", "lead_source_categories", "carriers", "product_lines",
            "product_categories", "locations", "loss_reasons", "custom_fields", "csrs", "tags",
            "assign_groups", "life_professionals", "service_categories", "service_priorities",
            "service_resolutions",
        ):  # fmt: skip
            check(f"settings.{name}", getattr(client.settings, name))
        for kind in ("lead", "service"):
            check(f"pipelines.list({kind!r})", lambda k=kind: client.pipelines.list(k))
            check(
                f"pipelines.list_with_stages({kind!r})",
                lambda k=kind: client.pipelines.list_with_stages(k),
            )
            check(f"pipelines.end_stages({kind!r})", lambda k=kind: client.pipelines.end_stages(k))
        check("departments.list", client.departments.list)

        print("\nLeads")
        check("leads.search", lambda: client.leads.search(page_size=5), remember="leads")
        check("leads.count", lambda: client.leads.count())
        check(
            "leads.paginate (first 150)",
            lambda: list(itertools.islice(client.leads.paginate(page_size=100), 150)),
        )
        if ids.get("leads"):
            lead_id = ids["leads"]
            check("leads.get", lambda: client.leads.get(lead_id))
            check("leads.notes.list", lambda: client.leads.notes.list(lead_id))
            check("leads.list_tasks", lambda: client.leads.list_tasks(lead_id))
            check("leads.quotes.list", lambda: client.leads.quotes.list(lead_id))
            check("leads.opportunities.list", lambda: client.leads.opportunities.list(lead_id))
            check("leads.files.list", lambda: client.leads.files.list(customer_referral_id=lead_id))
            check("leads.recycle_events", lambda: client.leads.recycle_events(lead_id))
        else:
            print("  - no leads in this account; skipping per-lead checks")

        print("\nCustomers & policies")
        check(
            "customers.search", lambda: client.customers.search(page_size=5), remember="customers"
        )
        if ids.get("customers"):
            customer_id = ids["customers"]
            check("customers.get", lambda: client.customers.get(customer_id))
            check("customers.list_tasks", lambda: client.customers.list_tasks(customer_id))
            check("customers.list_policies", lambda: client.customers.list_policies(customer_id))
            check(
                "customers.list_ams_policies",
                lambda: client.customers.list_ams_policies(customer_id),
            )
        else:
            print("  - no customers in this account; skipping per-customer checks")

        print("\nTasks, service, messaging, other")
        check("tasks.search", lambda: client.tasks.search(page_size=5), remember="tasks")
        if ids.get("tasks"):
            check("tasks.get", lambda: client.tasks.get(ids["tasks"]))
        check("service_tickets.search", lambda: client.service_tickets.search(page_size=5))
        check("life_health.search", lambda: client.life_health.search(page_size=5))
        check("email_threads.search", lambda: client.email_threads.search(page_size=5))
        check("text_threads.search", lambda: client.text_threads.search(page_size=5))
        check("text_threads.list_producers", client.text_threads.list_producers)
        check("dashboard.sales_data", lambda: client.dashboard.sales_data(period="mtd"))
        check(
            "business_classifications.search",
            lambda: client.business_classifications.search(search_text="auto"),
        )

    passed = sum(ok for _, ok, _ in results)
    failed = [(n, d) for n, ok, d in results if not ok]
    print(f"\n{'=' * 70}\n{passed}/{len(results)} checks passed")
    if failed:
        print("\nFailed:")
        for name, detail in failed:
            print(f"  - {name}: {detail}")
    if collector.messages:
        print("\nModel mismatch warnings (field paths only, no data values):")
        for message in dict.fromkeys(collector.messages):
            print(f"  - {message}")
    if diagnostics:
        print("\nDiagnosis: off-spec fields, with masked shapes of the values received")
        print("(9 = digit, a/A = letter; counts = how many values had that shape)\n")
        for (model, path), entry in sorted(diagnostics.items()):
            print(f"  {model} -> {path}")
            print(f"      spec expects: {entry['error']}")
            for shape, count in entry["shapes"].most_common(4):
                print(f"      received:     {shape}   x{count}")
    elif collector.messages:
        print("\nRe-run with --diagnose to see the shape of each mismatched field.")
    if not failed and not collector.messages:
        print("Everything matched. Safe to release.")
    return 0 if not failed and not collector.messages else 1


if __name__ == "__main__":
    raise SystemExit(main())
