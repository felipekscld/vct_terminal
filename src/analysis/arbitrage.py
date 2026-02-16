"""Arbitrage and cross-bookmaker comparison.

Detects surebets and anomalies when odds from Betano and Bet365
imply probabilities that sum to less than 1.
"""

from __future__ import annotations

from src.db.connection import get_db


def detect_arbitrage(match_id: int) -> list[dict]:
    """Find arbitrage opportunities across bookmakers for a match.

    Returns a list of arb opportunities with details.
    """
    with get_db() as conn:
        rows = conn.execute(
            """SELECT market_type, selection, bookmaker, odds_value, map_number,
                      timestamp
               FROM odds_snapshots
               WHERE match_id = ?
               ORDER BY market_type, map_number, timestamp DESC""",
            (match_id,),
        ).fetchall()

    markets: dict[tuple, dict[str, list]] = {}
    for r in rows:
        key = (r["market_type"], r["map_number"])
        if key not in markets:
            markets[key] = {}
        sel = r["selection"]
        if sel not in markets[key]:
            markets[key][sel] = []
        markets[key][sel].append({
            "bookmaker": r["bookmaker"],
            "odds": r["odds_value"],
            "timestamp": r["timestamp"],
        })

    arbs = []
    for (market_type, map_number), selections in markets.items():
        if len(selections) < 2:
            continue

        best_per_selection: dict[str, dict] = {}
        for sel, entries in selections.items():
            best = max(entries, key=lambda x: x["odds"])
            best_per_selection[sel] = best

        implied_sum = sum(1.0 / b["odds"] for b in best_per_selection.values())

        if implied_sum < 1.0:
            margin = round((1 - implied_sum) * 100, 2)
            arbs.append({
                "market_type": market_type,
                "map_number": map_number,
                "is_arb": True,
                "implied_sum": round(implied_sum, 4),
                "margin_pct": margin,
                "selections": {
                    sel: {"bookmaker": info["bookmaker"], "odds": info["odds"]}
                    for sel, info in best_per_selection.items()
                },
                "description": f"SUREBET {market_type} map{map_number or ''}: "
                               f"margin={margin}%",
            })
        else:
            overround = round((implied_sum - 1) * 100, 2)
            for sel, entries in selections.items():
                if len(entries) >= 2:
                    odds_vals = [e["odds"] for e in entries]
                    max_o = max(odds_vals)
                    min_o = min(odds_vals)
                    if max_o > 0 and (max_o - min_o) / min_o > 0.08:
                        arbs.append({
                            "market_type": market_type,
                            "map_number": map_number,
                            "is_arb": False,
                            "implied_sum": round(implied_sum, 4),
                            "overround_pct": overround,
                            "anomaly_selection": sel,
                            "selections": {
                                sel: [{"bookmaker": e["bookmaker"], "odds": e["odds"]}
                                      for e in entries]
                            },
                            "description": f"ANOMALIA {market_type} {sel}: "
                                           f"spread={round(max_o - min_o, 2)} "
                                           f"({min_o} vs {max_o})",
                        })

    return arbs
