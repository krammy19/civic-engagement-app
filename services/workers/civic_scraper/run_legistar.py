import json
import traceback
from pathlib import Path

from civic_scraper.connectors.legistar import LegistarConnector

CITIES = [
    {
        "jurisdiction": "Oakland",
        "calendar_url": "https://oakland.legistar.com/calendar.aspx",
        "body": "Successor Agency and the City Council",
    },
    {
        "jurisdiction": "Culver City",
        "calendar_url": "https://culver-city.legistar.com/Calendar.aspx",
        "body": "City Council Meeting Agenda",
    },
    {
        "jurisdiction": "Mountain View",
        "calendar_url": "https://mountainview.legistar.com/Calendar.aspx",
        "body": "City Council",
    },
    {
        "jurisdiction": "San Francisco",
        "calendar_url": "https://sfgov.legistar.com/Calendar.aspx",
        "body": "Board of Supervisors",
    },
    {
        "jurisdiction": "Santa Clara",
        "calendar_url": "https://santaclara.legistar.com/Calendar.aspx",
        "body": "City Council and Authorities Concurrent",
    },
]

PERIOD = "This Month"
FALLBACK_PERIOD = "Last Month"
MEETING_LIMIT = 5
OUTPUT_ROOT = Path("data/processed")


# -- Phase 1: calendar scraping ------------------------------------------------

def scrape_meetings(city: dict, period: str) -> list:
    connector = LegistarConnector(
        jurisdiction=city["jurisdiction"],
        calendar_url=city["calendar_url"],
        headless=True,
    )
    return connector.list_meetings(period=period, body=city["body"], limit=MEETING_LIMIT)


def save_meetings(jurisdiction: str, meetings: list, period_label: str) -> Path:
    slug = jurisdiction.lower().replace(" ", "-")
    out_dir = OUTPUT_ROOT / slug
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"meetings_{period_label}_sample.json"
    with out_path.open("w", encoding="utf-8") as f:
        json.dump([m.to_dict() for m in meetings], f, indent=2)
    return out_path


# -- Phase 2: agenda item extraction ------------------------------------------

def extract_agenda(city: dict, meeting: dict) -> list:
    connector = LegistarConnector(
        jurisdiction=city["jurisdiction"],
        calendar_url=city["calendar_url"],
        headless=True,
    )
    return connector.get_meeting_details(meeting["meeting_details_url"])


def save_agenda(jurisdiction: str, meeting: dict, items: list) -> Path:
    slug = jurisdiction.lower().replace(" ", "-")
    out_dir = OUTPUT_ROOT / slug
    out_dir.mkdir(parents=True, exist_ok=True)
    date_slug = meeting["date"].replace("/", "-")
    out_path = out_dir / f"agenda_{date_slug}.json"
    with out_path.open("w", encoding="utf-8") as f:
        json.dump([i.to_dict() for i in items], f, indent=2)
    return out_path


# -- Main ----------------------------------------------------------------------

def main():
    # -- Phase 1 ---------------------------------------------------------------
    print(f"\n{'-'*70}")
    print(f"Phase 1 — Calendar  (period='{PERIOD}', limit={MEETING_LIMIT})")
    print(f"{'-'*70}")
    print(f"{'City':<20} {'Status':<8} {'Rows':<6} {'Details URLs'}")
    print(f"{'-'*70}")

    city_meetings = {}

    for city in CITIES:
        name = city["jurisdiction"]
        try:
            meetings = scrape_meetings(city, PERIOD)
            period_label = "this_month"

            # Fallback if no meetings found, or none have published documents yet
            if not meetings or not any(m.meeting_details_url for m in meetings):
                meetings = scrape_meetings(city, FALLBACK_PERIOD)
                period_label = "last_month"

            out_path = save_meetings(name, meetings, period_label)
            with_url = [m for m in meetings if m.meeting_details_url]
            city_meetings[name] = {"city": city, "meetings": meetings, "with_url": with_url}

            label = f"'{PERIOD}'" if period_label == "this_month" else f"'{FALLBACK_PERIOD}' (fallback)"
            print(f"{name:<20} {'OK':<8} {len(meetings):<6} {len(with_url)} have URL  [{label}]")
            print(f"{'':20}          -> {out_path}")
        except Exception as e:
            city_meetings[name] = {"city": city, "meetings": [], "with_url": []}
            print(f"{name:<20} {'FAIL':<8}       {e}")
            traceback.print_exc()

    # -- Phase 2 ---------------------------------------------------------------
    print(f"\n{'-'*70}")
    print(f"Phase 2 — Agenda items  (first meeting with details URL per city)")
    print(f"{'-'*70}")
    print(f"{'City':<20} {'Status':<8} {'Items':<7} {'Sample title'}")
    print(f"{'-'*70}")

    for city in CITIES:
        name = city["jurisdiction"]
        data = city_meetings.get(name, {})
        with_url = data.get("with_url", [])

        if not with_url:
            print(f"{name:<20} {'SKIP':<8}        no meetings with details URL")
            continue

        items, target = [], None
        for candidate in with_url:
            try:
                candidate_dict = candidate.to_dict() if hasattr(candidate, "to_dict") else candidate
                result = extract_agenda(city, candidate_dict)
                if result:
                    items, target = result, candidate_dict
                    break
            except Exception as e:
                print(f"{name:<20} {'WARN':<8}        skipping {candidate.date}: {e}")

        if target is None:
            print(f"{name:<20} {'SKIP':<8}        all detail pages returned 0 items")
        else:
            try:
                out_path = save_agenda(name, target, items)
                sample = items[0].title[:55]
                print(f"{name:<20} {'OK':<8} {len(items):<7} {sample!r}")
                print(f"{'':20}  meeting: {target['date']}  -> {out_path}")
            except Exception as e:
                print(f"{name:<20} {'FAIL':<8}        {e}")
                traceback.print_exc()

    print()


if __name__ == "__main__":
    main()
