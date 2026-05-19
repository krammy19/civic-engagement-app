from dataclasses import dataclass, asdict
from typing import Optional


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

    def to_dict(self):
        return asdict(self)


@dataclass
class AgendaItem:
    file_number: Optional[str]
    title: str
    type: Optional[str]
    agenda_note: Optional[str]
    legislation_url: Optional[str]
    action: Optional[str]
    result: Optional[str]
    version: Optional[str]

    def to_dict(self):
        return asdict(self)