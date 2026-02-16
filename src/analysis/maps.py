"""Map-specific analysis: query DB for team stats on specific maps.

All functions accept a DataFilter to restrict which matches/events/dates
are included in calculations. If no filter is passed, falls back to
config.data_filter (the global active filter).
"""

from __future__ import annotations

from typing import Optional

from src.config import config, DataFilter
from src.db.connection import get_db
from src.models.data_models import TeamStats


def _resolve_filter(filt: DataFilter | None) -> DataFilter:
    """Use provided filter or fall back to global config."""
    return filt if filt is not None else config.data_filter


def _bo_type_sql(bo_type: str | None, alias: str = "mt") -> tuple[str, list]:
    """Return (SQL condition, params) to restrict to matches of the same series format.
    bo_type e.g. 'bo3', 'bo5', '3', '5'. When None, returns no restriction (use all data).
    """
    if not bo_type or str(bo_type).strip() == "":
        return "", []
    s = str(bo_type).lower()
    if "5" in s:
        return (
            f"({alias}.bo_type IS NOT NULL AND ({alias}.bo_type LIKE '%5%' OR {alias}.bo_type = '5'))",
            [],
        )
    return (
        f"({alias}.bo_type IS NULL OR {alias}.bo_type = '' OR {alias}.bo_type LIKE '%3%' OR {alias}.bo_type = '3')",
        [],
    )


