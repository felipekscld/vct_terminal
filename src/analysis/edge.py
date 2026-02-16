"""Edge calculator: compare p_model vs p_impl from bookmaker odds.

All analysis respects the active DataFilter.

Market key format (for matching odds to model):
  market_type|mapN?|selection
  - market_type: e.g. map1_winner, map1_ot, correct_score, over_3.5_maps
  - mapN: optional, for per-map markets (map1, map2, ...)
  - selection: e.g. team name/tag for map winner, "yes"/"no" for OT, score string for correct_score

Adding new markets (when Openclaw or a house starts recording a new market_type/selection):
  1. If the market has a model-derived probability: in build_market_probs() add the logic to
     produce the key and p_model (using map_analyses, series_result, or ot_results as needed).
  2. Add the market_type to ALL_MARKET_TYPES and MARKET_LABELS in src/config.py if it should
     appear in UI/config.
  3. Markets without model support can still be stored in odds_snapshots; they will show edges
     once the corresponding key and p_model are added in build_market_probs.
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

    strong_ok = config.edge.min_sample_for_strong is None or sample_size >= config.edge.min_sample_for_strong
    observe_ok = config.edge.min_sample_for_observe is None or sample_size >= config.edge.min_sample_for_observe
    if edge >= config.edge.strong_edge and confidence != "low" and strong_ok:
        recommendation = "EDGE FORTE"
    elif edge >= config.edge.min_edge and confidence != "low" and observe_ok:
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
    """Normalize a market key for lookup. Format: market_type|mapN?|selection (e.g. map1_winner|map1|nrg)."""
    parts = [market_type.lower()]
    if map_number:
        parts.append(f"map{map_number}")
    parts.append(selection.lower())
    return "|".join(parts)


def build_market_probs(
    map_analyses: list,
    series_result: dict | None = None,
    ot_results: list[dict] | None = None,
    team_a_aliases: list[str] | None = None,
    team_b_aliases: list[str] | None = None,
) -> dict[str, dict]:
    """Build the market_probs dict from analysis results for use with analyze_market_edges.

    Returns a dict mapping market_key -> {p_model, confidence, sample_size, map_number}.
    When team_a_aliases/team_b_aliases are provided (e.g. [name, tag]), each normalized
    alias gets the same prob entry so odds with selection "NRG" or "Sentinels" can match.
    """
    probs: dict[str, dict] = {}

    for i, ma in enumerate(map_analyses):
        map_num = ma.map_order or (i + 1)
        team_a_name = (ma.team_a_stats.team_name if ma.team_a_stats else "team_a").strip().lower()
        team_b_name = (ma.team_b_stats.team_name if ma.team_b_stats else "team_b").strip().lower()

        team_a_norm = [team_a_name]
        if team_a_aliases:
            for a in team_a_aliases:
                if a and a.strip():
                    n = a.strip().lower()
                    if n not in team_a_norm:
                        team_a_norm.append(n)
        team_b_norm = [team_b_name]
        if team_b_aliases:
            for b in team_b_aliases:
                if b and b.strip():
                    n = b.strip().lower()
                    if n not in team_b_norm:
                        team_b_norm.append(n)

        val_a = {
            "p_model": ma.p_team_a_win,
            "confidence": ma.confidence,
            "sample_size": ma.sample_size,
            "map_number": map_num,
        }
        val_b = {
            "p_model": round(1 - ma.p_team_a_win, 4),
            "confidence": ma.confidence,
            "sample_size": ma.sample_size,
            "map_number": map_num,
        }
        for sel in team_a_norm:
            probs[f"map{map_num}_winner|map{map_num}|{sel}"] = val_a
        for sel in team_b_norm:
            probs[f"map{map_num}_winner|map{map_num}|{sel}"] = val_b

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
