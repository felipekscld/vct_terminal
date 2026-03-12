"""Betano-only scraper using Playwright network capture with DOM fallback."""

from __future__ import annotations

import hashlib
import html as html_lib
import os
import random
import re
import time
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class BetanoScraperConfig:
    headless: bool = _env_bool("BETANO_SCRAPER_HEADLESS", False)
    timeout_ms: int = int(os.getenv("BETANO_SCRAPER_TIMEOUT_MS", "30000"))
    retries: int = int(os.getenv("BETANO_SCRAPER_RETRIES", "3"))
    proxy_url: str | None = (os.getenv("BETANO_PROXY_URL") or "").strip() or None
    debug: bool = _env_bool("BETANO_SCRAPER_DEBUG", False)
    profile_dir: Path = Path("data/browser_profile/betano")


class BetanoScraperError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class BetanoStealthScraper:
    BETANO_MASTER_URLS = (
        "https://www.betano.bet.br/sport/esports/competicoes/valorant/189513/?sl=205971",
        "https://www.betano.bet.br/sport/esports/competicoes/valorant/189513/",
    )
    BETANO_URLS = (
        "https://www.betano.bet.br/sport/esports/competicoes/valorant/189513/",
        "https://www.betano.bet.br/sport/esports/competicoes/valorant/189513/?sl=205971",
        "https://www.betano.bet.br/sport/esports/competicoes/valorant/",
        "https://www.betano.bet.br/esportes/esports/competicoes/valorant/",
        "https://www.betano.bet.br/sport/esports/valorant/",
        "https://www.betano.com/sport/esports/competicoes/valorant/",
        "https://www.betano.com/en/sport/esports/competitions/valorant/",
        "https://www.betano.com/sport/esports/valorant/",
    )

    USER_AGENT = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/133.0.0.0 Safari/537.36"
    )

    def __init__(self, config: BetanoScraperConfig | None = None):
        self.config = config or BetanoScraperConfig()

    def scrape_match_odds(
        self,
        team1: str,
        team2: str,
        team1_tag: str | None = None,
        team2_tag: str | None = None,
    ) -> list[dict[str, Any]]:
        last_error: BetanoScraperError | None = None

        for attempt in range(1, max(self.config.retries, 1) + 1):
            try:
                entries = self._scrape_once(team1, team2, team1_tag=team1_tag, team2_tag=team2_tag)
                if entries:
                    return entries
                last_error = BetanoScraperError(
                    "betano_markets_not_found",
                    "Mercados da Betano nao foram encontrados para o confronto.",
                )
            except BetanoScraperError as exc:
                last_error = exc
                if exc.code in {"betano_browser_closed"}:
                    break
            except Exception as exc:
                if self._is_closed_error(exc):
                    last_error = BetanoScraperError(
                        "betano_browser_closed",
                        "Navegador/contexto da Betano foi fechado durante a coleta.",
                    )
                    break
                last_error = BetanoScraperError(
                    "betano_parse_failed",
                    f"Falha inesperada no scraper da Betano: {exc}",
                )

            if attempt < self.config.retries:
                backoff = min(1.5 * attempt, 4.0)
                time.sleep(backoff)

        if last_error is not None:
            raise last_error
        raise BetanoScraperError("betano_parse_failed", "Falha desconhecida no scraper da Betano.")

    def _scrape_once(
        self,
        team1: str,
        team2: str,
        team1_tag: str | None,
        team2_tag: str | None,
    ) -> list[dict[str, Any]]:
        try:
            from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
            from playwright.sync_api import sync_playwright
        except Exception as exc:
            raise BetanoScraperError(
                "betano_parse_failed",
                f"Playwright nao disponivel. Instale dependencias: {exc}",
            ) from exc

        try:
            from playwright_stealth import stealth_sync
        except Exception:
            stealth_sync = None

        aliases_a = self._team_aliases(team1, team1_tag)
        aliases_b = self._team_aliases(team2, team2_tag)
        if not aliases_a or not aliases_b:
            raise BetanoScraperError("betano_match_not_found", "Times invalidos para busca na Betano.")

        self.config.profile_dir.mkdir(parents=True, exist_ok=True)

        captured_payloads: list[tuple[str, Any]] = []

        with sync_playwright() as playwright:
            context_args: dict[str, Any] = {
                "user_data_dir": str(self.config.profile_dir),
                "headless": bool(self.config.headless),
                "locale": "pt-BR",
                "timezone_id": "America/Sao_Paulo",
                "user_agent": self.USER_AGENT,
                "viewport": {"width": 1366, "height": 900},
                "service_workers": "block",
                "ignore_https_errors": True,
                "args": [
                    "--disable-blink-features=AutomationControlled",
                    "--no-first-run",
                    "--no-default-browser-check",
                    "--disable-dev-shm-usage",
                ],
            }
            if self.config.proxy_url:
                context_args["proxy"] = {"server": self.config.proxy_url}

            context = None
            page = None
            try:
                context = playwright.chromium.launch_persistent_context(**context_args)
                page = context.new_page()

                if stealth_sync is not None:
                    try:
                        stealth_sync(page)
                    except Exception:
                        pass

                def on_response(response):
                    if response.status >= 400:
                        return
                    url = response.url.lower()
                    content_type = (response.headers or {}).get("content-type", "").lower()
                    is_json = "json" in content_type or any(k in url for k in ("/api/", "odds", "events", "markets"))
                    if not is_json:
                        return
                    try:
                        payload = response.json()
                    except Exception:
                        return
                    captured_payloads.append((response.url, payload))

                page.on("response", on_response)

                opened = False
                for url in self.BETANO_URLS:
                    try:
                        page.goto(url, wait_until="domcontentloaded", timeout=self.config.timeout_ms)
                        opened = True
                        break
                    except PlaywrightTimeoutError:
                        continue
                    except Exception as exc:
                        if self._is_closed_error(exc):
                            raise BetanoScraperError(
                                "betano_browser_closed",
                                "Navegador/contexto da Betano foi fechado durante a abertura.",
                            ) from exc
                        continue

                if not opened:
                    raise BetanoScraperError(
                        "betano_challenge_blocked",
                        "Nao foi possivel abrir a Betano (timeout/bloqueio).",
                    )

                self._human_pause(page)
                self._accept_cookies_if_needed(page)
                self._accept_age_gate_if_needed(page)
                self._human_pause(page)
                self._open_master_competition(page)
                self._human_pause(page)
                opened_match = self._open_match_if_listed(page, aliases_a, aliases_b)
                tab_snapshots: list[str] = []
                if opened_match:
                    match_url = page.url
                    tab_snapshots = self._interact_with_match_page(page, match_url=match_url)
                    self._ensure_match_url(page, match_url)
                self._human_pause(page)
                self._scroll_feed(page)
                page.wait_for_timeout(2500)
                if self.config.debug:
                    odds_links = 0
                    try:
                        odds_links = int(page.eval_on_selector_all("a[href*='/odds/']", "els => els.length"))
                    except Exception:
                        odds_links = 0
                    print(
                        "[BETANO DEBUG] "
                        f"final_url={page.url} payloads={len(captured_payloads)} odds_links={odds_links} opened_match={opened_match}"
                    )

                payload_entries, matched_event = self._extract_entries_from_payloads(
                    captured_payloads,
                    aliases_a,
                    aliases_b,
                    team1,
                    team2,
                    known_match_page=opened_match,
                )
                dom_entries: list[dict[str, Any]] = []
                html_sources: list[str] = [page.content(), *tab_snapshots]
                for html_snapshot in html_sources:
                    dom_entries.extend(
                        self._extract_entries_from_dom(
                            html_snapshot,
                            team1,
                            team2,
                            aliases_a,
                            aliases_b,
                            skip_team_validation=opened_match,
                        )
                    )
                dom_entries = self._dedup_entries(dom_entries)
                entries = self._dedup_entries([*payload_entries, *dom_entries])
                if self.config.debug:
                    print(
                        "[BETANO DEBUG] "
                        f"payload_entries={len(payload_entries)} dom_entries={len(dom_entries)} merged_entries={len(entries)} snapshots={len(tab_snapshots)}"
                    )

                html = page.content()
                page_url = page.url
                challenge = self._looks_like_challenge(html)
                not_found = self._looks_like_not_found(html)

                if entries:
                    return entries
                if not_found:
                    raise BetanoScraperError(
                        "betano_match_not_found",
                        f"Betano retornou pagina sem competicao valida ({page_url}).",
                    )
                if challenge:
                    raise BetanoScraperError(
                        "betano_challenge_blocked",
                        "Betano retornou challenge anti-bot durante a coleta.",
                    )
                if not matched_event and not opened_match:
                    raise BetanoScraperError(
                        "betano_match_not_found",
                        f"Confronto {team1} vs {team2} nao encontrado na Betano.",
                    )
                raise BetanoScraperError(
                    "betano_markets_not_found",
                    "Confronto encontrado, mas mercados/odds nao foram extraidos.",
                )
            except BetanoScraperError:
                raise
            except Exception as exc:
                if self._is_closed_error(exc):
                    raise BetanoScraperError(
                        "betano_browser_closed",
                        "Navegador/contexto da Betano foi fechado durante a coleta.",
                    ) from exc
                raise
            finally:
                if context is not None:
                    try:
                        context.close()
                    except Exception:
                        pass

    def _human_pause(self, page: Any) -> None:
        delay = random.randint(250, 900)
        try:
            page.wait_for_timeout(delay)
        except Exception:
            return

    def _scroll_feed(self, page: Any) -> None:
        for _ in range(3):
            try:
                page.mouse.wheel(0, random.randint(700, 1300))
            except Exception:
                pass
            try:
                page.wait_for_timeout(random.randint(300, 800))
            except Exception:
                return

    def _accept_cookies_if_needed(self, page: Any) -> None:
        labels = (
            "Aceitar",
            "Aceitar tudo",
            "Accept",
            "Accept all",
            "Concordo",
            "I agree",
        )
        for label in labels:
            try:
                locator = page.get_by_role("button", name=re.compile(re.escape(label), re.IGNORECASE))
                if locator.count() > 0:
                    locator.first.click(timeout=1000)
                    page.wait_for_timeout(400)
                    return
            except Exception:
                continue
        self._click_text_action(page, ("aceitar", "accept", "consent", "concordo"))

    def _accept_age_gate_if_needed(self, page: Any) -> None:
        labels = (
            r"tenho\s+mais\s+de\s+18",
            r"i.?m\s+over\s+18",
            r"sou\s+maior\s+de\s+18",
            r"\b18\+\b",
        )
        for label in labels:
            try:
                locator = page.get_by_role("button", name=re.compile(label, re.IGNORECASE))
                if locator.count() > 0:
                    locator.first.click(timeout=1200)
                    page.wait_for_timeout(500)
                    return
            except Exception:
                continue
            try:
                locator = page.get_by_role("link", name=re.compile(label, re.IGNORECASE))
                if locator.count() > 0:
                    locator.first.click(timeout=1200)
                    page.wait_for_timeout(500)
                    return
            except Exception:
                continue
        self._click_text_action(page, ("18", "maior", "over 18"))

    def _click_text_action(self, page: Any, includes: tuple[str, ...]) -> bool:
        try:
            clicked = page.evaluate(
                """(includes) => {
                    const elems = Array.from(document.querySelectorAll('button, a, [role=\"button\"], [role=\"link\"], div, span'));
                    const norm = (s) => (s || '')
                        .toLowerCase()
                        .normalize('NFD')
                        .replace(/[\\u0300-\\u036f]/g, '')
                        .replace(/\\s+/g, ' ')
                        .trim();
                    const wanted = (includes || []).map(norm).filter(Boolean);
                    for (const el of elems) {
                        const t = norm(el.textContent);
                        if (!t) continue;
                        if (wanted.some(k => t.includes(k))) {
                            try { el.click(); return true; } catch (_) {}
                        }
                    }
                    return false;
                }""",
                list(includes),
            )
            page.wait_for_timeout(400)
            return bool(clicked)
        except Exception:
            return False

    def _open_master_competition(self, page: Any) -> None:
        for url in self.BETANO_MASTER_URLS:
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=self.config.timeout_ms)
                page.wait_for_timeout(1000)
                return
            except Exception:
                continue

    def _force_valorant_navigation(self, page: Any) -> None:
        for href in (
            "/sport/esports/competicoes/valorant/189513/",
            "/sport/esports/competicoes/valorant/189513/?sl=205971",
            "/sport/esports/competicoes/valorant/",
            "/esportes/esports/competicoes/valorant/",
            "/sport/esports/valorant/",
            "/en/sport/esports/competitions/valorant/",
        ):
            try:
                current = page.url.rstrip("/")
                target = f"https://www.betano.bet.br{href}" if "betano.bet.br" in current else f"https://www.betano.com{href}"
                page.goto(target, wait_until="domcontentloaded", timeout=self.config.timeout_ms)
                page.wait_for_timeout(1000)
                if self._looks_like_not_found(page.content()):
                    continue
                return
            except Exception:
                continue

    def _open_match_if_listed(self, page: Any, aliases_a: set[str], aliases_b: set[str]) -> bool:
        for _ in range(10):
            href = self._find_match_href_on_page(page, aliases_a, aliases_b)
            if href:
                try:
                    page.goto(href, wait_until="domcontentloaded", timeout=self.config.timeout_ms)
                    page.wait_for_timeout(1200)
                    return True
                except Exception:
                    pass

            try:
                page.mouse.wheel(0, 900)
                page.wait_for_timeout(350)
            except Exception:
                return False

            advanced = self._advance_master_carousel(page)
            if not advanced:
                continue
            try:
                page.wait_for_timeout(700)
            except Exception:
                return False

        return False

    def _interact_with_match_page(self, page: Any, match_url: str) -> list[str]:
        snapshots: list[str] = []
        seen_hashes: set[str] = set()

        for url in self._build_match_tab_urls(match_url):
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=self.config.timeout_ms)
                page.wait_for_timeout(900)
                self._sweep_tab_content(page)
                if "?bt=4" in url:
                    self._force_open_bt4_sections(page)
                    self._sweep_tab_content(page, passes=8)
                self._append_snapshot(page, snapshots, seen_hashes)
                if self.config.debug:
                    print(f"[BETANO DEBUG] tab_url={url}")
            except Exception:
                continue

        if not snapshots:
            return self._visit_supported_tabs(page, match_url=match_url)
        return snapshots

    def _build_match_tab_urls(self, match_url: str) -> list[str]:
        base = match_url.split("?", 1)[0].rstrip("/")
        urls = [
            f"{base}/",
            f"{base}/?bt=1",
            f"{base}/?bt=3",
            f"{base}/?bt=4",
            f"{base}/?bt=6",
        ]
        seen: set[str] = set()
        unique_urls: list[str] = []
        for url in urls:
            if url not in seen:
                seen.add(url)
                unique_urls.append(url)
        return unique_urls

    def _visit_supported_tabs(self, page: Any, match_url: str) -> list[str]:
        snapshots: list[str] = []
        seen_hashes: set[str] = set()
        self._sweep_tab_content(page)
        self._append_snapshot(page, snapshots, seen_hashes)
        tab_groups = (
            ("Principais", "principais"),
            ("Mercados de Mapa", "mercados de mapa"),
            ("Mercados Rápidos", "Mercados Rapidos", "mercados rápidos", "mercados rapidos"),
            ("Outros especiais", "outros especiais"),
            ("Todos", "todos"),
        )
        for idx, labels in enumerate(tab_groups):
            if idx == 0:
                continue
            self._ensure_match_url(page, match_url)
            self._scroll_to_top(page)
            opened = False
            for label in labels:
                if self._open_tab(page, label):
                    opened = True
                    break
            if not opened:
                if self.config.debug:
                    print(f"[BETANO DEBUG] tab_open_failed labels={labels}")
                continue
            self._ensure_match_url(page, match_url)
            self._sweep_tab_content(page)
            self._append_snapshot(page, snapshots, seen_hashes)
        return snapshots

    def _ensure_match_url(self, page: Any, match_url: str) -> None:
        try:
            current = page.url
        except Exception:
            return
        if "/odds/" in str(current).lower():
            return
        try:
            page.goto(match_url, wait_until="domcontentloaded", timeout=self.config.timeout_ms)
            page.wait_for_timeout(900)
            if self.config.debug:
                print(f"[BETANO DEBUG] restored_match_url={match_url}")
        except Exception:
            return

    def _scroll_to_top(self, page: Any) -> None:
        try:
            page.evaluate("window.scrollTo(0, 0)")
            page.wait_for_timeout(300)
        except Exception:
            return

    def _sweep_tab_content(self, page: Any, passes: int = 5) -> None:
        for _ in range(max(1, passes)):
            self._expand_target_sections(page)
            self._expand_all_market_sections(page)
            self._click_market_controls(page)
            try:
                page.mouse.wheel(0, 1100)
                page.wait_for_timeout(350)
            except Exception:
                return

    def _force_open_bt4_sections(self, page: Any) -> None:
        targets = (
            "Número de mapas Par/ímpar",
            "Prorrogação (Mapa 1)",
            "Prorrogação (Mapa 2)",
            "Prorrogação (Mapa 3)",
        )
        for label in targets:
            self._open_section_with_scroll(page, label, max_steps=18)
        try:
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(450)
            self._expand_target_sections(page)
            self._expand_all_market_sections(page)
        except Exception:
            return

    def _open_section_with_scroll(self, page: Any, label: str, max_steps: int = 14) -> bool:
        for _ in range(max_steps):
            try:
                opened = page.evaluate(
                    """(label) => {
                        const norm = (s) => (s || '')
                          .toLowerCase()
                          .normalize('NFD')
                          .replace(/[\\u0300-\\u036f]/g, '')
                          .replace(/\\s+/g, ' ')
                          .trim();
                        const target = norm(label);
                        const nodes = Array.from(document.querySelectorAll('button, [role="button"], div, span, a'));
                        for (const el of nodes) {
                            const text = norm((el.textContent || '') + ' ' + (el.getAttribute('aria-label') || '') + ' ' + (el.getAttribute('title') || ''));
                            if (!text || text.length < 4) continue;
                            if (!(text.includes(target) || target.includes(text))) continue;
                            const rect = el.getBoundingClientRect();
                            if (rect.width <= 0 || rect.height <= 0) continue;
                            const expanded = (el.getAttribute('aria-expanded') || '').toLowerCase();
                            const dataState = (el.getAttribute('data-state') || '').toLowerCase();
                            const cls = norm(String(el.className || ''));
                            if (expanded === 'true' || dataState === 'open' || cls.includes('expanded')) return true;
                            try { el.click(); return true; } catch (_) {}
                        }
                        return false;
                    }""",
                    label,
                )
                if opened:
                    page.wait_for_timeout(280)
                    return True
            except Exception:
                pass
            try:
                page.mouse.wheel(0, 1200)
                page.wait_for_timeout(260)
            except Exception:
                break
        if self.config.debug:
            print(f"[BETANO DEBUG] section_open_failed label={label}")
        return False

    def _click_market_controls(self, page: Any) -> None:
        try:
            page.evaluate(
                """() => {
                    const labels = [
                        'mostrar mais',
                        'ver mais',
                        'expandir',
                        'mais mercados',
                        'todos os mercados'
                    ];
                    const norm = (s) => (s || '')
                        .toLowerCase()
                        .normalize('NFD')
                        .replace(/[\\u0300-\\u036f]/g, '')
                        .replace(/\\s+/g, ' ')
                        .trim();
                    const wanted = labels.map(norm);
                    const buttons = Array.from(document.querySelectorAll('button, [role="button"]'));
                    for (const el of buttons) {
                        if (el.dataset && el.dataset.codexMoreClicked === '1') continue;
                        const txt = norm((el.textContent || '') + ' ' + (el.getAttribute('aria-label') || ''));
                        if (!txt) continue;
                        if (!wanted.some((w) => txt.includes(w))) continue;
                        try {
                            el.click();
                            if (el.dataset) el.dataset.codexMoreClicked = '1';
                        } catch (_) {}
                    }
                }"""
            )
            page.wait_for_timeout(200)
        except Exception:
            return

    def _expand_target_sections(self, page: Any) -> None:
        try:
            page.evaluate(
                """() => {
                    const targets = [
                        'total de mapas',
                        'resultado correto',
                        'handicap do jogo',
                        'prorrogacao',
                        'prorrogação',
                        'vencedor do round de pistola',
                        'pontuacao correta dos rounds de pistola',
                        'pontuação correta dos rounds de pistola',
                        'numero de mapas par impar',
                        'número de mapas par ímpar',
                    ];
                    const norm = (s) => (s || '')
                      .toLowerCase()
                      .normalize('NFD')
                      .replace(/[\\u0300-\\u036f]/g, '')
                      .replace(/\\s+/g, ' ')
                      .trim();
                    const els = Array.from(document.querySelectorAll('button[aria-expanded], [role="button"][aria-expanded], button, [role="button"]'));
                    for (const el of els) {
                        if (el.dataset && el.dataset.codexExpandedTarget === '1') continue;
                        const text = norm((el.textContent || '') + ' ' + (el.getAttribute('aria-label') || ''));
                        if (!text) continue;
                        if (!targets.some((t) => text.includes(norm(t)))) continue;
                        const expanded = (el.getAttribute('aria-expanded') || '').toLowerCase();
                        const dataState = (el.getAttribute('data-state') || '').toLowerCase();
                        const cls = norm(String(el.className || ''));
                        const seemsClosed = (
                            expanded !== 'true' ||
                            expanded === 'false' ||
                            dataState === 'closed' ||
                            cls.includes('collapsed') ||
                            cls.includes('closed')
                        );
                        if (!seemsClosed) continue;
                        try {
                            el.click();
                            if (el.dataset) el.dataset.codexExpandedTarget = '1';
                        } catch (_) {}
                    }
                }"""
            )
            page.wait_for_timeout(250)
        except Exception:
            return

    def _append_snapshot(self, page: Any, snapshots: list[str], seen_hashes: set[str]) -> None:
        try:
            html = page.content()
            sig = hashlib.md5(html.encode("utf-8", errors="ignore")).hexdigest()
            if sig not in seen_hashes:
                seen_hashes.add(sig)
                snapshots.append(html)
            try:
                visible_text = page.inner_text("body")
                if visible_text and visible_text.strip():
                    text_payload = "<pre>" + html_lib.escape(visible_text) + "</pre>"
                    text_sig = hashlib.md5(text_payload.encode("utf-8", errors="ignore")).hexdigest()
                    if text_sig not in seen_hashes:
                        seen_hashes.add(text_sig)
                        snapshots.append(text_payload)
            except Exception:
                pass
            if self.config.debug:
                active = self._active_tab_label(page) or "unknown"
                print(f"[BETANO DEBUG] tab_active={active} snapshots={len(snapshots)} html_len={len(html)}")
        except Exception:
            return

    def _open_tab(self, page: Any, label: str) -> bool:
        try:
            locator = page.get_by_role("tab", name=re.compile(re.escape(label), re.IGNORECASE))
            if locator.count() > 0:
                locator.first.click(timeout=1000)
                page.wait_for_timeout(450)
                return True
        except Exception:
            pass
        try:
            locator = page.get_by_role("button", name=re.compile(re.escape(label), re.IGNORECASE))
            if locator.count() > 0:
                locator.first.click(timeout=1000)
                page.wait_for_timeout(450)
                return True
        except Exception:
            pass
        try:
            locator = page.get_by_role("link", name=re.compile(re.escape(label), re.IGNORECASE))
            if locator.count() > 0:
                locator.first.click(timeout=1000)
                page.wait_for_timeout(450)
                return True
        except Exception:
            pass
        try:
            expected_tokens = [t for t in self._normalize_text(label).split() if len(t) >= 4]
            clicked = page.evaluate(
                """({label, expectedTokens}) => {
                    const norm = (s) => (s || '')
                      .toLowerCase()
                      .normalize('NFD')
                      .replace(/[\\u0300-\\u036f]/g, '')
                      .replace(/\\s+/g, ' ')
                      .trim();
                    const target = norm(label);
                    const tabNames = [
                        'principais',
                        'mercados de mapa',
                        'mercados de rounds',
                        'mercados rapidos',
                        'outros especiais',
                        'combos',
                        'todos'
                    ].map(norm);
                    const containers = Array.from(document.querySelectorAll('div, section, nav, header'))
                      .map((el) => {
                        const t = norm(el.textContent || '');
                        if (!t || t.length < 20 || t.length > 2000) return null;
                        const score = tabNames.reduce((acc, name) => acc + (t.includes(name) ? 1 : 0), 0);
                        if (score < 4) return null;
                        return {el, score, len: t.length};
                      })
                      .filter(Boolean)
                      .sort((a, b) => b.score - a.score || a.len - b.len);
                    const scope = containers.length ? containers[0].el : document;
                    const nodes = Array.from(scope.querySelectorAll('[role="tab"], button, [role="button"], a, div, span'));
                    for (const el of nodes) {
                      const text = norm(el.textContent || el.getAttribute('aria-label') || '');
                      if (!text) continue;
                      const tokenHit = expectedTokens.length > 0 && expectedTokens.every((tok) => text.includes(tok));
                      if (!(text === target || text.includes(target) || target.includes(text) || tokenHit)) continue;
                      const rect = el.getBoundingClientRect();
                      if (rect.width <= 0 || rect.height <= 0) continue;
                      if (el.closest('[aria-hidden="true"]')) continue;
                      if (window.getComputedStyle(el).display === 'none') continue;
                      if (window.getComputedStyle(el).visibility === 'hidden') continue;
                      if (window.getComputedStyle(el).pointerEvents === 'none') continue;
                      if (el.tagName.toLowerCase() === 'a') {
                        const href = (el.getAttribute('href') || '').trim().toLowerCase();
                        if (href && !href.startsWith('#') && !href.startsWith('javascript:')) continue;
                      }
                      {
                        try { el.click(); return true; } catch (_) {}
                      }
                    }
                    return false;
                }""",
                {"label": label, "expectedTokens": expected_tokens},
            )
            if not clicked:
                return False
            page.wait_for_timeout(450)
            return True
        except Exception:
            return False

    def _active_tab_label(self, page: Any) -> str | None:
        try:
            raw = page.evaluate(
                """() => {
                    const norm = (s) => (s || '').replace(/\\s+/g, ' ').trim();
                    const pick = (list) => {
                        for (const el of list) {
                            const t = norm(el.textContent || el.getAttribute('aria-label') || '');
                            if (t) return t;
                        }
                        return null;
                    };
                    let found = pick(document.querySelectorAll('[role="tab"][aria-selected="true"]'));
                    if (found) return found;
                    found = pick(document.querySelectorAll('[role="tab"].active, [role="tab"][class*="active"]'));
                    if (found) return found;
                    found = pick(document.querySelectorAll('button[aria-selected="true"], a[aria-current="page"]'));
                    if (found) return found;
                    return null;
                }"""
            )
            if raw:
                return str(raw)
        except Exception:
            return None
        return None

    def _expand_all_market_sections(self, page: Any) -> None:
        try:
            page.evaluate(
                """() => {
                    const candidates = Array.from(
                        document.querySelectorAll('button[aria-expanded=\"false\"], [role=\"button\"][aria-expanded=\"false\"]')
                    );
                    for (const el of candidates) {
                        try { el.click(); } catch (_) {}
                    }
                }"""
            )
            page.evaluate(
                """() => {
                    const keywords = [
                        'vencedor',
                        'resultado',
                        'handicap',
                        'total de mapas',
                        'prorrogacao',
                        'prorrogação',
                        'pistola',
                        'pontuacao correta dos rounds de pistola',
                        'pontuação correta dos rounds de pistola'
                    ];
                    const norm = (s) => (s || '')
                        .toLowerCase()
                        .normalize('NFD')
                        .replace(/[\\u0300-\\u036f]/g, '')
                        .replace(/\\s+/g, ' ')
                        .trim();
                    const looksLikeOdd = (t) => /\\b\\d{1,3}[\\.,]\\d{1,3}\\b/.test(t);
                    const elems = Array.from(document.querySelectorAll('button, [role=\"button\"]'));
                    for (const el of elems) {
                        const text = norm((el.textContent || '') + ' ' + (el.getAttribute('aria-label') || '') + ' ' + (el.getAttribute('title') || ''));
                        if (!text) continue;
                        if (!keywords.some((k) => text.includes(k))) continue;
                        if (looksLikeOdd(text)) continue;

                        const expanded = (el.getAttribute('aria-expanded') || '').toLowerCase();
                        const dataState = (el.getAttribute('data-state') || '').toLowerCase();
                        const collapsed = (el.getAttribute('data-collapsed') || '').toLowerCase();
                        const className = norm(String(el.className || ''));
                        const shouldClick = (
                            expanded === 'false' ||
                            dataState === 'closed' ||
                            collapsed === 'true' ||
                            className.includes('collapsed') ||
                            className.includes('closed')
                        );
                        if (!shouldClick) continue;
                        try { el.click(); } catch (_) {}
                    }
                }"""
            )
            page.wait_for_timeout(250)
        except Exception:
            return

    def _find_match_href_on_page(self, page: Any, aliases_a: set[str], aliases_b: set[str]) -> str | None:
        try:
            links: list[dict[str, str]] = page.eval_on_selector_all(
                "a[href*='/odds/']",
                """els => els.map(e => ({
                    href: e.href || '',
                    text: (e.innerText || e.textContent || '').trim()
                })).filter(x => x.href)""",
            )
        except Exception:
            return None

        for link in links:
            href = str(link.get("href") or "")
            text = str(link.get("text") or "")
            merged = self._normalize_text(f"{href} {text}")
            if self._contains_team(merged, aliases_a) and self._contains_team(merged, aliases_b):
                return href
        return None

    def _advance_master_carousel(self, page: Any) -> bool:
        selectors = (
            "button[aria-label*='próximo' i]",
            "button[aria-label*='proximo' i]",
            "button[aria-label*='next' i]",
            "button[title*='próximo' i]",
            "button[title*='proximo' i]",
            "button[title*='next' i]",
            "button[class*='next']",
            "[data-qa*='next']",
            "[data-testid*='next']",
        )
        for selector in selectors:
            try:
                locator = page.locator(selector)
                if locator.count() > 0:
                    locator.first.click(timeout=900)
                    return True
            except Exception:
                continue

        try:
            clicked = page.evaluate(
                """() => {
                    const elems = Array.from(document.querySelectorAll('button, [role=\"button\"], a'));
                    const norm = (s) => (s || '').toLowerCase().normalize('NFD').replace(/[\\u0300-\\u036f]/g, '').replace(/\\s+/g, ' ').trim();
                    for (const el of elems) {
                        const t = norm((el.textContent || '') + ' ' + (el.getAttribute('aria-label') || '') + ' ' + (el.getAttribute('title') || ''));
                        if (!t) continue;
                        if (t.includes('proximo') || t.includes('próximo') || t.includes('next') || t.includes('seguinte') || t === '>' || t === '>>' || t.includes('›')) {
                            try { el.click(); return true; } catch (_) {}
                        }
                    }
                    return false;
                }"""
            )
            return bool(clicked)
        except Exception:
            return False

    def _extract_entries_from_payloads(
        self,
        payloads: list[tuple[str, Any]],
        aliases_a: set[str],
        aliases_b: set[str],
        team1: str,
        team2: str,
        known_match_page: bool = False,
    ) -> tuple[list[dict[str, Any]], bool]:
        entries: list[dict[str, Any]] = []
        matched_event = bool(known_match_page)

        for url, payload in payloads:
            event_nodes = self._find_event_nodes(payload, aliases_a, aliases_b)
            candidate_nodes = list(event_nodes)

            if not candidate_nodes and known_match_page and isinstance(payload, dict):
                payload_url = self._normalize_text(url)
                if any(key in payload_url for key in ("odds", "market", "event", "fixture", "esports")):
                    candidate_nodes = [payload]

            if candidate_nodes:
                matched_event = True
            for node in candidate_nodes:
                parsed = self._parse_markets_from_node(node, team1=team1, team2=team2)
                if parsed:
                    if self.config.debug:
                        print(f"[BETANO DEBUG] payload match from {url} -> {len(parsed)} entries")
                    entries.extend(parsed)

            if known_match_page:
                payload_url = self._normalize_text(url)
                if any(key in payload_url for key in ("odds", "market", "event", "fixture", "esports")):
                    parsed_any = self._parse_markets_from_payload(payload, team1=team1, team2=team2)
                    if parsed_any:
                        matched_event = True
                        if self.config.debug:
                            print(f"[BETANO DEBUG] known-match payload parse from {url} -> {len(parsed_any)} entries")
                        entries.extend(parsed_any)

        if entries:
            entries = self._dedup_entries(entries)
        return entries, matched_event

    def _parse_markets_from_payload(self, payload: Any, team1: str, team2: str) -> list[dict[str, Any]]:
        market_nodes = self._collect_market_nodes(payload)
        parsed: list[dict[str, Any]] = []
        for node in market_nodes:
            parsed.extend(self._parse_markets_from_node(node, team1=team1, team2=team2))
        return self._dedup_entries(parsed)

    def _find_event_nodes(self, payload: Any, aliases_a: set[str], aliases_b: set[str]) -> list[dict[str, Any]]:
        found: list[dict[str, Any]] = []

        def walk(node: Any, depth: int) -> None:
            if depth > 12:
                return
            if isinstance(node, dict):
                if self._node_contains_both_teams(node, aliases_a, aliases_b):
                    found.append(node)
                    return
                for value in node.values():
                    walk(value, depth + 1)
                return
            if isinstance(node, list):
                for item in node:
                    walk(item, depth + 1)

        walk(payload, 0)
        return found

    def _node_contains_both_teams(self, node: dict[str, Any], aliases_a: set[str], aliases_b: set[str]) -> bool:
        text = self._normalize_text(self._flatten_strings(node, limit=300))
        return self._contains_team(text, aliases_a) and self._contains_team(text, aliases_b)

    def _flatten_strings(self, data: Any, limit: int = 500) -> str:
        out: list[str] = []

        def walk(node: Any) -> None:
            if len(out) >= limit:
                return
            if isinstance(node, dict):
                for value in node.values():
                    walk(value)
                return
            if isinstance(node, list):
                for item in node:
                    walk(item)
                return
            if isinstance(node, (str, int, float)):
                out.append(str(node))

        walk(data)
        return " ".join(out)

    def _parse_markets_from_node(self, node: dict[str, Any], team1: str, team2: str) -> list[dict[str, Any]]:
        market_nodes = self._collect_market_nodes(node)
        parsed: list[dict[str, Any]] = []

        for market in market_nodes:
            market_name = self._extract_market_name(market)
            market_text = self._normalize_text(market_name)
            if not self._is_supported_market_text(market_text):
                continue
            map_number = self._extract_map_number(market_text)
            base_market = self._map_market_type(market_text, map_number)
            if not base_market:
                continue

            for selection, raw_odds, line in self._extract_outcomes(market):
                odds_value = self._to_decimal(raw_odds)
                if odds_value <= 1.0:
                    continue

                normalized_selection = self._normalize_selection(
                    selection,
                    line=line,
                    team1=team1,
                    team2=team2,
                )
                normalized_selection = self._apply_market_selection_context(
                    base_market,
                    market_name,
                    normalized_selection,
                    team1=team1,
                    team2=team2,
                )
                if not normalized_selection:
                    continue

                market_type = self._finalize_market_type(base_market, normalized_selection, line)
                if not market_type:
                    continue

                parsed.append(
                    {
                        "bookmaker": "betano",
                        "market_type": market_type,
                        "selection": normalized_selection,
                        "odds_value": odds_value,
                        "map_number": map_number,
                    }
                )

        return parsed

    def _apply_market_selection_context(
        self,
        market_type: str,
        market_name: str,
        selection: str,
        team1: str,
        team2: str,
    ) -> str:
        value = str(selection or "").strip()
        if not value:
            return ""

        if market_type != "team_win_min_maps":
            return value

        normalized_market = self._normalize_text(market_name)
        team1_aliases = self._team_aliases(team1, None)
        team2_aliases = self._team_aliases(team2, None)

        target_team: str | None = None
        if self._contains_team(normalized_market, team1_aliases) and not self._contains_team(normalized_market, team2_aliases):
            target_team = team1
        elif self._contains_team(normalized_market, team2_aliases) and not self._contains_team(normalized_market, team1_aliases):
            target_team = team2

        if not target_team:
            return value

        normalized_value = self._normalize_text(value)
        if normalized_value in {"sim", "yes"}:
            return f"{target_team} Yes"
        if normalized_value in {"nao", "não", "no"}:
            return f"{target_team} No"
        return f"{target_team} {value}"

    def _is_supported_market_text(self, market_text: str) -> bool:
        text = market_text
        if not text:
            return False
        blocked = (
            "margem de vitoria",
            "margem de vitória",
            "combos",
        )
        if any(b in text for b in blocked):
            return False
        if "vencedor do round (" in text and "pistola" not in text:
            return False
        if "vencedor do round " in text and "pistola" not in text:
            return False
        supported = (
            "vencedor",
            "winner",
            "resultado correto",
            "resultado (mapa",
            "handicap",
            "total de mapas",
            "prorrogacao",
            "prorrogação",
            "vencedor do round de pistola",
            "pontuacao correta dos rounds de pistola",
            "pontuação correta dos rounds de pistola",
            "numero de mapas par impar",
            "número de mapas par ímpar",
            "para ganhar pelo menos um mapa",
            "map winner",
            "correct score",
            "total maps",
            "overtime",
            "pistol",
        )
        return any(s in text for s in supported)

    def _collect_market_nodes(self, data: Any) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []

        def is_market_dict(node: dict[str, Any]) -> bool:
            name_keys = (
                "name",
                "title",
                "market",
                "marketName",
                "market_name",
                "groupName",
                "label",
                "description",
                "marketTypeName",
            )
            outcome_keys = (
                "outcomes",
                "selections",
                "selection",
                "options",
                "bets",
                "entries",
                "odds",
                "prices",
            )
            has_name = any(k in node for k in name_keys)
            has_outcomes = any(k in node for k in outcome_keys)
            return has_name and has_outcomes

        def walk(node: Any, depth: int) -> None:
            if depth > 12:
                return
            if isinstance(node, dict):
                if is_market_dict(node):
                    out.append(node)
                for value in node.values():
                    walk(value, depth + 1)
                return
            if isinstance(node, list):
                for item in node:
                    walk(item, depth + 1)

        walk(data, 0)
        return out

    def _extract_market_name(self, market: dict[str, Any]) -> str:
        for key in (
            "name",
            "title",
            "market",
            "marketName",
            "market_name",
            "groupName",
            "label",
            "description",
            "marketTypeName",
        ):
            value = market.get(key)
            if value:
                return str(value)
        return ""

    def _extract_outcomes(self, market: dict[str, Any]) -> list[tuple[str, Any, float | None]]:
        outcomes: list[tuple[str, Any, float | None]] = []

        for key in ("outcomes", "selections", "options", "bets", "entries", "prices"):
            value = market.get(key)
            if not isinstance(value, list):
                continue
            for item in value:
                if isinstance(item, dict):
                    line = self._extract_line(item)
                    name = self._extract_name(item)
                    odds = self._extract_price(item)
                    if name and odds is not None:
                        outcomes.append((name, odds, line))
                elif isinstance(item, (int, float, str)):
                    price = self._to_decimal(item)
                    if price > 1.0:
                        outcomes.append(("Unknown", item, None))

        for key in ("selections", "selection", "prices", "odds"):
            value = market.get(key)
            if not isinstance(value, dict):
                continue
            line = self._extract_line(value)
            kv_outcomes = self._extract_named_prices_from_dict(value)
            for selection, odds in kv_outcomes:
                outcomes.append((selection, odds, line))

        odds_field = market.get("odds")
        if isinstance(odds_field, list):
            for item in odds_field:
                if isinstance(item, dict):
                    line = self._extract_line(item)
                    kv_outcomes = self._extract_named_prices_from_dict(item)
                    for selection, odds in kv_outcomes:
                        outcomes.append((selection, odds, line))

        direct_kv = self._extract_named_prices_from_dict(market)
        if direct_kv:
            line = self._extract_line(market)
            for selection, odds in direct_kv:
                outcomes.append((selection, odds, line))

        return outcomes

    def _extract_named_prices_from_dict(self, data: dict[str, Any]) -> list[tuple[str, Any]]:
        allowed = {
            "home",
            "away",
            "team1",
            "team2",
            "1",
            "2",
            "over",
            "under",
            "yes",
            "no",
            "draw",
            "x",
        }
        out: list[tuple[str, Any]] = []
        for key, value in data.items():
            k = self._normalize_text(str(key))
            if k not in allowed:
                continue
            if self._to_decimal(value) > 1.0:
                out.append((str(key), value))
        return out

    def _extract_name(self, data: dict[str, Any]) -> str:
        for key in ("name", "label", "title", "selection", "participant", "runner", "outcome"):
            value = data.get(key)
            if value is not None and str(value).strip():
                return str(value).strip()
        return ""

    def _extract_line(self, data: dict[str, Any]) -> float | None:
        for key in ("line", "handicap", "hdp", "points", "point"):
            if key in data:
                val = self._to_float(data.get(key))
                if val is not None:
                    return val
        return None

    def _extract_price(self, data: dict[str, Any]) -> Any:
        for key in ("odds", "price", "value", "decimal", "decimalOdds", "odd"):
            if key in data:
                return data.get(key)
        return None

    @staticmethod
    def _remove_last_decimal_token(text: str) -> str:
        matches = list(re.finditer(r"\b\d{1,3}(?:[.,]\d{1,3})\b", text or ""))
        if not matches:
            return str(text or "").strip()
        match = matches[-1]
        return f"{text[:match.start()]} {text[match.end():]}".strip()

    @staticmethod
    def _extract_selection_price_pairs(text: str) -> list[tuple[str, str]]:
        matches = list(re.finditer(r"\b\d{1,3}(?:[.,]\d{1,3})\b", text or ""))
        if not matches:
            return []
        pairs: list[tuple[str, str]] = []
        cursor = 0
        for match in matches:
            sel = (text[cursor:match.start()] or "").strip(" -–|:;\t\r\n")
            odd = match.group(0)
            if sel:
                pairs.append((sel, odd))
            cursor = match.end()
        return pairs

    def _normalize_selection(self, selection: str, line: float | None, team1: str, team2: str) -> str:
        norm = self._normalize_text(selection)
        if not norm:
            return ""

        if norm in {"home", "team1", "1", "h"}:
            base = team1
        elif norm in {"away", "team2", "2", "a"}:
            base = team2
        elif norm in {"draw", "x"}:
            base = "Draw"
        elif norm in {"yes", "no", "over", "under"}:
            base = norm.title()
        else:
            base = selection.strip()

        if line is not None and norm in {"over", "under"}:
            return f"{base} {self._format_line(line)}"

        return base

    def _finalize_market_type(self, market_type: str, selection: str, line: float | None) -> str | None:
        if market_type != "over_maps":
            return market_type
        if line is None:
            return market_type

        sel = self._normalize_text(selection)
        if abs(line - 2.5) < 0.01:
            if "under" in sel:
                return "under_maps_2_5"
            return "over_maps_2_5"
        if abs(line - 4.5) < 0.01:
            if "under" in sel:
                return "under_maps_4_5"
            return "over_maps_4_5"
        return market_type

    def _map_market_type(self, market_text: str, map_number: int | None) -> str | None:
        text = market_text

        if "correct score" in text or "resultado correto" in text or "placar correto" in text:
            return "correct_score"

        if "resultado" in text and map_number is not None:
            return f"map{map_number}_winner"

        if ("vencedor do round de pistola" in text or "pistol round winner" in text) and map_number is not None:
            if "rodada 13" in text or "round 13" in text:
                return f"map{map_number}_pistol"
            return f"map{map_number}_pistol_1h"

        if ("pontuacao correta dos rounds de pistola" in text or "pontuação correta dos rounds de pistola" in text) and map_number is not None:
            return f"map{map_number}_pistol_correct_score"

        if "numero de mapas par impar" in text or "número de mapas par ímpar" in text:
            return "total_maps_parity"

        if "para ganhar pelo menos um mapa" in text:
            return "team_win_min_maps"

        if ("margem de vitoria" in text or "margem de vitória" in text) and map_number is not None:
            return f"map{map_number}_margin_of_victory"

        if map_number is not None:
            if self._looks_like_overtime_market_text(text):
                return f"map{map_number}_ot"
            if any(k in text for k in ("handicap", "spread")):
                return f"map{map_number}_handicap"
            if any(k in text for k in ("pistol", "pistola")):
                return f"map{map_number}_pistol_1h"
            if any(k in text for k in ("winner", "vencedor", "moneyline", "ml")):
                return f"map{map_number}_winner"

        if "match" in text and any(k in text for k in ("winner", "vencedor", "moneyline")):
            return "match_winner"
        if any(k in text for k in ("vencedor da serie", "serie winner", "match winner")):
            return "match_winner"
        if (
            "total" in text
            and any(k in text for k in ("map", "mapa"))
            and "round" not in text
            and "rodada" not in text
        ):
            return "over_maps"
        if "handicap" in text and "map" not in text and "mapa" not in text:
            return "handicap_match"

        return None

    def _infer_market_type_from_row_text(self, row_text: str) -> str | None:
        norm = self._normalize_text(row_text)
        if not norm:
            return None
        if ("mais de" in norm or "menos de" in norm or "over" in norm or "under" in norm) and (
            "2 5" in norm or "4 5" in norm
        ):
            return "over_maps"
        if re.search(r"\b\d+\s*-\s*\d+\b", row_text):
            return "correct_score"
        return None

    def _extract_entries_from_dom(
        self,
        html: str,
        team1: str,
        team2: str,
        aliases_a: set[str],
        aliases_b: set[str],
        skip_team_validation: bool = False,
    ) -> list[dict[str, Any]]:
        soup = BeautifulSoup(html, "html.parser")
        text = self._normalize_text(soup.get_text(" ", strip=True))
        if not skip_team_validation and not (self._contains_team(text, aliases_a) and self._contains_team(text, aliases_b)):
            return []

        block_entries: list[dict[str, Any]] = []
        row_entries: list[dict[str, Any]] = []
        odds_pattern = re.compile(r"\b\d{1,3}(?:[\.,]\d{1,3})\b")
        market_blocks = soup.find_all(["section", "article", "div"], class_=re.compile(r"market|event|group|accordion|tab", re.IGNORECASE))

        for block in soup.find_all(["section", "article", "div"]):
            block_text = block.get_text(" ", strip=True)
            if len(block_text) < 12 or len(block_text) > 3000:
                continue
            if not odds_pattern.search(block_text):
                continue
            normalized_block = self._normalize_text(block_text[:800])
            if not self._is_supported_market_text(normalized_block):
                continue
            market_blocks.append(block)

        for block in market_blocks:
            title_el = block.find(["h2", "h3", "h4", "span", "div"], class_=re.compile(r"title|label|header", re.IGNORECASE))
            if title_el is None:
                title_el = block.find(["h1", "h2", "h3", "h4", "header", "strong", "button"])
            title = title_el.get_text(" ", strip=True) if title_el else ""
            if not title:
                lines = [ln.strip() for ln in block.get_text("\n", strip=True).splitlines() if ln.strip()]
                for line in lines:
                    if not odds_pattern.search(line):
                        title = line
                        break
            market_text = self._normalize_text(title)
            if not self._is_supported_market_text(market_text):
                continue
            map_number = self._extract_map_number(market_text)
            market_type = self._map_market_type(market_text, map_number)
            if not market_type:
                continue

            options = block.find_all(["button", "div", "span"], class_=re.compile(r"selection|outcome|option", re.IGNORECASE))
            if not options:
                options = block.find_all(["button", "a", "div", "span", "li"])
            for option in options:
                option_text = option.get_text(" ", strip=True)
                if not option_text or len(option_text) > 200:
                    continue
                odd_values = odds_pattern.findall(option_text)
                if not odd_values:
                    continue
                odd = self._to_decimal(odd_values[-1].replace(",", "."))
                if odd <= 1.0:
                    continue

                selection = self._remove_last_decimal_token(option_text)
                selection = self._normalize_selection(selection, None, team1=team1, team2=team2)
                selection = self._apply_market_selection_context(
                    market_type,
                    title or market_text,
                    selection,
                    team1=team1,
                    team2=team2,
                )
                if not selection:
                    continue

                finalized_market_type = self._finalize_market_type(market_type, selection, self._to_float(selection))
                block_entries.append(
                    {
                        "bookmaker": "betano",
                        "market_type": finalized_market_type or market_type,
                        "selection": selection,
                        "odds_value": odd,
                        "map_number": map_number,
                    }
                )

        for row in soup.find_all(["button", "a", "div", "span", "li"]):
            row_text = row.get_text(" ", strip=True)
            if not row_text or len(row_text) > 220:
                continue
            pairs = self._extract_selection_price_pairs(row_text)
            if not pairs:
                continue

            context_bits: list[str] = [row_text]
            best_heading = ""
            parent = row.parent
            hops = 0
            while parent is not None and hops < 5:
                heading = parent.find(["h1", "h2", "h3", "h4", "strong", "header"])
                if heading:
                    heading_text = heading.get_text(" ", strip=True)[:180]
                    if heading_text and not best_heading:
                        best_heading = heading_text
                    context_bits.append(heading_text)
                sibling = parent.find_previous_sibling(["h1", "h2", "h3", "h4", "strong", "button", "div", "span"])
                if sibling:
                    sibling_text = sibling.get_text(" ", strip=True)[:180]
                    if sibling_text and not best_heading and not odds_pattern.search(sibling_text):
                        best_heading = sibling_text
                    context_bits.append(sibling_text)
                direct_parts = [t.strip() for t in parent.find_all(string=True, recursive=False) if str(t).strip()]
                if direct_parts:
                    context_bits.append(" ".join(direct_parts)[:160])
                parent = parent.parent
                hops += 1
            if best_heading:
                context_text = self._normalize_text(f"{best_heading} {row_text}")
            else:
                context_text = self._normalize_text(" ".join(context_bits))

            previous_heading = ""
            try:
                prev = row.find_previous(
                    lambda tag: (
                        getattr(tag, "name", "") in {"h1", "h2", "h3", "h4", "h5", "header", "strong", "button", "div", "span"}
                        and bool(tag.get_text(" ", strip=True))
                        and len(tag.get_text(" ", strip=True)) <= 120
                        and not odds_pattern.search(tag.get_text(" ", strip=True))
                        and self._is_supported_market_text(self._normalize_text(tag.get_text(" ", strip=True)))
                    )
                )
                if prev:
                    previous_heading = prev.get_text(" ", strip=True)
            except Exception:
                previous_heading = ""

            if previous_heading:
                context_text = self._normalize_text(f"{previous_heading} {context_text}")

            if not self._is_supported_market_text(context_text):
                direct_market = self._infer_market_type_from_row_text(row_text)
                if not direct_market:
                    continue
                context_text = f"{context_text} {direct_market}"
            map_number = self._extract_map_number(context_text)
            market_type = self._map_market_type(context_text, map_number)
            if not market_type:
                direct_market = self._infer_market_type_from_row_text(row_text)
                if direct_market:
                    market_type = direct_market
                    map_number = None
                else:
                    if self._contains_team(context_text, aliases_a) and self._contains_team(context_text, aliases_b):
                        market_type = "match_winner"
                    else:
                        continue
            if market_type == "correct_score" and map_number is not None:
                market_type = "correct_score"
                map_number = None

            if not market_type:
                if self._contains_team(context_text, aliases_a) and self._contains_team(context_text, aliases_b):
                    market_type = "match_winner"
                else:
                    continue

            for raw_selection, raw_odd in pairs:
                odd = self._to_decimal(raw_odd.replace(",", "."))
                if odd <= 1.0:
                    continue
                selection = self._normalize_selection(raw_selection, None, team1=team1, team2=team2)
                selection = self._apply_market_selection_context(
                    market_type,
                    context_text,
                    selection,
                    team1=team1,
                    team2=team2,
                )
                if not selection:
                    continue

                finalized_market_type = self._finalize_market_type(market_type, selection, self._to_float(selection))
                row_entries.append(
                    {
                        "bookmaker": "betano",
                        "market_type": finalized_market_type or market_type,
                        "selection": selection,
                        "odds_value": odd,
                        "map_number": map_number,
                    }
                )

        page_text = soup.get_text(" ", strip=True)
        ot_entries = self._extract_ot_entries_from_page_text(page_text)
        parity_entries = self._extract_total_maps_parity_from_page_text(page_text)
        # Prefer row-level extraction; block-level entries are fallback for sections without clean odds buttons.
        return self._dedup_entries([*row_entries, *block_entries, *ot_entries, *parity_entries])

    def _extract_ot_entries_from_page_text(self, page_text: str) -> list[dict[str, Any]]:
        if not page_text:
            return []
        text = re.sub(r"\s+", " ", page_text).strip()
        entries: list[dict[str, Any]] = []
        heading_pattern = re.compile(
            r"(?:Prorroga(?:ç|c)[aã]o|Overtime)\s*\(?(?:Mapa|Map)\s*(\d)\)?",
            re.IGNORECASE,
        )
        label_before_price = re.compile(
            r"\b(Sim|Yes|N(?:ã|a)o|No)\b\s*(\d{1,3}[.,]\d{1,3})",
            re.IGNORECASE,
        )
        price_before_label = re.compile(
            r"(\d{1,3}[.,]\d{1,3})\s*\b(Sim|Yes|N(?:ã|a)o|No)\b",
            re.IGNORECASE,
        )

        matches = list(heading_pattern.finditer(text))
        for idx, match in enumerate(matches):
            try:
                map_number = int(match.group(1))
            except Exception:
                continue

            start = match.end()
            if idx + 1 < len(matches):
                end = matches[idx + 1].start()
            else:
                end = min(len(text), start + 1400)
            window = text[start:end]
            if not window:
                continue

            found: dict[str, float] = {}
            for label, odd_text in label_before_price.findall(window):
                odd = self._to_decimal(odd_text.replace(",", "."))
                if odd <= 1.0:
                    continue
                key = "Sim" if self._normalize_text(label) in {"sim", "yes"} else "Não"
                found[key] = odd

            if not found:
                for odd_text, label in price_before_label.findall(window):
                    odd = self._to_decimal(odd_text.replace(",", "."))
                    if odd <= 1.0:
                        continue
                    key = "Sim" if self._normalize_text(label) in {"sim", "yes"} else "Não"
                    found[key] = odd

            for selection, odd in found.items():
                entries.append(
                    {
                        "bookmaker": "betano",
                        "market_type": f"map{map_number}_ot",
                        "selection": selection,
                        "odds_value": odd,
                        "map_number": map_number,
                    }
                )
        return entries

    def _extract_total_maps_parity_from_page_text(self, page_text: str) -> list[dict[str, Any]]:
        if not page_text:
            return []
        text = re.sub(r"\s+", " ", page_text).strip()
        entries: list[dict[str, Any]] = []
        heading_pattern = re.compile(
            r"(?:N(?:u|ú)mero de mapas Par/?(?:[ií]mpar)|Total maps odd/even)(.{0,420})",
            re.IGNORECASE,
        )
        odd_match_pattern = re.compile(r"\b(?:[ií]mpar|odd)\b\s*(\d{1,3}[.,]\d{1,3})", re.IGNORECASE)
        even_match_pattern = re.compile(r"\b(?:par|even)\b\s*(\d{1,3}[.,]\d{1,3})", re.IGNORECASE)

        for match in heading_pattern.finditer(text):
            window = match.group(1)
            if not window:
                continue
            odd_match = odd_match_pattern.search(window)
            even_match = even_match_pattern.search(window)
            if odd_match:
                odd = self._to_decimal(odd_match.group(1).replace(",", "."))
                if odd > 1.0:
                    entries.append(
                        {
                            "bookmaker": "betano",
                            "market_type": "total_maps_parity",
                            "selection": "Ímpar",
                            "odds_value": odd,
                            "map_number": None,
                        }
                    )
            if even_match:
                even = self._to_decimal(even_match.group(1).replace(",", "."))
                if even > 1.0:
                    entries.append(
                        {
                            "bookmaker": "betano",
                            "market_type": "total_maps_parity",
                            "selection": "Par",
                            "odds_value": even,
                            "map_number": None,
                        }
                    )
        return entries

    @staticmethod
    def _looks_like_overtime_market_text(text: str) -> bool:
        if "overtime" in text or "prorrogacao" in text or "prorrogação" in text:
            return True
        return bool(re.search(r"\bot\b", text))

    def _looks_like_challenge(self, html: str) -> bool:
        text = self._normalize_text(html)
        strong_markers = (
            "access denied",
            "captcha",
            "verify you are human",
            "detected unusual traffic",
            "bot detection",
            "checking your browser before accessing",
            "attention required",
            "ddos protection",
        )
        if any(marker in text for marker in strong_markers):
            return True
        if "cloudflare" in text and ("checking your browser" in text or "attention required" in text):
            return True
        return False

    def _looks_like_not_found(self, html: str) -> bool:
        text = self._normalize_text(html)
        markers = (
            "home page does not exist",
            "homepage does not exist",
            "pagina nao existe",
            "pagina que procura nao existe",
            "a pagina que procura nao existe",
            "a página que procura não existe",
        )
        return any(marker in text for marker in markers)

    @staticmethod
    def _dedup_entries(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
        dedup: dict[tuple[Any, ...], dict[str, Any]] = {}
        for item in entries:
            key = (
                item.get("bookmaker"),
                item.get("market_type"),
                item.get("selection"),
                item.get("map_number"),
            )
            if key not in dedup:
                dedup[key] = item
        return list(dedup.values())

    @staticmethod
    def _extract_map_number(text: str) -> int | None:
        match = re.search(r"(?:map|mapa|m)\s*[_-]?(\d)", text)
        if not match:
            return None
        try:
            return int(match.group(1))
        except Exception:
            return None

    @staticmethod
    def _format_line(value: float) -> str:
        if abs(value - round(value)) < 0.001:
            return str(int(round(value)))
        return f"{value:.2f}".rstrip("0").rstrip(".")

    @staticmethod
    def _to_float(value: Any) -> float | None:
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return float(value)
        text = str(value).strip().replace(",", ".")
        if not text:
            return None
        match = re.search(r"[-+]?\d+(?:\.\d+)?", text)
        if not match:
            return None
        try:
            return float(match.group(0))
        except Exception:
            return None

    @classmethod
    def _to_decimal(cls, value: Any) -> float:
        parsed = cls._to_float(value)
        if parsed is None:
            return 0.0
        if 1.0 < parsed < 30.0:
            return round(parsed, 4)
        if abs(parsed) >= 100:
            return round(cls._american_to_decimal(parsed), 4)
        return 0.0

    @staticmethod
    def _american_to_decimal(price: float) -> float:
        if price > 0:
            return 1.0 + (price / 100.0)
        return 1.0 + (100.0 / abs(price))

    @staticmethod
    def _normalize_text(text: str) -> str:
        if not text:
            return ""
        normalized = unicodedata.normalize("NFKD", text)
        clean = "".join(ch for ch in normalized if not unicodedata.combining(ch))
        clean = clean.lower()
        clean = re.sub(r"[^a-z0-9]+", " ", clean)
        return re.sub(r"\s+", " ", clean).strip()

    @staticmethod
    def _is_closed_error(exc: Exception) -> bool:
        text = str(exc).lower()
        markers = (
            "has been closed",
            "target page, context or browser has been closed",
            "browser has closed",
            "context closed",
            "page closed",
        )
        return any(marker in text for marker in markers)

    @classmethod
    def _team_aliases(cls, team_name: str | None, team_tag: str | None) -> set[str]:
        aliases: set[str] = set()
        for raw in (team_name, team_tag):
            if not raw:
                continue
            norm = cls._normalize_text(str(raw))
            if not norm:
                continue
            aliases.add(norm)
            aliases.add(norm.replace(" ", ""))
            parts = [p for p in norm.split() if p]
            if parts:
                aliases.add(parts[0])
            if len(parts) > 1:
                aliases.add("".join(p[0] for p in parts))
        return {a for a in aliases if len(a) >= 2}

    @classmethod
    def _contains_team(cls, text: str, aliases: set[str]) -> bool:
        for alias in aliases:
            if len(alias) <= 3:
                if re.search(rf"\b{re.escape(alias)}\b", text):
                    return True
            elif alias in text:
                return True
        return False


def scrape_betano_detailed(
    team1: str,
    team2: str,
    team1_tag: str | None = None,
    team2_tag: str | None = None,
) -> dict[str, Any]:
    scraper = BetanoStealthScraper()
    try:
        entries = scraper.scrape_match_odds(team1, team2, team1_tag=team1_tag, team2_tag=team2_tag)
        return {
            "entries": entries,
            "source": "betano_scraping",
            "error": None,
            "error_code": None,
        }
    except BetanoScraperError as exc:
        return {
            "entries": [],
            "source": "betano_scraping",
            "error": str(exc),
            "error_code": exc.code,
        }


def scrape_betano(team1: str, team2: str) -> list[dict[str, Any]]:
    result = scrape_betano_detailed(team1, team2)
    return list(result.get("entries") or [])
