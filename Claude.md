# Civic Engagement App — Phase 1 Progress Summary

## Project Vision

The project goal is to build a civic engagement platform capable of:

- Aggregating local government meeting data
- Structuring agendas, minutes, videos, and metadata
- Supporting multiple municipal platforms (Legistar, Granicus, PrimeGov, etc.)
- Eventually enabling search, summarization, AI analysis, alerts, and civic transparency tooling

The current focus is:

> Phase 1 — Robust ingestion and normalization of municipal meeting data.

The first target platform is Legistar.

---

# Development Environment Setup

## Tools Installed / Configured

### VS Code
Installed and configured as the primary IDE.

Recommended extensions:
- Python
- Pylance
- Prettier
- GitLens (future optional)

### Git + GitHub

Repository:
- https://github.com/krammy19/civic-engagement-app

Git installed and configured globally:

```bash
git config --global user.name "Mark Noack"
git config --global user.email "marknoack9@gmail.com"
```

Repo cloned locally.

### Python Environment

Installed:
- Python
- pip
- Selenium
- BeautifulSoup4
- requests

Installed packages:

```bash
pip install selenium beautifulsoup4 requests
```

---

# Current Project Structure

```text
civic-engagement-app/
├── data/
│   ├── raw/
│   └── processed/
│       └── san-jose/
│
├── docs/
│   ├── architecture.md
│   ├── ingestion-pipeline.md
│   └── data-model.md
│
├── scripts/
│   └── scrape_meeting_detail.py
│
├── services/
│   └── workers/
│       └── civic_scraper/
│           ├── __init__.py
│           ├── models.py
│           ├── run_legistar.py
│           └── connectors/
│               ├── __init__.py
│               ├── base.py
│               └── legistar.py
│
├── requirements.txt
└── README.md
```

---

# Architectural Decisions

## Connector-Based Scraping Architecture

The scraper system is intentionally modular.

Key design decision:

> Each municipal platform gets its own connector.

Example future structure:

```text
connectors/
  legistar.py
  granicus.py
  primegov.py
  civicclerk.py
```

This avoids platform-specific assumptions leaking into the entire system.

## Uniform Output Model

Regardless of source platform, all connectors should emit a standardized meeting object.

Current canonical meeting model:

```python
@dataclass
class Meeting:
    source: str
    jurisdiction: str
    body: str
    date: str
    time: Optional[str]
    location: Optional[str]
    meeting_details_url: Optional[str]
    agenda_url: Optional[str]
    minutes_url: Optional[str]
    video_url: Optional[str]
```

Important design principle:

> Flexible parsing, standardized output.

This is critical because different cities expose different Legistar columns.

---

# Legistar Connector Development

## Initial Discovery

The San Jose Legistar page:

https://sanjose.legistar.com/Calendar.aspx

was analyzed.

Findings:

- The meeting calendar is dynamically searchable
- Selenium is required for full archive traversal
- requests-only scraping is insufficient for historical meeting extraction
- The table contains 12 columns, including optional columns such as:
  - Accessible Agenda
  - Accessible Minutes
  - Agenda Packet
  - Video

Example visible columns:

1. Name
2. Meeting Date
3. iCal icon column
4. Meeting Time
5. Meeting Location
6. Meeting Details
7. Agenda
8. Accessible Agenda
9. Agenda Packet
10. Minutes
11. Accessible Minutes
12. Video

---

# Selenium-Based Legistar Connector

## Purpose

The connector:

- Opens Calendar.aspx
- Selects year/body filters
- Executes search
- Traverses paginated results
- Parses meeting rows
- Emits normalized Meeting objects

## Key Technical Decisions

### Selenium Required

The previous city-agenda-scraper project was reviewed and used conceptually as inspiration.

However:
- The old scraper should NOT be copied directly
- Selenium APIs were outdated
- It was too tightly coupled
- It was not designed around normalized data models

