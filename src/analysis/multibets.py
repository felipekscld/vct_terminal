"""Multi-bet engine: parlay, spread, hedge, dutch, correct score optimizer.

Finds +EV opportunities that go beyond single bets by combining
multiple selections or spreading across maps.
"""

from __future__ import annotations

import math
from itertools import combinations, product
from typing import Optional

from src.config import config
from src.models.data_models import EdgeResult, MultiBetOpportunity



def analyze_spread(
    map_probs: list[float],
    map_odds: list[float],
    market_label: str = "OT",
    stake_per_map: float = 10.0,
) -> MultiBetOpportunity | None:
    """Analyze buying the same bet on every map (e.g., OT Yes on all maps).

    Args:
        map_probs: P(event happens) per map from model
        map_odds: decimal odds per map from bookmaker
        market_label: descriptive label (e.g., "OT", "Over 24.5 rds")
        stake_per_map: how much to bet per map

    Returns MultiBetOpportunity or None if not +EV.
    """
    n = len(map_probs)
    if n == 0 or len(map_odds) != n:
        return None

    total_stake = stake_per_map * n
    min_payout = min(stake_per_map * o for o in map_odds)

    corr = config.multibet.correlation_factor

    p_zero_raw = 1.0
    for p in map_probs:
        p_zero_raw *= (1 - p)

    p_zero = min(1.0, p_zero_raw * (1 + corr * (n - 1)))
    p_at_least_1 = 1 - p_zero

    mean_hits = sum(map_probs)
    hit_distribution = _poisson_binomial_approx(map_probs, corr)

    ev_by_hits: dict[int, float] = {}
    for k in range(n + 1):
        if k == 0:
            ev_by_hits[k] = -total_stake
        else:
            expected_payout = 0.0
            for combo in combinations(range(n), k):
                combo_payout = sum(stake_per_map * map_odds[i] for i in combo)
                expected_payout += combo_payout
            n_combos = math.comb(n, k)
            expected_payout /= n_combos if n_combos > 0 else 1
            ev_by_hits[k] = expected_payout - total_stake

    total_ev = sum(hit_distribution.get(k, 0) * ev_by_hits.get(k, 0) for k in range(n + 1))

    breakeven_hits = 0
    for k in range(1, n + 1):
        if ev_by_hits.get(k, 0) > 0:
            breakeven_hits = k
            break

    details = {
        "maps": n,
        "stake_per_map": stake_per_map,
        "total_stake": total_stake,
        "min_payout": round(min_payout, 2),
        "p_at_least_1": round(p_at_least_1, 4),
        "p_at_least_2": round(sum(v for k, v in hit_distribution.items() if k >= 2), 4),
        "mean_hits": round(mean_hits, 2),
        "breakeven_hits": breakeven_hits,
        "hit_distribution": {k: round(v, 4) for k, v in hit_distribution.items()},
        "map_probs": [round(p, 4) for p in map_probs],
        "map_odds": map_odds,
    }

    if total_ev <= 0:
        return None

    return MultiBetOpportunity(
        strategy="spread",
        description=f"{market_label} em todos os {n} mapas",
        total_stake=total_stake,
        min_payout=round(min_payout, 2),
        p_model=round(p_at_least_1, 4),
        ev=round(total_ev, 2),
        edge=round(total_ev / total_stake, 4) if total_stake > 0 else 0,
        details=details,
    )



def analyze_parlay(
    legs: list[dict],
) -> MultiBetOpportunity | None:
    """Analyze a parlay (accumulator) bet.

    Args:
        legs: list of {"market": str, "selection": str, "p_model": float,
                       "odds": float, "bookmaker": str, "confidence": str}

    Returns MultiBetOpportunity or None if not +EV.
    """
    if len(legs) < 2:
        return None

    corr = config.multibet.correlation_factor

    combined_odds = 1.0
    for leg in legs:
        combined_odds *= leg["odds"]

    combined_p = 1.0
    for leg in legs:
        combined_p *= leg["p_model"]

    n = len(legs)
    correlation_penalty = 1.0 - corr * (n - 1) * 0.5
    combined_p *= max(0.5, correlation_penalty)
    combined_p = min(0.99, combined_p)

    p_impl = 1.0 / combined_odds if combined_odds > 0 else 0
    edge = combined_p - p_impl

    if edge < config.multibet.min_parlay_edge:
        return None

    description_parts = [f"{l['selection']}@{l['odds']}" for l in legs]

    return MultiBetOpportunity(
        strategy="parlay",
        description=" + ".join(description_parts),
        combined_odds=round(combined_odds, 2),
        p_model=round(combined_p, 4),
        p_impl=round(p_impl, 4),
        edge=round(edge, 4),
        details={
            "legs": legs,
            "correlation_factor": corr,
            "n_legs": n,
        },
    )


