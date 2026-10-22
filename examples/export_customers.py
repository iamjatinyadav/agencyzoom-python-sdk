"""Stream every customer in a state into a CSV file, page by page.

Pagination is lazy, so memory stays flat no matter how many customers there are,
and the built-in rate limiter keeps the export within AgencyZoom's quota.

    python examples/export_customers.py TX customers.csv
"""

from __future__ import annotations

import csv
import sys

from agencyzoom import AgencyZoom

FIELDS = ["id", "firstname", "lastname", "email", "phone", "city", "state"]


def main(state: str, out_path: str) -> None:
    with AgencyZoom() as client, open(out_path, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDS, extrasaction="ignore")
        writer.writeheader()
        count = 0
        for customer in client.customers.paginate(state=state):
            writer.writerow(customer.model_dump())
            count += 1
    print(f"Exported {count} customers to {out_path}")


if __name__ == "__main__":
    main(*sys.argv[1:3])
