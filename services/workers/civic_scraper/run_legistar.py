import json
import traceback
from pathlib import Path

from civic_scraper.connectors.legistar import LegistarConnector

CITIES = [
    {
        "jurisdiction": "Oakland",
        "calendar_url": "https://oakland.legistar.com/calendar.aspx",
        "body": "City Council",
    },
    {
        "jurisdiction": "Culver City",
        "calendar_url": "https://culver-city.legistar.com/Calendar.aspx",
        "body": "City Council",
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
LIMIT = 5
OUTPUT_ROOT = Path("data/processed")


def test_city(city: dict):
    connector = LegistarConnector(
        jurisdiction=city["jurisdiction"],
        calendar_url=city["calendar_url"],
        headless=True,
    )
    return connector.list_meetings(period=PERIOD, body=city["body"], limit=LIMIT)


def save_results(jurisdiction: str, meetings: list):
    slug = jurisdiction.lower().replace(" ", "-")
    out_dir = OUTPUT_ROOT / slug
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "meetings_this_month_sample.json"
    with out_path.open("w", encoding="utf-8") as f:
        json.dump([m.to_dict() for m in meetings], f, indent=2)
    return out_path


def summarize_fields(meetings: list) -> str:
    if not meetings:
        return "(no meetings)"
    first = meetings[0].to_dict()
    populated = [k for k, v in first.items() if v is not None and k not in ("source", "jurisdiction")]
    missing = [k for k, v in first.items() if v is None and k not in ("source", "jurisdiction")]
    parts = [f"ok: {', '.join(populated)}"]
    if missing:
        parts.append(f"null: {', '.join(missing)}")
    return " | ".join(parts)


def main():
    print(f"\nLegistar scraper test — period='{PERIOD}', limit={LIMIT} rows per city\n")
    print(f"{'City':<20} {'Status':<8} {'Rows':<6} Fields")
    print("-" * 80)

    for city in CITIES:
        name = city["jurisdiction"]
        try:
            meetings = test_city(city)
            out_path = save_results(name, meetings)
            status = "OK"
            rows = len(meetings)
            fields = summarize_fields(meetings)
            print(f"{name:<20} {status:<8} {rows:<6} {fields}")
            print(f"{'':20}          -> {out_path}")
        except Exception as e:
            print(f"{name:<20} {'FAIL':<8}       {e}")
            traceback.print_exc()

    print()


if __name__ == "__main__":
    main()