def find_profitable_parlays(
    available_bets: list[dict],
    max_legs: int = 3,
) -> list[MultiBetOpportunity]:
    """Search for +EV parlays from available individual bets.

    Tests all 2-leg and 3-leg combinations from available_bets.
    """
    results = []
    for size in range(2, max_legs + 1):
        for combo in combinations(available_bets, size):
            opp = analyze_parlay(list(combo))
            if opp:
                results.append(opp)

    results.sort(key=lambda x: x.edge, reverse=True)
    return results[:10]



def analyze_parlay_cross_match(
    legs: list[dict],
) -> MultiBetOpportunity | None:
    """Analyze a parlay where each leg is from a different match (no correlation penalty).

    Args:
        legs: list of {"market", "selection", "p_model", "odds", "bookmaker",
                      "match_id", "match_label"} (match_id/label for display)
    """
    if len(legs) < 2:
        return None

    combined_odds = 1.0
    for leg in legs:
        combined_odds *= leg["odds"]

    combined_p = 1.0
    for leg in legs:
        combined_p *= leg["p_model"]
    combined_p = min(0.99, combined_p)

    p_impl = 1.0 / combined_odds if combined_odds > 0 else 0
    edge = combined_p - p_impl

    if edge < config.multibet.min_parlay_edge:
        return None

    description_parts = [f"{l.get('match_label', '?')}: {l['selection']}@{l['odds']}" for l in legs]

    return MultiBetOpportunity(
        strategy="parlay",
        description=" | ".join(description_parts),
        combined_odds=round(combined_odds, 2),
        p_model=round(combined_p, 4),
        p_impl=round(p_impl, 4),
        edge=round(edge, 4),
        details={
            "legs": legs,
            "cross_match": True,
            "n_legs": len(legs),
        },
    )


def find_cross_match_parlays(
    matches_edges: list[dict],
    max_legs: int = 4,
) -> list[MultiBetOpportunity]:
    """Find +EV parlays with one leg per match (different games).

    Args:
        matches_edges: list of {
            "match_id": int,
            "match_label": str,
            "edges": [ {"market", "selection", "p_model", "odds", "bookmaker", "confidence"}, ... ]
        }
        max_legs: max number of legs (matches) in the parlay.

    Returns up to 10 best cross-match parlays, sorted by edge.
    """
    results = []
    n_matches = len(matches_edges)
    if n_matches < 2:
        return results

    for size in range(2, min(max_legs + 1, n_matches + 1)):
        for match_combo in combinations(matches_edges, size):
            legs_per_match = []
            for m in match_combo:
                positive = [e for e in m["edges"] if e.get("p_model", 0) > 0 and e.get("odds", 0) > 1]
                if not positive:
                    break
                best = max(positive, key=lambda e: e.get("edge", 0) or 0)
                leg = {
                    "market": best.get("market", ""),
                    "selection": best.get("selection", ""),
                    "p_model": best.get("p_model", 0),
                    "odds": best.get("odds", 0),
                    "bookmaker": best.get("bookmaker", ""),
                    "confidence": best.get("confidence", ""),
                    "match_id": m["match_id"],
                    "match_label": m.get("match_label", f"Match {m['match_id']}"),
                }
                if "edge" in best:
                    leg["edge"] = best["edge"]
                legs_per_match.append(leg)
            if len(legs_per_match) == size:
                opp = analyze_parlay_cross_match(legs_per_match)
                if opp:
                    results.append(opp)

    results.sort(key=lambda x: x.edge, reverse=True)
    return results[:10]



def dutch_calculator(
    outcomes: list[dict],
    total_stake: float,
) -> dict:
    """Calculate optimal stake distribution for dutching.

    Args:
        outcomes: list of {"selection": str, "odds": float, "bookmaker": str}
        total_stake: total amount to distribute

    Returns dict with stake per outcome and guaranteed profit (or loss).
    """
    if not outcomes:
        return {"error": "No outcomes provided"}

    implied_probs = [1.0 / o["odds"] for o in outcomes]
    total_implied = sum(implied_probs)

    stakes = []
    for i, o in enumerate(outcomes):
        stake = total_stake * (implied_probs[i] / total_implied)
        payout = stake * o["odds"]
        stakes.append({
            "selection": o["selection"],
            "bookmaker": o["bookmaker"],
            "odds": o["odds"],
            "stake": round(stake, 2),
            "payout": round(payout, 2),
        })

    payouts = [s["payout"] for s in stakes]
    guaranteed_return = min(payouts)
    profit = guaranteed_return - total_stake

    return {
        "stakes": stakes,
        "total_stake": round(total_stake, 2),
        "guaranteed_return": round(guaranteed_return, 2),
        "profit": round(profit, 2),
        "is_profitable": profit > 0,
        "roi_pct": round((profit / total_stake) * 100, 2) if total_stake > 0 else 0,
    }


