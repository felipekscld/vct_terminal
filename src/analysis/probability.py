"""Core probability estimation engine.

Estimates p_model for map wins, OT, and series outcomes.
All calculations respect the active DataFilter so only relevant
event/stage/date data is used.
"""

from __future__ import annotations

import math
import random
from typing import Optional

from src.config import config, DataFilter
from src.analysis.maps import (
    get_team_map_stats,
    get_h2h_stats,
    get_global_map_stats,
)
from src.analysis.compositions import get_comp_stats_for_matchup
from src.models.data_models import MapAnalysis, TeamStats


def _resolve_filter(filt: DataFilter | None) -> DataFilter:
    return filt if filt is not None else config.data_filter


def _confidence_level(sample_size: int) -> str:
    """Determine confidence from sample size."""
    if sample_size >= config.edge.min_sample_general * 2:
        return "high"
    elif sample_size >= config.edge.min_sample_map:
        return "medium"
    return "low"


def _wilson_lower(wins: int, total: int, z: float = 1.0) -> float:
    """Wilson score lower bound for a proportion (conservative estimate)."""
    if total == 0:
        return 0.5
    p = wins / total
    denom = 1 + z * z / total
    centre = p + z * z / (2 * total)
    spread = z * math.sqrt((p * (1 - p) + z * z / (4 * total)) / total)
    return max(0.0, min(1.0, (centre - spread) / denom))


def _safe_rate(wins: int, total: int, prior: float = 0.5) -> float:
    """Bayesian-ish rate with a weak prior towards 0.5 for tiny samples."""
    if total == 0:
        return prior
    return (wins + prior) / (total + 1.0)



def estimate_map_win(
    team_a_id: int,
    team_b_id: int,
    map_name: str,
    starting_side_a: str | None = None,
    comp_a: list[str] | None = None,
    comp_b: list[str] | None = None,
    data_filter: DataFilter | None = None,
    bo_type: str | None = None,
) -> MapAnalysis:
    """Estimate P(team_a wins map_name) using weighted factors.

    All data queries are filtered by data_filter (or config.data_filter).
    When bo_type is set ('bo3' or 'bo5'), only historical data from matches
    of that format is used (Bo5 probs use only Bo5 past results, etc.).
    """
    filt = _resolve_filter(data_filter)
    w = config.model_weights

    a_stats = get_team_map_stats(team_a_id, map_name, data_filter=filt, bo_type=bo_type)
    b_stats = get_team_map_stats(team_b_id, map_name, data_filter=filt, bo_type=bo_type)

    sample = a_stats.games_played + b_stats.games_played
    factors: dict = {"filter": filt.description, "sample_a": a_stats.games_played, "sample_b": b_stats.games_played}

    base_a = _safe_rate(a_stats.wins, a_stats.games_played)
    base_b = _safe_rate(b_stats.wins, b_stats.games_played)
    p_base = base_a / (base_a + base_b) if (base_a + base_b) > 0 else 0.5
    factors["base_winrate"] = round(p_base, 4)

    rd_a = a_stats.avg_round_diff
    rd_b = b_stats.avg_round_diff
    diff = rd_a - rd_b
    p_opp = 1 / (1 + math.exp(-diff / 3.0))
    factors["opponent_adjusted"] = round(p_opp, 4)

    h2h = get_h2h_stats(team_a_id, team_b_id, map_name=map_name, data_filter=filt, bo_type=bo_type)
    if h2h["total_maps"] >= 1:
        p_h2h = _safe_rate(h2h["a_wins"], h2h["total_maps"])
    else:
        p_h2h = 0.5
    factors["h2h"] = round(p_h2h, 4)
    factors["h2h_maps"] = h2h["total_maps"]

    p_side = 0.5
    if starting_side_a:
        if starting_side_a.lower() in ("attacker", "atk"):
            p_side = 0.5 + (a_stats.atk_round_rate - 0.5) * 0.3
        else:
            p_side = 0.5 + (a_stats.def_round_rate - 0.5) * 0.3
        p_side = max(0.3, min(0.7, p_side))
    factors["side_advantage"] = round(p_side, 4)

    p_comp = 0.5
    if comp_a and comp_b:
        comp_info = get_comp_stats_for_matchup(
            team_a_id, team_b_id, map_name, comp_a, comp_b, data_filter=filt, bo_type=bo_type
        )
        if comp_info.get("has_data"):
            p_comp = comp_info["p_a_advantage"]
    factors["comp_factor"] = round(p_comp, 4)

    pistol_diff = a_stats.pistol_rate - b_stats.pistol_rate
    p_pistol = 0.5 + pistol_diff * 0.5
    p_pistol = max(0.3, min(0.7, p_pistol))
    factors["pistol"] = round(p_pistol, 4)

    p_recency = p_base
    factors["recency"] = round(p_recency, 4)

    p_model = (
        w.base_map_winrate * p_base
        + w.opponent_adjusted * p_opp
        + w.h2h * p_h2h
        + w.side_advantage * p_side
        + w.comp_factor * p_comp
        + w.pistol_factor * p_pistol
        + w.recency * p_recency
    )
    p_model = max(0.05, min(0.95, p_model))

    return MapAnalysis(
        map_name=map_name,
        map_order=0,
        team_a_stats=a_stats,
        team_b_stats=b_stats,
        p_team_a_win=round(p_model, 4),
        confidence=_confidence_level(sample),
        sample_size=sample,
        factors=factors,
    )



