from typing import List, Optional
from urllib.parse import urljoin
import time

import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import StaleElementReferenceException, TimeoutException

from civic_scraper.connectors.base import CivicConnector
from civic_scraper.models import Meeting, AgendaItem


# Alternate lowercase header names some Legistar sites use for each canonical column
_COLUMN_ALIASES: dict[str, list[str]] = {
    "name": ["body"],
    "meeting date": ["date"],
    "meeting time": ["time"],
    "meeting location": ["location"],
    "meeting details": ["details"],
}


class LegistarConnector(CivicConnector):
    def __init__(self, jurisdiction: str, calendar_url: str, headless: bool = True):
        self.jurisdiction = jurisdiction
        self.calendar_url = calendar_url
        idx = calendar_url.lower().find("/calendar.aspx")
        self.base_url = (calendar_url[:idx] if idx != -1 else calendar_url) + "/"
        self.headless = headless

    def _create_driver(self):
        options = Options()
        if self.headless:
            options.add_argument("--headless=new")
        options.add_argument("--window-size=1400,1000")
        return webdriver.Chrome(options=options)

    def list_meetings(
        self,
        period: Optional[str] = None,
        body: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Meeting]:
        driver = self._create_driver()

        try:
            driver.get(self.calendar_url)
            wait = WebDriverWait(driver, 20)

            if period is not None:
                self._select_dropdown_option(
                    driver,
                    wait,
                    input_id="ctl00_ContentPlaceHolder1_lstYears_Input",
                    option_text=period,
                )

            time.sleep(1)

            if body is not None:
                self._select_dropdown_option(
                    driver,
                    wait,
                    input_id="ctl00_ContentPlaceHolder1_lstBodies_Input",
                    option_text=body,
                )
                time.sleep(1)

            self._click_search(driver)

            meetings: List[Meeting] = []
            remaining = limit

            while True:
                wait.until(
                    EC.presence_of_element_located(
                        (By.ID, "ctl00_ContentPlaceHolder1_gridCalendar_ctl00")
                    )
                )

                page_meetings = self._parse_meetings(driver.page_source, body or "", remaining)
                meetings.extend(page_meetings)

                if remaining is not None:
                    remaining -= len(page_meetings)
                    if remaining <= 0:
                        break

                if not self._go_to_next_page(driver, wait):
                    break

            return meetings

        finally:
            driver.quit()

    def _select_dropdown_option(self, driver, wait, input_id: str, option_text: str):
        last_error = None

        for _ in range(3):
            try:
                dropdown_input = wait.until(
                    EC.element_to_be_clickable((By.ID, input_id))
                )
                dropdown_input.click()

                # Use presence_of_element_located (not clickable) so that options
                # deep in a long list are found even when outside the visible viewport.
                option_xpath = f"//li[contains(normalize-space(), '{option_text}')]"
                option = wait.until(
                    EC.presence_of_element_located((By.XPATH, option_xpath))
                )
                driver.execute_script("arguments[0].scrollIntoView(true);", option)
                time.sleep(0.2)
                driver.execute_script("arguments[0].click();", option)
                return

            except StaleElementReferenceException as e:
                last_error = e
                time.sleep(1)

        raise last_error

    def _click_search(self, driver):
        # Use a longer timeout here — body selection can trigger a loading overlay
        # that temporarily blocks the button beyond the standard wait window.
        search_wait = WebDriverWait(driver, 40)
        for _ in range(3):
            try:
                search_button = search_wait.until(
                    EC.element_to_be_clickable(
                        (By.ID, "ctl00_ContentPlaceHolder1_btnSearch")
                    )
                )
                search_button.click()
                return
            except StaleElementReferenceException:
                time.sleep(0.5)
            except TimeoutException:
                # Some Legistar sites auto-search on dropdown change and have no
                # explicit search button; the table will already be populated.
                return
        raise RuntimeError("Search button stale after retries")

    def _extract_headers(self, table) -> list:
        """Return one header string per column, expanding colspan so indices align with td columns.

        Prefers <th class="rgHeader"> (RadGrid column headers) to avoid picking up
        pager rows, which also use <th> but appear before the column header row.
        Falls back to the first <tr> containing any <th> for non-standard layouts.
        """
        def _expand(ths):
            headers = []
            for th in ths:
                text = th.get_text(" ", strip=True)
                colspan = int(th.get("colspan", 1))
                headers.extend([text] * colspan)
            return headers

        rg_headers = table.find_all("th", class_="rgHeader")
        if rg_headers:
            return _expand(rg_headers)

        search_root = table.find("thead") or table
        for tr in search_root.find_all("tr"):
            ths = tr.find_all("th")
            if ths:
                return _expand(ths)
        return []

    def _resolve_col(self, col_index: dict, col_name: str) -> Optional[int]:
        """Look up a column index by canonical name, falling back to known aliases."""
        key = col_name.lower()
        if key in col_index:
            return col_index[key]
        for alt in _COLUMN_ALIASES.get(key, []):
            if alt in col_index:
                return col_index[alt]
        return None

    def _get_cell_text(self, cols: list, col_index: dict, col_name: str) -> Optional[str]:
        idx = self._resolve_col(col_index, col_name)
        if idx is None or idx >= len(cols):
            return None
        return cols[idx].get_text(" ", strip=True)

    def _get_cell_link(self, cols: list, col_index: dict, col_name: str) -> Optional[str]:
        idx = self._resolve_col(col_index, col_name)
        if idx is None or idx >= len(cols):
            return None
        return self._extract_link(cols[idx])

    def _parse_meetings(self, html: str, body: str, limit: Optional[int] = None) -> List[Meeting]:
        soup = BeautifulSoup(html, "html.parser")
        table = soup.find("table", {"id": "ctl00_ContentPlaceHolder1_gridCalendar_ctl00"})

        if not table:
            return []

        headers = self._extract_headers(table)
        col_index = {name.lower(): i for i, name in enumerate(headers)}

        meetings = []

        tbodies = table.find_all("tbody") or [table]
        done = False
        for tbody in tbodies:
            if done:
                break
            for row in tbody.find_all("tr", recursive=False):
                if "rgPager" in (row.get("class") or []):
                    continue

                cols = row.find_all("td")
                if not cols:
                    continue

                date = self._get_cell_text(cols, col_index, "Meeting Date")
                if date is None:
                    continue

                meeting = Meeting(
                    source="legistar",
                    jurisdiction=self.jurisdiction,
                    body=self._get_cell_text(cols, col_index, "Name") or body,
                    date=date,
                    time=self._get_cell_text(cols, col_index, "Meeting Time"),
                    location=self._get_cell_text(cols, col_index, "Meeting Location"),
                    meeting_details_url=self._get_cell_link(cols, col_index, "Meeting Details"),
                    agenda_url=self._get_cell_link(cols, col_index, "Agenda"),
                    minutes_url=self._get_cell_link(cols, col_index, "Minutes"),
                    video_url=self._get_cell_link(cols, col_index, "Video"),
                )

                meetings.append(meeting)
                if limit is not None and len(meetings) >= limit:
                    done = True
                    break

        return meetings

    def _extract_link(self, cell) -> Optional[str]:
        link = cell.find("a")
        if link and link.get("href"):
            return urljoin(self.base_url, link["href"])
        return None

    def _go_to_next_page(self, driver, wait) -> bool:
        try:
            next_button = driver.find_element(By.LINK_TEXT, "Next")
            classes = next_button.get_attribute("class") or ""

            if "rgPageDisabled" in classes:
                return False

            next_button.click()
            wait.until(EC.staleness_of(next_button))
            return True

        except Exception:
            return False

    def get_meeting_details(self, meeting_details_url: str) -> List[AgendaItem]:
        """Fetch and parse agenda items from a meeting details page.

        Args:
            meeting_details_url: URL to the meeting details page

        Returns:
            List of AgendaItem objects for significant items (those with File # entries)
        """
        try:
            response = requests.get(meeting_details_url, timeout=30)
            response.raise_for_status()
            return self._parse_agenda_items(response.text)
        except Exception:
            return []

    def _parse_agenda_items(self, html: str) -> List[AgendaItem]:
        soup = BeautifulSoup(html, "html.parser")
        table = soup.find("table", {"id": "ctl00_ContentPlaceHolder1_gridMain_ctl00"})
        if not table:
            return []

        headers = self._extract_headers(table)
        # Non-breaking spaces appear in header text on some Legistar sites
        headers = [h.replace("\xa0", " ") for h in headers]
        col_index = {h.lower(): i for i, h in enumerate(headers)}

        def cell_text(cells, name):
            idx = col_index.get(name)
            if idx is None or idx >= len(cells):
                return None
            return cells[idx].get_text(" ", strip=True).replace("\xa0", " ") or None

        items = []
        tbodies = table.find_all("tbody") or [table]
        for tbody in tbodies:
            for row in tbody.find_all("tr", recursive=False):
                if "rgPager" in (row.get("class") or []):
                    continue
                cells = row.find_all("td")
                if not cells:
                    continue

                file_idx = col_index.get("file #")
                if file_idx is None or file_idx >= len(cells):
                    continue
                legislation_url = self._extract_legislation_link(cells[file_idx])
                if not legislation_url:
                    continue

                items.append(AgendaItem(
                    file_number=cell_text(cells, "file #"),
                    version=cell_text(cells, "ver."),
                    agenda_note=cell_text(cells, "agenda note"),
                    type=cell_text(cells, "type"),
                    title=cell_text(cells, "title"),
                    action=cell_text(cells, "action"),
                    result=cell_text(cells, "result"),
                    legislation_url=legislation_url,
                ))

        return items

    def _extract_legislation_link(self, cell) -> Optional[str]:
        link = cell.find("a")
        if link and link.get("href") and "LegislationDetail.aspx" in link["href"]:
            return urljoin(self.base_url, link["href"])
        return None
