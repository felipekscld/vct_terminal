"""Odds collection for automatic ingestion (Betano-only scraping)."""

from __future__ import annotations

import os
import re
import unicodedata
from collections import Counter
from typing import Any

from rich.console import Console

from src.collectors.betano_scraper import scrape_betano_detailed
from src.db.connection import get_db

console = Console()

BET365_DISABLED_ERROR = "Integracao automatica da bet365 desativada neste projeto."


def _infer_map_number(market_type: str) -> int | None:
    digits = "".join(c for c in str(market_type) if c.isdigit())
    return int(digits) if digits else None


def insert_odds(match_id: int, odds_list: list[dict[str, Any]]) -> int:
    count = 0
    with get_db() as conn:
        for odd in odds_list:
            try:
                market_type = str(odd.get("market_type", "")).lower().strip()
                selection = str(odd.get("selection", "")).strip()
                bookmaker = str(odd.get("bookmaker", "")).lower().strip()
                odds_value = float(odd.get("odds_value", 0))
                map_number = odd.get("map_number")

                if not market_type or not selection or not bookmaker or odds_value <= 1.0:
                    continue

                if map_number is None:
                    map_number = _infer_map_number(market_type)

                conn.execute(
                    """INSERT INTO odds_snapshots
                       (match_id, map_number, bookmaker, market_type, selection, odds_value)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (match_id, map_number, bookmaker, market_type, selection, odds_value),
                )
                count += 1
            except Exception as exc:
                console.print(f"[red]Failed to insert odd {odd}: {exc}[/red]")
    return count


def _normalize_market_type(market_type: str, map_number: int | None) -> str:
    mt = market_type.lower().strip()

    if mt.startswith("map") and any(ch.isdigit() for ch in mt):
        return mt

    if map_number is not None:
        per_map_aliases = {
            "map_winner": "winner",
            "map_ot": "ot",
            "overtime": "ot",
            "map_pistol": "pistol",
            "map_pistol_1h": "pistol_1h",
            "map_handicap": "handicap",
            "map_total_rounds": "total_rounds",
            "map_pistol_correct_score": "pistol_correct_score",
            "map_total_rounds_parity": "total_rounds_parity",
            "map_margin_of_victory": "margin_of_victory",
        }
        suffix = per_map_aliases.get(mt)
        if suffix:
            return f"map{map_number}_{suffix}"

    return mt


def _normalize_text(value: str) -> str:
    if not value:
        return ""
    normalized = unicodedata.normalize("NFKD", value)
    stripped = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    stripped = stripped.lower().strip()
    stripped = re.sub(r"[^a-z0-9+\-./ ]+", " ", stripped)
    return re.sub(r"\s+", " ", stripped).strip()


def _team_aliases(*values: str | None) -> set[str]:
    out: set[str] = set()
    for raw in values:
        if not raw:
            continue
        text = _normalize_text(str(raw))
        if not text:
            continue
        out.add(text)
        out.add(text.replace(" ", ""))
    return out


def _contains_alias(text: str, aliases: set[str]) -> bool:
    low = _normalize_text(text)
    compact = low.replace(" ", "")
    return any(a in low or a in compact for a in aliases if a)


def _extract_signed_line(text: str) -> str | None:
    import re
    m = re.search(r"([+-]\d+(?:[.,]\d+)?)", text)
    if not m:
        return None
    return m.group(1).replace(",", ".")


def _extract_score(text: str) -> str | None:
    m = re.search(r"\b(\d+)\s*-\s*(\d+)\b", text)
    if not m:
        return None
    return f"{m.group(1)}-{m.group(2)}"


def _extract_total_line(text: str) -> str | None:
    m = re.search(r"(\d+(?:[.,]\d+)?)", text)
    if not m:
        return None
    return m.group(1).replace(",", ".")


def _normalize_yes_no(text: str) -> str | None:
    if any(token in text for token in ("sim", "yes")):
        return "Yes"
    if any(token in text for token in ("nao", "não", "no")):
        return "No"
    return None


def _normalize_parity(text: str) -> str | None:
    if any(token in text for token in ("impar", "ímpar", "odd")):
        return "Odd"
    if any(token in text for token in ("par", "even")):
        return "Even"
    return None


def _normalize_selection_for_market(
    market_type: str,
    selection: str,
    team1: str,
    team2: str,
    team1_tag: str | None,
    team2_tag: str | None,
) -> str | None:
    s = str(selection or "").strip()
    if not s:
        return None
    low = _normalize_text(s)
    team1_aliases = _team_aliases(team1, team1_tag)
    team2_aliases = _team_aliases(team2, team2_tag)
    has_t1 = _contains_alias(low, team1_aliases)
    has_t2 = _contains_alias(low, team2_aliases)

    if (
        market_type in {"match_winner"}
        or market_type.endswith("_winner")
        or market_type.endswith("_pistol_1h")
        or market_type.endswith("_pistol")
    ):
        if has_t1 and has_t2:
            if "empate" in low or "draw" in low:
                return "Draw"
            return None
        if has_t1:
            return team1
        if has_t2:
            return team2
        if "empate" in low or "draw" in low:
            return "Draw"
        return None

    if market_type in {"handicap_match"} or market_type.endswith("_handicap"):
        line = _extract_signed_line(s)
        if not line:
            return None
        if has_t1 and not has_t2:
            return f"{team1} {line}"
        if has_t2 and not has_t1:
            return f"{team2} {line}"
        return None

    if market_type in {"over_maps_2_5", "under_maps_2_5", "over_maps_4_5", "under_maps_4_5"}:
        if market_type == "over_maps_2_5":
            return "Over 2.5"
        if market_type == "under_maps_2_5":
            return "Under 2.5"
        if market_type == "over_maps_4_5":
            return "Over 4.5"
        return "Under 4.5"

    if market_type == "over_maps":
        s2 = low.replace(",", ".")
        line = _extract_total_line(s2)
        if "mais" in s2 or "over" in s2:
            return f"Over {line}" if line else "Over"
        if "menos" in s2 or "under" in s2:
            return f"Under {line}" if line else "Under"
        return None

    if market_type == "correct_score" or market_type.endswith("_pistol_correct_score"):
        return _extract_score(s)

    if market_type.endswith("_ot"):
        return _normalize_yes_no(low)

    if market_type.endswith("_total_rounds"):
        s2 = low.replace(",", ".")
        line = _extract_total_line(s2)
        if "mais" in s2 or "over" in s2:
            return f"Over {line}" if line else "Over"
        if "menos" in s2 or "under" in s2:
            return f"Under {line}" if line else "Under"
        return None

    if market_type.endswith("_total_rounds_parity") or market_type == "total_maps_parity":
        return _normalize_parity(low)

    if market_type == "team_win_min_maps":
        answer = _normalize_yes_no(low)
        if not answer:
            return None
        if has_t1 and not has_t2:
            return f"{team1} {answer}"
        if has_t2 and not has_t1:
            return f"{team2} {answer}"
        return answer

    return s


def _sanitize_entries(
    entries: list[dict[str, Any]],
    bookmaker: str,
    team1: str,
    team2: str,
    team1_tag: str | None,
    team2_tag: str | None,
) -> list[dict[str, Any]]:
    cleaned: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for item in entries:
        try:
            market_type = str(item.get("market_type", "")).lower().strip()
            selection = str(item.get("selection", "")).strip()
            odds_value = float(item.get("odds_value", 0))
            map_number = item.get("map_number")
            map_number = int(map_number) if map_number is not None else None
            if not market_type or not selection or odds_value <= 1.0:
                continue
            market_type = _normalize_market_type(market_type, map_number)
            if market_type == "team_win_min_maps":
                map_number = None
            if market_type == "correct_score":
                map_number = None
            normalized_selection = _normalize_selection_for_market(
                market_type=market_type,
                selection=selection,
                team1=team1,
                team2=team2,
                team1_tag=team1_tag,
                team2_tag=team2_tag,
            )
            if not normalized_selection:
                continue
            key = (market_type, normalized_selection, map_number)
            if key in seen:
                continue
            seen.add(key)
            cleaned.append(
                {
                    "bookmaker": bookmaker,
                    "market_type": market_type,
                    "selection": normalized_selection,
                    "odds_value": odds_value,
                    "map_number": map_number,
                }
            )
        except (TypeError, ValueError):
            continue
    return cleaned


def _force_include_ot_entries(
    raw_entries: list[dict[str, Any]],
    cleaned_entries: list[dict[str, Any]],
    bookmaker: str,
) -> list[dict[str, Any]]:
    out = list(cleaned_entries)
    seen = {
        (
            str(item.get("market_type", "")).lower().strip(),
            str(item.get("selection", "")).strip(),
            item.get("map_number"),
        )
        for item in out
    }

    for item in raw_entries:
        try:
            market_type = str(item.get("market_type", "")).lower().strip()
            if not market_type.endswith("_ot"):
                continue
            odds_value = float(item.get("odds_value", 0))
            if odds_value <= 1.0:
                continue
            selection_raw = str(item.get("selection", "")).strip()
            selection = _normalize_yes_no(_normalize_text(selection_raw))
            if not selection:
                continue
            map_number = item.get("map_number")
            if map_number is None:
                map_number = _infer_map_number(market_type)
            map_number = int(map_number) if map_number is not None else None
            key = (market_type, selection, map_number)
            if key in seen:
                continue
            seen.add(key)
            out.append(
                {
                    "bookmaker": bookmaker,
                    "market_type": market_type,
                    "selection": selection,
                    "odds_value": odds_value,
                    "map_number": map_number,
                }
            )
        except (TypeError, ValueError):
            continue

    return out


def collect_odds_from_sites(match_id: int) -> dict[str, Any]:
    context = get_match_context(match_id)
    if not context:
        return {
            "inserted": 0,
            "bookmakers": {
                "betano": {
                    "scraped": 0,
                    "inserted": 0,
                    "source": "betano_scraping",
                    "error": "Match nao encontrado.",
                    "error_code": "betano_match_not_found",
                },
                "bet365": {
                    "scraped": 0,
                    "inserted": 0,
                    "source": "disabled",
                    "error": BET365_DISABLED_ERROR,
                    "error_code": "bet365_disabled",
                },
            },
            "provider": None,
        }

    team1 = context.get("team1")
    team2 = context.get("team2")
    team1_tag = context.get("team1_tag")
    team2_tag = context.get("team2_tag")

    if not team1 or not team2:
        return {
            "inserted": 0,
            "bookmakers": {
                "betano": {
                    "scraped": 0,
                    "inserted": 0,
                    "source": "betano_scraping",
                    "error": "Times nao encontrados no match.",
                    "error_code": "betano_match_not_found",
                },
                "bet365": {
                    "scraped": 0,
                    "inserted": 0,
                    "source": "disabled",
                    "error": BET365_DISABLED_ERROR,
                    "error_code": "bet365_disabled",
                },
            },
            "provider": None,
        }

    scraped = scrape_betano_detailed(
        team1=team1,
        team2=team2,
        team1_tag=team1_tag,
        team2_tag=team2_tag,
    )
    raw_entries = list(scraped.get("entries") or [])

    entries = _sanitize_entries(
        raw_entries,
        "betano",
        team1=team1,
        team2=team2,
        team1_tag=team1_tag,
        team2_tag=team2_tag,
    )
    entries = _force_include_ot_entries(raw_entries, entries, "betano")
    if os.getenv("BETANO_SCRAPER_DEBUG", "").strip().lower() in {"1", "true", "yes", "on"}:
        raw_counter = Counter(str(x.get("market_type", "")).lower().strip() for x in raw_entries)
        clean_counter = Counter(str(x.get("market_type", "")).lower().strip() for x in entries)
        preview = [
            {
                "market_type": str(x.get("market_type", "")).lower().strip(),
                "selection": str(x.get("selection", "")).strip(),
                "odds_value": x.get("odds_value"),
                "map_number": x.get("map_number"),
            }
            for x in raw_entries[:16]
        ]
        raw_ot_preview = [
            {
                "market_type": str(x.get("market_type", "")).lower().strip(),
                "selection": str(x.get("selection", "")).strip(),
                "odds_value": x.get("odds_value"),
                "map_number": x.get("map_number"),
            }
            for x in raw_entries
            if str(x.get("market_type", "")).lower().strip().endswith("_ot")
        ][:12]
        clean_ot_preview = [
            {
                "market_type": str(x.get("market_type", "")).lower().strip(),
                "selection": str(x.get("selection", "")).strip(),
                "odds_value": x.get("odds_value"),
                "map_number": x.get("map_number"),
            }
            for x in entries
            if str(x.get("market_type", "")).lower().strip().endswith("_ot")
        ][:12]
        console.print(
            "[BETANO DEBUG] "
            f"raw_entries={len(raw_entries)} raw_markets={dict(raw_counter)} "
            f"clean_entries={len(entries)} clean_markets={dict(clean_counter)}"
        )
        console.print(f"[BETANO DEBUG] raw_preview={preview}")
        console.print(f"[BETANO DEBUG] raw_ot_preview={raw_ot_preview}")
        console.print(f"[BETANO DEBUG] clean_ot_preview={clean_ot_preview}")
    inserted = insert_odds(match_id, entries) if entries else 0

    betano_error = scraped.get("error")
    betano_error_code = scraped.get("error_code")

    if entries and inserted <= 0:
        betano_error = "Odds da betano foram coletadas, mas falharam ao gravar no banco."
        betano_error_code = "betano_parse_failed"
    elif not entries and raw_entries and not betano_error:
        betano_error = "Odds da betano foram capturadas, mas descartadas na validacao."
        betano_error_code = "betano_parse_failed"
    elif inserted > 0:
        betano_error = None
        betano_error_code = None

    betano_result = {
        "scraped": len(entries),
        "inserted": inserted,
        "source": str(scraped.get("source") or "betano_scraping"),
        "error": betano_error,
        "error_code": betano_error_code,
    }

    if betano_result["error"]:
        console.print(f"[red]{betano_result['error']}[/red]")
    else:
        console.print(f"[green]✓ betano: {betano_result['inserted']} odds gravadas.[/green]")

    bet365_result = {
        "scraped": 0,
        "inserted": 0,
        "source": "disabled",
        "error": BET365_DISABLED_ERROR,
        "error_code": "bet365_disabled",
    }

    return {
        "inserted": inserted,
        "bookmakers": {
            "betano": betano_result,
            "bet365": bet365_result,
        },
        "provider": None,
        "match": {
            "team1": team1,
            "team2": team2,
            "team1_tag": team1_tag,
            "team2_tag": team2_tag,
            "fixture_id": None,
            "description": context.get("description"),
        },
    }


def get_match_context(match_id: int) -> dict[str, Any] | None:
    with get_db() as conn:
        row = conn.execute(
            """SELECT m.id, t1.name as t1_name, t2.name as t2_name,
                      t1.tag as t1_tag, t2.tag as t2_tag,
                      e.name as event_name, m.stage_name, m.bo_type, m.date, m.time
               FROM matches m
               LEFT JOIN teams t1 ON m.team1_id = t1.id
               LEFT JOIN teams t2 ON m.team2_id = t2.id
               LEFT JOIN events e ON m.event_id = e.id
               WHERE m.id = ?""",
            (match_id,),
        ).fetchone()

        if not row:
            return None

        team1 = row["t1_name"]
        team2 = row["t2_name"]

        parts = []
        if team1 and team2:
            parts.append(f"{team1} vs {team2}")
        if row["event_name"]:
            parts.append(row["event_name"])
        if row["stage_name"]:
            parts.append(row["stage_name"])
        if row["bo_type"]:
            parts.append(row["bo_type"])

        return {
            "team1": team1,
            "team2": team2,
            "team1_tag": row["t1_tag"],
            "team2_tag": row["t2_tag"],
            "date": row["date"],
            "time": row["time"],
            "description": " - ".join(parts) if parts else f"Match {match_id}",
        }


def get_match_description(match_id: int) -> str | None:
    context = get_match_context(match_id)
    if not context:
        return None
    return context.get("description")
