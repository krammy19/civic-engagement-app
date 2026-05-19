from abc import ABC, abstractmethod
from typing import List, Optional
from civic_scraper.models import Meeting


class CivicConnector(ABC):
    @abstractmethod
    def list_meetings(
        self,
        period: Optional[str] = None,
        body: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Meeting]:
        pass