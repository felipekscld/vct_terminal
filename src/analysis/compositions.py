"""Composition analysis: meta classification, per-comp stats, matchup scoring.

All queries respect DataFilter for event/stage/date scoping.
"""

from __future__ import annotations

import hashlib
from typing import Optional

from src.config import config, DataFilter
from src.db.connection import get_db
from src.analysis.maps import _bo_type_sql


ROLE_KEYWORDS = {
    "controller": ["omen", "brimstone", "viper", "astra", "harbor", "clove"],
    "duelist": ["jett", "raze", "reyna", "phoenix", "neon", "yoru", "iso", "waylay"],
    "initiator": ["sova", "breach", "skye", "kayo", "fade", "gekko", "tejo"],
    "sentinel": ["killjoy", "cypher", "sage", "chamber", "deadlock", "vyse"],
}


def _resolve_filter(filt: DataFilter | None) -> DataFilter:
    return filt if filt is not None else config.data_filter


def classify_comp(agents: list[str]) -> dict[str, int]:
    """Classify a composition by role counts."""
    roles: dict[str, int] = {"controller": 0, "duelist": 0, "initiator": 0, "sentinel": 0}
    for agent in agents:
        a = agent.lower().strip()
        for role, names in ROLE_KEYWORDS.items():
            if a in names:
                roles[role] += 1
                break
    return roles


def comp_hash(agents: list[str]) -> str:
    """Deterministic hash for a sorted agent list."""
    sorted_agents = sorted(a.lower().strip() for a in agents if a)
    return hashlib.md5("|".join(sorted_agents).encode()).hexdigest()[:12]


def get_comp_winrate(
    comp_agents: list[str],
    map_name: str,
    team_id: int | None = None,
    data_filter: DataFilter | None = None,
    bo_type: str | None = None,
) -> dict:
    """Get win rate and stats for a specific composition on a map.

    If team_id is provided, returns team-specific stats.
    Otherwise, returns global (meta) stats for that comp across all teams.
    When bo_type is set, only maps from matches of that format are included.
    """
    filt = _resolve_filter(data_filter)
    chash = comp_hash(comp_agents)

    with get_db() as conn:
        conditions = ["mc.comp_hash = ?", "m.map_name = ?"]
        params: list = [chash, map_name]

        if team_id:
            conditions.append("mc.team_id = ?")
            params.append(team_id)

        conditions.append("m.team1_score IS NOT NULL")

        filter_conds, filter_params = filt.build_sql_conditions("mt")
        conditions.extend(filter_conds)
        params.extend(filter_params)

        bo_cond, bo_params = _bo_type_sql(bo_type, "mt")
        if bo_cond:
            conditions.append(bo_cond)
            params.extend(bo_params)

        where = " AND ".join(conditions)
        rows = conn.execute(
            f"""SELECT m.*, mc.team_id as comp_team_id
                FROM map_compositions mc
                JOIN maps m ON mc.map_id = m.id
                JOIN matches mt ON m.match_id = mt.id
                WHERE {where}""",
            params,
        ).fetchall()

    total = len(rows)
    wins = sum(1 for r in rows if r["winner_team_id"] == r["comp_team_id"])
    ot_count = sum(1 for r in rows if r["is_ot"])
    close_count = sum(1 for r in rows
                      if (r["team1_score"] or 0) + (r["team2_score"] or 0) >= 23)

    return {
        "comp_hash": chash,
        "agents": comp_agents,
        "map_name": map_name,
        "team_id": team_id,
        "total": total,
        "wins": wins,
        "winrate": wins / total if total else 0.5,
        "ot_count": ot_count,
        "ot_rate": ot_count / total if total else None,
        "close_rate": close_count / total if total else None,
        "roles": classify_comp(comp_agents),
        "filter": filt.description,
    }


