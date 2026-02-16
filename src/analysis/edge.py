"""Edge calculator: compare p_model vs p_impl from bookmaker odds.

All analysis respects the active DataFilter.
"""

from __future__ import annotations

import math
from typing import Optional

from src.config import config, DataFilter
from src.db.connection import get_db
from src.models.data_models import EdgeResult, MarketOdds


def remove_margin(odds_list: list[float], method: str = "power") -> list[float]:
    """Remove bookmaker margin from a set of odds for the same market.

    'power' method (Shin/power): assumes margin is distributed proportionally.
    Returns fair (no-margin) odds.
    """
    if not odds_list or any(o <= 1.0 for o in odds_list):
        return odds_list

    implied = [1.0 / o for o in odds_list]
    total = sum(implied)

    if total <= 1.0:
        return odds_list

    if method == "power":
        fair = [p / total for p in implied]
        return [1.0 / p if p > 0 else 999.0 for p in fair]

    return odds_list


def calculate_edge(
    p_model: float,
    odds: float,
    confidence: str = "medium",
    sample_size: int = 0,
) -> EdgeResult:
    """Calculate edge for a single bet."""
    p_impl = 1.0 / odds if odds > 0 else 0.0
    edge = p_model - p_impl

    if edge >= config.edge.strong_edge and confidence != "low":
        recommendation = "EDGE FORTE"
    elif edge >= config.edge.min_edge and confidence != "low":
        recommendation = "OBSERVAR"
    else:
        recommendation = "SEM EDGE"

    suggested_stake = 0.0
    if edge > 0 and odds > 1.0:
        kelly = (p_model * odds - 1) / (odds - 1)
        kelly = max(0, kelly)
        fractional_kelly = kelly * config.bankroll.kelly_fraction
        suggested_stake = round(
            min(
                config.bankroll.total * fractional_kelly,
                config.bankroll.total * config.bankroll.max_stake_pct,
            ),
            2,
        )

    return EdgeResult(
        market="",
        selection="",
        bookmaker="",
        odds=odds,
        p_impl=round(p_impl, 4),
        p_model=round(p_model, 4),
        edge=round(edge, 4),
        confidence=confidence,
        sample_size=sample_size,
        recommendation=recommendation,
        suggested_stake=suggested_stake,
    )


def analyze_market_edges(
    match_id: int,
    market_probs: dict[str, dict],
    data_filter: DataFilter | None = None,
) -> list[EdgeResult]:
    """Compare model probabilities against all odds for a match.

    Args:
        match_id: the match to look up odds for
        market_probs: dict mapping market keys to
            {"p_model": float, "confidence": str, "sample_size": int, "map_number": int|None}

    Returns list of EdgeResult for every market with odds in the DB.
    """
    with get_db() as conn:
        odds_rows = conn.execute(
            """SELECT * FROM odds_snapshots
               WHERE match_id = ?
               ORDER BY timestamp DESC""",
            (match_id,),
        ).fetchall()

    latest_odds: dict[tuple, dict] = {}
    for row in odds_rows:
        key = (row["market_type"], row["selection"], row["bookmaker"])
        if key not in latest_odds:
            latest_odds[key] = dict(row)

    results = []
    for (market_type, selection, bookmaker), odds_data in latest_odds.items():
        market_key = _build_market_key(market_type, selection, odds_data.get("map_number"))
        prob_info = market_probs.get(market_key)
        if not prob_info:
            continue

        edge_result = calculate_edge(
            p_model=prob_info["p_model"],
            odds=odds_data["odds_value"],
            confidence=prob_info.get("confidence", "low"),
            sample_size=prob_info.get("sample_size", 0),
        )
        edge_result.market = market_type
        edge_result.selection = selection
        edge_result.bookmaker = bookmaker
        edge_result.map_number = odds_data.get("map_number")
        results.append(edge_result)

    results.sort(key=lambda x: x.edge, reverse=True)
    return results


def _build_market_key(market_type: str, selection: str, map_number: int | None) -> str:
    """Normalize a market key for lookup."""
    parts = [market_type.lower()]
    if map_number:
        parts.append(f"map{map_number}")
    parts.append(selection.lower())
    return "|".join(parts)


def build_market_probs(
    map_analyses: list,
    series_result: dict | None = None,
    ot_results: list[dict] | None = None,
) -> dict[str, dict]:
    """Build the market_probs dict from analysis results for use with analyze_market_edges.

    Returns a dict mapping market_key -> {p_model, confidence, sample_size, map_number}.
    """
    probs: dict[str, dict] = {}

    for i, ma in enumerate(map_analyses):
        map_num = ma.map_order or (i + 1)

        team_a_key = f"map{map_num}_winner|map{map_num}|{(ma.team_a_stats.team_name if ma.team_a_stats else 'team_a').lower()}"
        team_b_key = f"map{map_num}_winner|map{map_num}|{(ma.team_b_stats.team_name if ma.team_b_stats else 'team_b').lower()}"
        probs[team_a_key] = {
            "p_model": ma.p_team_a_win,
            "confidence": ma.confidence,
            "sample_size": ma.sample_size,
            "map_number": map_num,
        }
        probs[team_b_key] = {
            "p_model": round(1 - ma.p_team_a_win, 4),
            "confidence": ma.confidence,
            "sample_size": ma.sample_size,
            "map_number": map_num,
        }

    if ot_results:
        for i, ot in enumerate(ot_results):
            map_num = i + 1
            probs[f"map{map_num}_ot|map{map_num}|yes"] = {
                "p_model": ot["p_ot"],
                "confidence": ot["confidence"],
                "sample_size": ot["sample_size"],
                "map_number": map_num,
            }
            probs[f"map{map_num}_ot|map{map_num}|no"] = {
                "p_model": round(1 - ot["p_ot"], 4),
                "confidence": ot["confidence"],
                "sample_size": ot["sample_size"],
                "map_number": map_num,
            }

    if series_result:
        for score_str, prob in series_result.get("score_probs", {}).items():
            probs[f"correct_score||{score_str}"] = {
                "p_model": prob,
                "confidence": "medium",
                "sample_size": 0,
                "map_number": None,
            }

        if "p_over_3.5_maps" in series_result:
            probs["over_3.5_maps||yes"] = {
                "p_model": series_result["p_over_3.5_maps"],
                "confidence": "medium",
                "sample_size": 0,
                "map_number": None,
            }
            probs["over_3.5_maps||no"] = {
                "p_model": round(1 - series_result["p_over_3.5_maps"], 4),
                "confidence": "medium",
                "sample_size": 0,
                "map_number": None,
            }

    return probs
