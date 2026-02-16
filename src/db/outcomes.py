"""Register match outcomes for tracking (backtest/calibration of edges)."""

from __future__ import annotations

import json

from src.db.connection import get_db


def _get_map_results(conn, match_id: int) -> list[dict]:
    """Return map results for a match (maps table first, then live_map_results)."""
    rows = conn.execute(
        """SELECT map_order, map_name, team1_score, team2_score, winner_team_id
           FROM maps
           WHERE match_id = ? AND team1_score IS NOT NULL AND team2_score IS NOT NULL
           ORDER BY map_order""",
        (match_id,),
    ).fetchall()
    if rows:
        return [
            {
                "map_order": r["map_order"],
                "map_name": r["map_name"] or f"Map {r['map_order']}",
                "team1_score": r["team1_score"],
                "team2_score": r["team2_score"],
                "winner_team_id": r["winner_team_id"],
            }
            for r in rows
        ]
    live = conn.execute(
        """SELECT map_number, map_name, winner_team_id, score_a, score_b
           FROM live_map_results
           WHERE match_id = ?
           ORDER BY map_number""",
        (match_id,),
    ).fetchall()
    if not live:
        return []
    return [
        {
            "map_order": r["map_number"],
            "map_name": r["map_name"] or f"Map {r['map_number']}",
            "team1_score": r["score_a"],
            "team2_score": r["score_b"],
            "winner_team_id": r["winner_team_id"],
        }
        for r in live
    ]


def register_match_outcome(match_id: int) -> bool:
    """If match is completed and not yet in match_outcomes, insert score1/score2 and map results.
    Returns True if a row was inserted, False otherwise."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT score1, score2, status FROM matches WHERE id = ?",
            (match_id,),
        ).fetchone()
        if not row or row["status"] != "completed":
            return False
        score1 = row["score1"]
        score2 = row["score2"]
        if score1 is None and score2 is None:
            return False
        score1 = score1 if score1 is not None else 0
        score2 = score2 if score2 is not None else 0

        existing = conn.execute(
            "SELECT 1 FROM match_outcomes WHERE match_id = ?",
            (match_id,),
        ).fetchone()
        if existing:
            return False

        map_results = _get_map_results(conn, match_id)
        map_results_json = json.dumps(map_results) if map_results else None

        conn.execute(
            """INSERT INTO match_outcomes (match_id, score1, score2, map_results_json, created_at)
               VALUES (?, ?, ?, ?, datetime('now'))""",
            (match_id, score1, score2, map_results_json),
        )
    return True