def get_comp_stats_for_matchup(
    team_a_id: int,
    team_b_id: int,
    map_name: str,
    comp_a: list[str],
    comp_b: list[str],
    data_filter: DataFilter | None = None,
    bo_type: str | None = None,
) -> dict:
    """Compare two compositions in a matchup context.

    Returns advantage signal and OT rate for the comp pair.
    When bo_type is set, only data from matches of that format is used.
    """
    filt = _resolve_filter(data_filter)

    a_team = get_comp_winrate(comp_a, map_name, team_id=team_a_id, data_filter=filt, bo_type=bo_type)
    b_team = get_comp_winrate(comp_b, map_name, team_id=team_b_id, data_filter=filt, bo_type=bo_type)

    a_meta = get_comp_winrate(comp_a, map_name, team_id=None, data_filter=filt, bo_type=bo_type)
    b_meta = get_comp_winrate(comp_b, map_name, team_id=None, data_filter=filt, bo_type=bo_type)

    has_data = (a_team["total"] + b_team["total"] + a_meta["total"] + b_meta["total"]) > 0

    team_weight = 0.6
    meta_weight = 0.4

    a_score = team_weight * a_team["winrate"] + meta_weight * a_meta["winrate"]
    b_score = team_weight * b_team["winrate"] + meta_weight * b_meta["winrate"]

    total_score = a_score + b_score
    p_a = a_score / total_score if total_score > 0 else 0.5

    ot_values = [v for v in [a_team.get("ot_rate"), b_team.get("ot_rate"),
                              a_meta.get("ot_rate"), b_meta.get("ot_rate")]
                 if v is not None]
    avg_ot = sum(ot_values) / len(ot_values) if ot_values else None

    return {
        "has_data": has_data,
        "p_a_advantage": round(p_a, 4),
        "a_team_stats": a_team,
        "b_team_stats": b_team,
        "a_meta_stats": a_meta,
        "b_meta_stats": b_meta,
        "ot_rate": avg_ot,
        "filter": filt.description,
    }


def get_team_likely_comp(
    team_id: int,
    map_name: str,
    data_filter: DataFilter | None = None,
    limit: int = 3,
) -> list[dict]:
    """Get the most frequently used compositions by a team on a map.

    Returns the top N comps with their usage count and win rate.
    """
    filt = _resolve_filter(data_filter)

    with get_db() as conn:
        conditions = ["mc.team_id = ?", "m.map_name = ?", "m.team1_score IS NOT NULL"]
        params: list = [team_id, map_name]

        filter_conds, filter_params = filt.build_sql_conditions("mt")
        conditions.extend(filter_conds)
        params.extend(filter_params)

        where = " AND ".join(conditions)
        rows = conn.execute(
            f"""SELECT mc.comp_hash, mc.agent1, mc.agent2, mc.agent3, mc.agent4, mc.agent5,
                       m.winner_team_id, mc.team_id,
                       COUNT(*) OVER (PARTITION BY mc.comp_hash) as usage_count
                FROM map_compositions mc
                JOIN maps m ON mc.map_id = m.id
                JOIN matches mt ON m.match_id = mt.id
                WHERE {where}
                ORDER BY mt.date DESC""",
            params,
        ).fetchall()

    comp_data: dict[str, dict] = {}
    for r in rows:
        ch = r["comp_hash"]
        if ch not in comp_data:
            agents = [r[f"agent{i}"] for i in range(1, 6) if r[f"agent{i}"]]
            comp_data[ch] = {
                "comp_hash": ch,
                "agents": agents,
                "roles": classify_comp(agents),
                "used": 0,
                "wins": 0,
            }
        comp_data[ch]["used"] += 1
        if r["winner_team_id"] == r["team_id"]:
            comp_data[ch]["wins"] += 1

    result = sorted(comp_data.values(), key=lambda x: x["used"], reverse=True)[:limit]
    for c in result:
        c["winrate"] = c["wins"] / c["used"] if c["used"] else 0
    return result
