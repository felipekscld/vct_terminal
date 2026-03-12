"""Best-effort scraper for Bet365 odds pages."""

from __future__ import annotations

import re
import unicodedata
from typing import Any
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


class Bet365Scraper:
    """Try to scrape esports odds from Bet365 public pages."""

    BASE_URL = "https://www.bet365.com"
    SEARCH_URLS = (
        "https://www.bet365.com",
        "https://www.bet365.com/#/IP/B151",
        "https://www.bet365.com/#/AS/B151",
        "https://www.bet365.com/#/AC/B18/C20604387/D43/E181157/F43/",
    )
    TIMEOUT = 12

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
            }
        )

    def search_match(self, team1: str, team2: str) -> str | None:
        """Find a Bet365 match page URL containing both team names."""
        aliases_a = self._team_aliases(team1)
        aliases_b = self._team_aliases(team2)

        for url in self.SEARCH_URLS:
            try:
                resp = self.session.get(url, timeout=self.TIMEOUT, allow_redirects=True)
            except Exception:
                continue

            if resp.status_code >= 400:
                continue

            soup = BeautifulSoup(resp.content, "html.parser")
            found = self._find_match_link(soup, aliases_a, aliases_b, resp.url)
            if found:
                return found

            page_text = self._normalize_text(soup.get_text(separator=" ", strip=True))
            if self._contains_both_teams(page_text, aliases_a, aliases_b):
                return resp.url

        return None

    def _find_match_link(
        self,
        soup: BeautifulSoup,
        aliases_a: set[str],
        aliases_b: set[str],
        page_url: str,
    ) -> str | None:
        for link in soup.find_all("a", href=True):
            parts = [
                link.get_text(" ", strip=True),
                str(link.get("aria-label") or ""),
                str(link.get("title") or ""),
            ]
            text = self._normalize_text(" ".join(parts))
            if self._contains_both_teams(text, aliases_a, aliases_b):
                return self._to_absolute_url(str(link["href"]), page_url)

        for node in soup.find_all(["div", "article", "li", "section"]):
            text = self._normalize_text(node.get_text(" ", strip=True))
            if not self._contains_both_teams(text, aliases_a, aliases_b):
                continue
            link = node.find("a", href=True)
            if link:
                return self._to_absolute_url(str(link["href"]), page_url)

        return None

    def scrape_odds(self, match_url: str, team1: str, team2: str) -> list[dict[str, Any]]:
        """Extract odds from a specific Bet365 match page."""
        try:
            resp = self.session.get(match_url, timeout=self.TIMEOUT, allow_redirects=True)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.content, "html.parser")
        except Exception:
            return []

        aliases_a = self._team_aliases(team1)
        aliases_b = self._team_aliases(team2)
        page_text = self._normalize_text(soup.get_text(separator=" ", strip=True))
        if not self._contains_both_teams(page_text, aliases_a, aliases_b):
            return []

        odds_list: list[dict[str, Any]] = []
        market_blocks = soup.find_all("div", class_=re.compile(r"market|Market|gl-Market", re.IGNORECASE))

        for block in market_blocks:
            title = self._extract_title(block)
            if not title:
                continue

            market_type, map_number = self._market_type_from_title(title)
            outcome_names = [
                n.get_text(" ", strip=True)
                for n in block.find_all(
                    ["span", "div"], class_=re.compile(r"name|Name|label|Label|Participant", re.IGNORECASE)
                )
            ]
            prices = [
                self._parse_decimal(p.get_text(" ", strip=True))
                for p in block.find_all(
                    ["span", "div"], class_=re.compile(r"odds|price|Price|Odds", re.IGNORECASE)
                )
            ]

            clean_names = [n for n in outcome_names if n]
            clean_prices = [p for p in prices if p and p > 1.0]
            if not clean_names or not clean_prices:
                continue

            for selection, odd in zip(clean_names, clean_prices):
                odds_list.append(
                    {
                        "bookmaker": "bet365",
                        "market_type": market_type,
                        "selection": selection,
                        "odds_value": odd,
                        "map_number": map_number,
                    }
                )

        return odds_list

    @staticmethod
    def _extract_title(block: BeautifulSoup) -> str:
        title = block.find(
            ["h2", "h3", "h4", "span", "div"], class_=re.compile(r"title|Title|header|Header", re.IGNORECASE)
        )
        if title:
            return title.get_text(" ", strip=True)
        return ""

    @staticmethod
    def _market_type_from_title(title: str) -> tuple[str, int | None]:
        t = title.lower()
        map_match = re.search(r"map\s*(\d)", t)
        map_number = int(map_match.group(1)) if map_match else None

        if "match" in t and "winner" in t:
            return "match_winner", None
        if "winner" in t and map_number is not None:
            return "map_winner", map_number
        if "overtime" in t and map_number is not None:
            return "map_ot", map_number
        if "handicap" in t and map_number is not None:
            return "map_handicap", map_number
        if "total" in t and "round" in t and map_number is not None:
            return "map_total_rounds", map_number
        if "correct" in t and "score" in t:
            return "correct_score", None

        return "special_market", map_number

    @staticmethod
    def _parse_decimal(text: str) -> float | None:
        match = re.search(r"\d+[\.,]?\d*", text)
        if not match:
            return None
        try:
            return float(match.group(0).replace(",", "."))
        except ValueError:
            return None

    @staticmethod
    def _normalize_text(text: str) -> str:
        if not text:
            return ""
        normalized = unicodedata.normalize("NFKD", text)
        ascii_text = "".join(ch for ch in normalized if not unicodedata.combining(ch))
        ascii_text = ascii_text.lower()
        ascii_text = re.sub(r"[^a-z0-9]+", " ", ascii_text)
        return re.sub(r"\s+", " ", ascii_text).strip()

    @staticmethod
    def _team_aliases(team: str) -> set[str]:
        base = Bet365Scraper._normalize_text(team)
        words = [w for w in base.split() if w]
        aliases: set[str] = set()
        if base:
            aliases.add(base)
            aliases.add(base.replace(" ", ""))
        if words:
            aliases.add(words[0])
        if len(words) > 1:
            aliases.add("".join(w[0] for w in words if w))
        return {a for a in aliases if len(a) >= 2}

    @staticmethod
    def _contains_team(text: str, aliases: set[str]) -> bool:
        for alias in aliases:
            if len(alias) <= 3:
                if re.search(rf"\b{re.escape(alias)}\b", text):
                    return True
            elif alias in text:
                return True
        return False

    @classmethod
    def _contains_both_teams(cls, text: str, aliases_a: set[str], aliases_b: set[str]) -> bool:
        return cls._contains_team(text, aliases_a) and cls._contains_team(text, aliases_b)

    @staticmethod
    def _to_absolute_url(href: str, page_url: str) -> str:
        if href.startswith("#"):
            return page_url
        return urljoin(page_url, href)

    def close(self) -> None:
        self.session.close()


def scrape_bet365(team1: str, team2: str) -> list[dict[str, Any]]:
    """Convenience wrapper for Bet365 scraping."""
    scraper = Bet365Scraper()
    try:
        match_url = scraper.search_match(team1, team2)
        if not match_url:
            return []
        return scraper.scrape_odds(match_url, team1, team2)
    finally:
        scraper.close()
