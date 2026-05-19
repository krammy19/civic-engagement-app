import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

BASE_URL = "https://sanjose.legistar.com/"
CALENDAR_URL = urljoin(BASE_URL, "Calendar.aspx")


def extract_link(cell):
    link = cell.find("a")
    if link and link.get("href"):
        return urljoin(BASE_URL, link["href"])
    return None


def parse_table(table):
    meetings = []

    rows = table.find_all("tr")

    for row in rows:
        cols = row.find_all("td")
        if len(cols) < 4:
            continue

        meeting = {
            "date": cols[0].get_text(" ", strip=True),
            "time": cols[1].get_text(" ", strip=True),
            "name": cols[2].get_text(" ", strip=True),
            "location": cols[3].get_text(" ", strip=True),
            "details_url": extract_link(cols[4]) if len(cols) > 4 else None,
            "agenda_url": extract_link(cols[5]) if len(cols) > 5 else None,
            "minutes_url": extract_link(cols[6]) if len(cols) > 6 else None,
            "video_url": extract_link(cols[7]) if len(cols) > 7 else None,
        }

        meetings.append(meeting)

    return meetings


def main():
    response = requests.get(CALENDAR_URL, timeout=30)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    table = soup.find("table", {"id": "ctl00_ContentPlaceHolder1_gridCalendar_ctl00"})

    if not table:
        print("Could not find all-meetings calendar table.")
        return

    meetings = parse_table(table)

    print(f"Parsed {len(meetings)} meetings")

    for meeting in meetings[:10]:
        print(meeting)


if __name__ == "__main__":
    main()