def hedge_calculator(
    original_stake: float,
    original_odds: float,
    hedge_odds: float,
    lock_profit: bool = True,
) -> dict:
    """Calculate hedge bet to lock in profit or minimize loss.

    Args:
        original_stake: amount bet on original selection
        original_odds: decimal odds of original bet
        hedge_odds: current decimal odds for the opposite outcome
        lock_profit: if True, calculates stake to guarantee equal profit

    Returns dict with hedge stake and outcomes.
    """
    original_payout = original_stake * original_odds

    if lock_profit:
        hedge_stake = original_payout / hedge_odds
        profit_if_original = original_payout - original_stake - hedge_stake
        profit_if_hedge = hedge_stake * hedge_odds - original_stake - hedge_stake
    else:
        hedge_stake = original_stake / (hedge_odds - 1)
        profit_if_original = original_payout - original_stake - hedge_stake
        profit_if_hedge = hedge_stake * hedge_odds - original_stake - hedge_stake

    return {
        "original_stake": round(original_stake, 2),
        "original_odds": original_odds,
        "original_payout": round(original_payout, 2),
        "hedge_stake": round(hedge_stake, 2),
        "hedge_odds": hedge_odds,
        "hedge_payout": round(hedge_stake * hedge_odds, 2),
        "profit_if_original_wins": round(profit_if_original, 2),
        "profit_if_hedge_wins": round(profit_if_hedge, 2),
        "total_invested": round(original_stake + hedge_stake, 2),
        "guaranteed_profit": round(min(profit_if_original, profit_if_hedge), 2),
    }



def correct_score_coverage(
    score_probs: dict[str, float],
    score_odds: dict[str, float],
    total_budget: float = 50.0,
) -> MultiBetOpportunity | None:
    """Find +EV correct score bets by comparing model distribution vs odds.

    Args:
        score_probs: model probabilities {"2-0": 0.28, "2-1": 0.30, ...}
        score_odds: bookmaker odds {"2-0": 3.50, "2-1": 3.80, ...}
        total_budget: max total stake across all score bets

    Returns MultiBetOpportunity covering +EV scores, or None.
    """
    ev_scores = []
    for score, p_model in score_probs.items():
        if score not in score_odds:
            continue
        odds = score_odds[score]
        p_impl = 1.0 / odds if odds > 0 else 0
        edge = p_model - p_impl
        if edge > 0:
            ev_scores.append({
                "score": score,
                "p_model": round(p_model, 4),
                "odds": odds,
                "p_impl": round(p_impl, 4),
                "edge": round(edge, 4),
                "ev_per_unit": round(p_model * odds - 1, 4),
            })

    if not ev_scores:
        return None

    ev_scores.sort(key=lambda x: x["ev_per_unit"], reverse=True)

    total_ev = sum(s["ev_per_unit"] for s in ev_scores if s["ev_per_unit"] > 0)
    for s in ev_scores:
        if total_ev > 0:
            s["stake"] = round(total_budget * (s["ev_per_unit"] / total_ev), 2)
        else:
            s["stake"] = round(total_budget / len(ev_scores), 2)
        s["potential_return"] = round(s["stake"] * s["odds"], 2)

    actual_total = sum(s["stake"] for s in ev_scores)
    combined_p = sum(s["p_model"] for s in ev_scores)
    expected_return = sum(s["p_model"] * s["potential_return"] for s in ev_scores)
    total_ev_amount = expected_return - actual_total

    return MultiBetOpportunity(
        strategy="correct_score",
        description=f"Correct score coverage: {', '.join(s['score'] for s in ev_scores)}",
        total_stake=round(actual_total, 2),
        p_model=round(combined_p, 4),
        ev=round(total_ev_amount, 2),
        edge=round(total_ev_amount / actual_total, 4) if actual_total > 0 else 0,
        details={
            "scores": ev_scores,
            "expected_return": round(expected_return, 2),
        },
    )



def _poisson_binomial_approx(
    probs: list[float],
    correlation: float = 0.0,
) -> dict[int, float]:
    """Approximate Poisson binomial distribution with correlation adjustment.

    Returns {k: P(exactly k successes)} for k in 0..n.
    """
    n = len(probs)
    if n == 0:
        return {0: 1.0}

    dp = [0.0] * (n + 1)
    dp[0] = 1.0

    for p in probs:
        new_dp = [0.0] * (n + 1)
        for k in range(n + 1):
            new_dp[k] += dp[k] * (1 - p)
            if k > 0:
                new_dp[k] += dp[k - 1] * p
        dp = new_dp

    if correlation > 0 and n >= 2:
        for k in range(n + 1):
            dist_from_mean = abs(k - sum(probs))
            dp[k] *= (1 + correlation * dist_from_mean * 0.1)

        total = sum(dp)
        if total > 0:
            dp = [v / total for v in dp]

    return {k: dp[k] for k in range(n + 1)}
