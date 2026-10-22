"""Basic usage: search leads, add a note, and create a follow-up task.

export AGENCYZOOM_USERNAME=owner@agency.com AGENCYZOOM_PASSWORD=...
python examples/quickstart.py
"""

from __future__ import annotations

from agencyzoom import AgencyZoom, NotFoundError


def main() -> None:
    with AgencyZoom(cache_ttl=600) as client:
        sources = {s.id: s.name for s in client.settings.lead_sources()}
        print(f"{len(sources)} lead sources")

        page = client.leads.search(status=0, page_size=5)
        print(f"{page.total_count} new leads; first page:")
        for lead in page.leads or []:
            print(f"  #{lead.id} {lead.firstname} {lead.lastname}")

        if page.leads:
            lead_id = page.leads[0].id
            assert lead_id is not None
            client.leads.notes.create(lead_id, "Reached out via SDK quickstart")
            try:
                detail = client.leads.get(lead_id)
                print("Lead email:", detail.email)
            except NotFoundError:
                print("Lead disappeared in the meantime")


if __name__ == "__main__":
    main()