def get_team_map_stats(
    team_id: int,
    map_name: str,
    data_filter: DataFilter | None = None,
    bo_type: str | None = None,
) -> TeamStats:
    """Aggregate stats for a team on a specific map.

    Uses data_filter to restrict to specific events, stages, and/or date range.
    When bo_type is set ('bo3' or 'bo5'), only maps from matches of that format are used.
    """
    filt = _resolve_filter(data_filter)

    with get_db() as conn:
        conditions = ["m.map_name = ?", "(m.team1_id = ? OR m.team2_id = ?)"]
        params: list = [map_name, team_id, team_id]

        filter_conds, filter_params = filt.build_sql_conditions("mt")
        conditions.extend(filter_conds)
        params.extend(filter_params)

        bo_cond, bo_params = _bo_type_sql(bo_type, "mt")
        if bo_cond:
            conditions.append(bo_cond)
            params.extend(bo_params)

        conditions.append("m.team1_score IS NOT NULL")
        conditions.append("m.team2_score IS NOT NULL")

        where = " AND ".join(conditions)
        rows = conn.execute(
            f"""SELECT m.*, mt.date, mt.event_id, mt.stage_name,
                       t1.name as t1_name, t2.name as t2_name,
                       e.name as event_name
                FROM maps m
                JOIN matches mt ON m.match_id = mt.id
                LEFT JOIN teams t1 ON m.team1_id = t1.id
                LEFT JOIN teams t2 ON m.team2_id = t2.id
                LEFT JOIN events e ON mt.event_id = e.id
                WHERE {where}
                ORDER BY mt.date DESC""",
            params,
        ).fetchall()

    team_name = ""
    stats = TeamStats(team_id=team_id, team_name="", map_name=map_name)
    map_ids = [r["id"] for r in rows]

    for r in rows:
        stats.games_played += 1
        is_team1 = r["team1_id"] == team_id

        if not team_name:
            team_name = r["t1_name"] if is_team1 else r["t2_name"]
            stats.team_name = team_name or ""

        my_score = r["team1_score"] if is_team1 else r["team2_score"]
        opp_score = r["team2_score"] if is_team1 else r["team1_score"]

        if r["winner_team_id"] == team_id:
            stats.wins += 1
        else:
            stats.losses += 1

        stats.avg_rounds_won += my_score or 0
        stats.avg_rounds_lost += opp_score or 0
        stats.avg_round_diff += (my_score or 0) - (opp_score or 0)

        if r["is_ot"]:
            stats.ot_count += 1

        total = (my_score or 0) + (opp_score or 0)
        if total >= 23:
            stats.close_maps += 1
        diff = abs((my_score or 0) - (opp_score or 0))
        if diff >= 7 and r["winner_team_id"] == team_id:
            stats.stomps_won += 1
        elif diff >= 7 and r["winner_team_id"] != team_id:
            stats.stomps_lost += 1

        if is_team1:
            my_atk = r["team1_atk_rounds"] or 0
            my_def = r["team1_def_rounds"] or 0
            my_pistols = r["team1_pistols_won"] or 0
            my_conversions = r["team1_pistol_conversions"] or 0
        else:
            my_atk = r["team2_atk_rounds"] or 0
            my_def = r["team2_def_rounds"] or 0
            my_pistols = r["team2_pistols_won"] or 0
            my_conversions = r["team2_pistol_conversions"] or 0

        stats.atk_rounds_won += my_atk
        stats.def_rounds_won += my_def
        half_rounds = max(12, (total + 1) // 2)
        stats.atk_rounds_played += half_rounds
        stats.def_rounds_played += half_rounds

        stats.pistols_won += my_pistols
        stats.pistols_played += 2
        stats.pistol_conversions += my_conversions

    if stats.games_played > 0:
        stats.avg_rounds_won /= stats.games_played
        stats.avg_rounds_lost /= stats.games_played
        stats.avg_round_diff /= stats.games_played

    if map_ids:
        with get_db() as conn2:
            placeholders = ",".join("?" for _ in map_ids)
            pistol_rows = conn2.execute(
                f"""SELECT winner_side, COUNT(*) AS cnt
                   FROM rounds
                   WHERE map_id IN ({placeholders}) AND round_number IN (1, 13)
                     AND winner_team_id = ?
                   GROUP BY winner_side""",
                [*map_ids, team_id],
            ).fetchall()
        for pr in pistol_rows:
            side = (pr["winner_side"] or "").lower()
            cnt = pr["cnt"] or 0
            if "attack" in side or side == "attacker":
                stats.pistol_atk_won = cnt
            elif "defen" in side or side == "defender":
                stats.pistol_def_won = cnt
        stats.pistol_atk_played = stats.games_played
        stats.pistol_def_played = stats.games_played

    return stats


def get_h2h_stats(
    team_a_id: int,
    team_b_id: int,
    map_name: str | None = None,
    data_filter: DataFilter | None = None,
    bo_type: str | None = None,
) -> dict:
    """Get head-to-head record between two teams, filtered by DataFilter.
    When bo_type is set, only maps from matches of that format are included.
    """
    filt = _resolve_filter(data_filter)

    with get_db() as conn:
        conditions = [
            "((m.team1_id = ? AND m.team2_id = ?) OR (m.team1_id = ? AND m.team2_id = ?))"
        ]
        params: list = [team_a_id, team_b_id, team_b_id, team_a_id]

        filter_conds, filter_params = filt.build_sql_conditions("mt")
        conditions.extend(filter_conds)
        params.extend(filter_params)

        bo_cond, bo_params = _bo_type_sql(bo_type, "mt")
        if bo_cond:
            conditions.append(bo_cond)
            params.extend(bo_params)

        if map_name:
            conditions.append("m.map_name = ?")
            params.append(map_name)

        conditions.append("m.team1_score IS NOT NULL")
        where = " AND ".join(conditions)

        rows = conn.execute(
            f"""SELECT m.* FROM maps m
                JOIN matches mt ON m.match_id = mt.id
                WHERE {where}""",
            params,
        ).fetchall()

    a_wins = sum(1 for r in rows if r["winner_team_id"] == team_a_id)
    b_wins = sum(1 for r in rows if r["winner_team_id"] == team_b_id)
    ot_count = sum(1 for r in rows if r["is_ot"])

    return {
        "total_maps": len(rows),
        "a_wins": a_wins,
        "b_wins": b_wins,
        "ot_count": ot_count,
        "ot_rate": ot_count / len(rows) if rows else 0,
    }


def get_global_map_stats(
    map_name: str,
    data_filter: DataFilter | None = None,
    bo_type: str | None = None,
) -> dict:
    """Get global statistics for a map across filtered events/dates.
    When bo_type is set, only maps from matches of that format are included.
    """
    filt = _resolve_filter(data_filter)

    with get_db() as conn:
        conditions = ["m.map_name = ?", "m.team1_score IS NOT NULL"]
        params: list = [map_name]

        filter_conds, filter_params = filt.build_sql_conditions("mt")
        conditions.extend(filter_conds)
        params.extend(filter_params)

        bo_cond, bo_params = _bo_type_sql(bo_type, "mt")
        if bo_cond:
            conditions.append(bo_cond)
            params.extend(bo_params)

        where = " AND ".join(conditions)
        rows = conn.execute(
            f"""SELECT m.* FROM maps m
                JOIN matches mt ON m.match_id = mt.id
                WHERE {where}""",
            params,
        ).fetchall()

    total = len(rows)
    ot_count = sum(1 for r in rows if r["is_ot"])
    close_count = sum(1 for r in rows
                      if (r["team1_score"] or 0) + (r["team2_score"] or 0) >= 23)

    avg_total_rounds = 0.0
    if total:
        avg_total_rounds = sum(
            (r["team1_score"] or 0) + (r["team2_score"] or 0) for r in rows
        ) / total

    return {
        "total_maps": total,
        "ot_count": ot_count,
        "ot_rate": ot_count / total if total else 0,
        "close_count": close_count,
        "close_rate": close_count / total if total else 0,
        "avg_total_rounds": avg_total_rounds,
    }


def list_available_filters() -> dict:
    """Query the DB to show which events, stages, and date ranges are available."""
    with get_db() as conn:
        events = conn.execute(
            "SELECT id, name, status FROM events ORDER BY id DESC"
        ).fetchall()

        stages = conn.execute(
            """SELECT DISTINCT s.event_id, e.name as event_name, s.name
               FROM stages s JOIN events e ON s.event_id = e.id
               ORDER BY s.event_id DESC, s.name"""
        ).fetchall()

        date_range = conn.execute(
            "SELECT MIN(date) as min_date, MAX(date) as max_date FROM matches WHERE date IS NOT NULL"
        ).fetchone()

        match_counts = conn.execute(
            """SELECT e.name, COUNT(*) as cnt
               FROM matches m JOIN events e ON m.event_id = e.id
               WHERE m.status = 'completed'
               GROUP BY m.event_id ORDER BY cnt DESC"""
        ).fetchall()

    return {
        "events": [dict(e) for e in events],
        "stages": [dict(s) for s in stages],
        "date_range": dict(date_range) if date_range else {},
        "match_counts": [dict(m) for m in match_counts],
    }