def estimate_ot_prob(
    team_a_id: int,
    team_b_id: int,
    map_name: str,
    comp_a: list[str] | None = None,
    comp_b: list[str] | None = None,
    data_filter: DataFilter | None = None,
    bo_type: str | None = None,
) -> dict:
    """Estimate P(overtime) on a specific map between two teams.
    When bo_type is set, only historical data from matches of that format is used.
    """
    filt = _resolve_filter(data_filter)
    ow = config.ot_weights

    global_stats = get_global_map_stats(map_name, data_filter=filt, bo_type=bo_type)
    a_stats = get_team_map_stats(team_a_id, map_name, data_filter=filt, bo_type=bo_type)
    b_stats = get_team_map_stats(team_b_id, map_name, data_filter=filt, bo_type=bo_type)
    h2h = get_h2h_stats(team_a_id, team_b_id, map_name=map_name, data_filter=filt, bo_type=bo_type)

    sample = global_stats["total_maps"]
    factors: dict = {"filter": filt.description}

    global_ot = global_stats["ot_rate"] if global_stats["total_maps"] >= 3 else 0.15
    factors["global_ot_rate"] = round(global_ot, 4)

    close_a = a_stats.close_rate
    close_b = b_stats.close_rate
    closeness = (close_a + close_b) / 2
    if h2h["total_maps"] >= 2:
        closeness = closeness * 0.6 + h2h["ot_rate"] * 0.4
    factors["closeness"] = round(closeness, 4)

    comp_ot = global_ot
    if comp_a and comp_b:
        comp_info = get_comp_stats_for_matchup(
            team_a_id, team_b_id, map_name, comp_a, comp_b, data_filter=filt, bo_type=bo_type
        )
        if comp_info.get("ot_rate") is not None:
            comp_ot = comp_info["ot_rate"]
    factors["comp_ot_rate"] = round(comp_ot, 4)

    pistol_swing = (a_stats.pistol_rate + b_stats.pistol_rate) / 2
    pistol_factor = pistol_swing * 0.5 + abs(a_stats.pistol_rate - b_stats.pistol_rate) * -0.3
    pistol_factor = max(0.0, min(1.0, pistol_factor + 0.3))
    factors["pistol_swing"] = round(pistol_factor, 4)

    p_ot = (
        ow.global_ot_rate * global_ot
        + ow.closeness_index * closeness
        + ow.comp_ot_rate * comp_ot
        + ow.pistol_swing * pistol_factor
    )
    p_ot = max(0.02, min(0.60, p_ot))

    return {
        "p_ot": round(p_ot, 4),
        "confidence": _confidence_level(sample),
        "sample_size": sample,
        "factors": factors,
    }



def simulate_series(
    map_probs: list[float],
    maps_to_win: int = 2,
    n_sims: int | None = None,
) -> dict[str, float]:
    """Monte Carlo simulation of a BO series.

    Args:
        map_probs: list of P(team_a wins map_i) for each potential map
                   Length should be >= (2 * maps_to_win - 1)
        maps_to_win: 2 for BO3, 3 for BO5
        n_sims: number of simulations (defaults to config)

    Returns dict with score probabilities like {"2-0": 0.28, "2-1": 0.30, ...}
    and P(team_a wins series), P(series > N maps), etc.
    """
    if n_sims is None:
        n_sims = config.multibet.monte_carlo_sims

    max_maps = 2 * maps_to_win - 1
    while len(map_probs) < max_maps:
        map_probs.append(map_probs[-1] if map_probs else 0.5)

    score_counts: dict[str, int] = {}
    a_series_wins = 0

    for _ in range(n_sims):
        a_score = 0
        b_score = 0
        for i in range(max_maps):
            if random.random() < map_probs[i]:
                a_score += 1
            else:
                b_score += 1
            if a_score == maps_to_win or b_score == maps_to_win:
                break
        key = f"{a_score}-{b_score}"
        score_counts[key] = score_counts.get(key, 0) + 1
        if a_score == maps_to_win:
            a_series_wins += 1

    score_probs = {k: v / n_sims for k, v in sorted(score_counts.items())}
    p_a_series = a_series_wins / n_sims
    total_maps_dist = {}
    for score_str, prob in score_probs.items():
        parts = score_str.split("-")
        total = int(parts[0]) + int(parts[1])
        total_maps_dist[total] = total_maps_dist.get(total, 0) + prob

    result = {
        "p_a_series": round(p_a_series, 4),
        "p_b_series": round(1 - p_a_series, 4),
        "score_probs": {k: round(v, 4) for k, v in score_probs.items()},
        "total_maps_dist": {k: round(v, 4) for k, v in sorted(total_maps_dist.items())},
    }

    if maps_to_win == 3:
        result["p_over_3.5_maps"] = round(
            sum(v for k, v in total_maps_dist.items() if k >= 4), 4
        )
    elif maps_to_win == 2:
        result["p_3_maps"] = round(total_maps_dist.get(3, 0), 4)

    return result