Instead:
- A cleaner LegistarConnector class was created
- The architecture now anticipates multiple future connectors

---

# Dynamic Column Mapping

## Important Discovery

Hardcoded column indexes were unreliable.

Problem encountered:
- Different Legistar instances may expose different columns
- Column counts vary
- Optional accessibility columns shift indexes
- Icon columns exist without labels

Initial parser bugs included:
- Date values landing in body fields
- Time values landing in location fields
- Missing video links
- Pagination rows being parsed as meetings

Example bad output:

```json
{
  "body": "12/31/2024",
  "date": "",
  "time": "Council Chambers CANCELLED"
}
```

## Corrected Approach

The parser was redesigned to:

- Extract table headers dynamically
- Normalize header names
- Preserve blank/icon columns for alignment
- Map rows based on headers instead of hardcoded indexes

Core helper methods:

```python
_extract_headers()
_map_row_by_headers()
_normalize_header()
```

This significantly improved resilience.

---

# JSON Output

Current output location:

```text
data/processed/san-jose/meetings_2024_city-council.json
```

Current behavior:
- File is overwritten on each run
- No append behavior

Write mode:

```python
open(..., "w")
```

---

# Running the Scraper

## Current Command

From repo root:

```bash
PYTHONPATH=services/workers python services/workers/civic_scraper/run_legistar.py
```

Reason:
- civic_scraper is nested under services/workers
- PYTHONPATH temporarily adds that folder to module resolution

---

# VS Code Debugger Setup

A project-local debugger config was created.

File:

```text
.vscode/launch.json
```

Purpose:
- Allows debugging without manually setting PYTHONPATH
- Supports breakpoints inside scraper code
- Applies ONLY to this repo/workspace

---

# Major Lessons / Discoveries

## 1. Legistar HTML Is Messy

Observed issues:
- Hidden columns
- Dynamic rendering
- Non-uniform city configurations
- Pager rows mixed with data rows
- Accessibility variants shifting columns

Conclusion:

> The connector layer must be adaptive.

## 2. Selenium Is Necessary

For:
- historical archives
- pagination
- dropdown filtering
- future agenda extraction

requests-only scraping is insufficient.

## 3. Data Normalization Is Critical

The app should NOT expose raw platform-specific schemas.

Instead:

```text
Platform HTML
    ↓
Connector Parser
    ↓
Normalized Meeting Model
    ↓
Downstream AI / Search / Alerts
```

---

# Current State of the Project

## Working

- GitHub repo initialized
- VS Code environment functional
- Selenium installed
- Legistar connector implemented
- Selenium search flow working
- Pagination traversal working
- JSON export working
- Dynamic header mapping partially implemented

## Still In Progress

- Final cleanup of Legistar column mapping
- Robust handling of optional columns
- Reliable extraction of video URLs
- Filtering out non-meeting rows
- Validation across multiple cities

---

# Immediate Next Steps

## 1. Finalize Robust Legistar Parsing

Need:
- stable header-to-cell alignment
- support for variable Legistar schemas
- stronger row validation

## 2. Meeting Detail Extraction

Next major milestone:

Scrape individual Meeting Details pages to extract:

- agenda items
- item descriptions
- attachments
- vote results
- transcripts (future)
- video metadata

This will likely become:

```python
fetch_meeting_detail(url)
fetch_agenda_items(url)
```

## 3. Expand Data Model

Future entities likely include:

```python
AgendaItem
Vote
Attachment
SpeakerComment
TranscriptChunk
```

---

# Long-Term Direction

Potential future capabilities:

- AI summaries of meetings
- Civic issue tracking
- Personalized alerts
- Searchable transcript archive
- Political trend analysis
- Public-facing civic dashboard
- RAG pipeline over municipal records
- AI-generated meeting digests
- Multi-city ingestion network

---

# Key Conceptual Direction

The project is no longer thought of as:

> “a scraper script.”

Instead, it is:

> A civic data ingestion and normalization platform.

