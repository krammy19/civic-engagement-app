from typing import List, Optional
from urllib.parse import urljoin
import time

from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import ElementClickInterceptedException, StaleElementReferenceException

from civic_scraper.connectors.base import CivicConnector
from civic_scraper.models import Meeting


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

            self._click_search(driver, wait)

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

                option_xpath = f"//li[normalize-space() = '{option_text}']"
                option = wait.until(
                    EC.element_to_be_clickable((By.XPATH, option_xpath))
                )
                try:
                    option.click()
                except ElementClickInterceptedException:
                    driver.execute_script("arguments[0].click();", option)
                return

            except StaleElementReferenceException as e:
                last_error = e
                time.sleep(1)

        raise last_error

    def _click_search(self, driver, wait):
        for _ in range(3):
            try:
                search_button = wait.until(
                    EC.element_to_be_clickable(
                        (By.ID, "ctl00_ContentPlaceHolder1_btnSearch")
                    )
                )
                search_button.click()
                return
            except StaleElementReferenceException:
                time.sleep(0.5)
        raise RuntimeError("Search button could not be clicked after retries")

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
