"""VLR.gg data collector using vlrdevapi."""

from __future__ import annotations

import hashlib
from contextlib import contextmanager
from datetime import datetime
from typing import Optional

import vlrdevapi as vlr
from rich.console import Console

from src.db.connection import get_db

console = Console()

VLR_REGION_ALL = "all"


@contextmanager
def _fetch_events_with_region_all():
    """Force region=all on events listing so we get Americas, EMEA, Pacific, China.
    Patches both the fetcher and list_events module so all code paths get the param."""
    from importlib import import_module
    fetcher_mod = import_module("vlrdevapi.fetcher")
    list_events_mod = import_module("vlrdevapi.events.list_events")
    orig_fetcher = fetcher_mod.fetch_html
    orig_list_events = list_events_mod.fetch_html

    def _patched_fetch(url: str, *args, **kwargs):
        if "/events" in url and "region=" not in url:
            url = url + ("&" if "?" in url else "?") + f"region={VLR_REGION_ALL}"
        return orig_fetcher(url, *args, **kwargs)

    fetcher_mod.clear_cache()
    fetcher_mod.fetch_html = _patched_fetch
    list_events_mod.fetch_html = _patched_fetch
    try:
        yield
    finally:
        fetcher_mod.fetch_html = orig_fetcher
        list_events_mod.fetch_html = orig_list_events


def sync_events(tier: str = "vct", status: str | None = None, limit_per_status: int = 30) -> list[int]:
    """Sync VCT events into the database. Returns list of event IDs.

    Fetches with region=all so we get Americas, EMEA, Pacific and China (not just one region).
    If status is None, fetches 'ongoing', 'upcoming' AND 'completed' so you get all campeonatos
    (incl. os que já concluíram) e todos os times do circuito para Estatísticas por time.
    Pass status='ongoing' or 'upcoming' to limit to that.
    """
    statuses_to_fetch = [status] if status else ["ongoing", "upcoming", "completed"]
    all_events: list = []
    seen_ids: set[int] = set()

    with _fetch_events_with_region_all():
        for st in statuses_to_fetch:
            console.print(f"[cyan]Buscando eventos {tier} status={st} (todas as regiões)...[/cyan]")
            events = vlr.events.list_events(tier=tier, status=st, limit=limit_per_status)
            for ev in events:
                if ev.id not in seen_ids:
                    seen_ids.add(ev.id)
                    all_events.append(ev)

    if not all_events:
        console.print("[yellow]Nenhum evento encontrado.[/yellow]")
        return []

    event_ids = []
    with get_db() as conn:
        for ev in all_events:
            conn.execute(
                """INSERT OR REPLACE INTO events
                   (id, name, region, tier, status, prize, start_date, end_date, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))""",
                (ev.id, ev.name, getattr(ev, "region", None), tier,
                 getattr(ev, "status", None), getattr(ev, "prize", None),
                 str(ev.start_date) if ev.start_date else None,
                 str(ev.end_date) if ev.end_date else None),
            )
            event_ids.append(ev.id)
            date_range = ""
            if ev.start_date or ev.end_date:
                date_range = f" ({ev.start_date} a {ev.end_date})" if ev.start_date and ev.end_date else f" ({ev.start_date or ev.end_date})"
            console.print(f"  [green]Evento:[/green] {ev.name} (ID: {ev.id}){date_range}")

    return event_ids


def sync_stages(event_id: int) -> list[str]:
    """Sync stages for an event. Returns list of stage names."""
    console.print(f"[cyan]Fetching stages for event {event_id}...[/cyan]")
    stages = vlr.events.stages(event_id)
    if not stages:
        console.print("[yellow]No stages found.[/yellow]")
        return []

    stage_names = []
    with get_db() as conn:
        for s in stages:
            name = s if isinstance(s, str) else getattr(s, "name", str(s))
            conn.execute(
                "INSERT OR IGNORE INTO stages (event_id, name) VALUES (?, ?)",
                (event_id, name),
            )
            stage_names.append(name)
            console.print(f"  [green]Stage:[/green] {name}")

    return stage_names


def sync_matches(event_id: int, stage: str | None = None) -> list[int]:
    """Sync all matches for an event (optionally filtered by stage). Returns match IDs."""
    label = f"event {event_id}" + (f" stage '{stage}'" if stage else "")
    console.print(f"[cyan]Fetching matches for {label}...[/cyan]")

    matches = vlr.events.matches(event_id, stage=stage)
    if not matches:
        console.print("[yellow]No matches found.[/yellow]")
        return []

    match_ids = []
    with get_db() as conn:
        for m in matches:
            t1 = m.teams[0] if m.teams else None
            t2 = m.teams[1] if m.teams and len(m.teams) > 1 else None

            if t1 and t1.id:
                _upsert_team(conn, t1)
            if t2 and t2.id:
                _upsert_team(conn, t2)

            date_str = str(m.date) if m.date else None
            time_str = getattr(m, "time", None)

            conn.execute(
                """INSERT OR REPLACE INTO matches
                   (id, event_id, stage_name, phase, date, time,
                    team1_id, team2_id, score1, score2, status, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))""",
                (
                    m.match_id, event_id,
                    getattr(m, "stage", stage),
                    getattr(m, "phase", None),
                    date_str, str(time_str) if time_str else None,
                    t1.id if t1 else None,
                    t2.id if t2 else None,
                    t1.score if t1 else None,
                    t2.score if t2 else None,
                    m.status,
                ),
            )
            match_ids.append(m.match_id)

    console.print(f"  [green]Synced {len(match_ids)} matches.[/green]")
    return match_ids


def sync_series_detail(match_id: int) -> bool:
    """Deep sync a single match: picks/bans, per-map stats, rounds, compositions.
    Returns True if successful."""
    console.print(f"[cyan]Deep syncing match {match_id}...[/cyan]")

    info = vlr.series.info(match_id=match_id)
    if not info:
        console.print(f"[yellow]No series info for match {match_id}.[/yellow]")
        return False

    with get_db() as conn:
        t1 = info.teams[0]
        t2 = info.teams[1]
        if t1.id:
            _upsert_team(conn, t1)
        if t2.id:
            _upsert_team(conn, t2)

        date_str = str(info.date) if info.date else None
        time_str = str(info.time) if info.time else None

        conn.execute(
            """UPDATE matches SET
                bo_type = ?, patch = ?, date = COALESCE(?, date),
                time = COALESCE(?, time), updated_at = datetime('now')
               WHERE id = ?""",
            (info.best_of, info.patch, date_str, time_str, match_id),
        )

        _sync_picks_bans(conn, match_id, info, t1, t2)

        map_data_list = vlr.series.matches(series_id=match_id)
        if not map_data_list:
            console.print(f"[yellow]No map data for match {match_id}.[/yellow]")
            return True

        pick_map = _build_pick_map(info)

        real_map_order = 0
        for map_data in map_data_list:
            if map_data.map_name and map_data.map_name.lower() == "all":
                continue
            real_map_order += 1

            _sync_single_map(
                conn, match_id, map_data, real_map_order,
                t1, t2, pick_map,
            )

    console.print(f"  [green]Deep sync complete for match {match_id}.[/green]")
    return True


def _upsert_team(conn, team_obj) -> None:
    """Insert or update a team record."""
    tid = getattr(team_obj, "id", None) or getattr(team_obj, "team_id", None)
    if not tid:
        return
    name = getattr(team_obj, "name", "")
    tag = getattr(team_obj, "short", None) or getattr(team_obj, "tag", None)
    country = getattr(team_obj, "country", None)
    cc = getattr(team_obj, "country_code", None)
    conn.execute(
        """INSERT INTO teams (id, name, tag, country, country_code, updated_at)
           VALUES (?, ?, ?, ?, ?, datetime('now'))
           ON CONFLICT(id) DO UPDATE SET
             name=excluded.name,
             tag=COALESCE(excluded.tag, teams.tag),
             country=COALESCE(excluded.country, teams.country),
             country_code=COALESCE(excluded.country_code, teams.country_code),
             updated_at=datetime('now')""",
        (tid, name, tag, country, cc),
    )


def _sync_picks_bans(conn, match_id: int, info, t1, t2) -> None:
    """Sync veto (picks/bans) from series.info() into pending_vetos (source='vlr')."""
    conn.execute(
        "DELETE FROM pending_vetos WHERE match_id = ? AND source = 'vlr'",
        (match_id,),
    )

    all_actions = info.map_actions if info.map_actions else []
    pick_order = 0
    for action_obj in all_actions:
        pick_order += 1
        team_name = action_obj.team
        team_id = _resolve_team_id(team_name, t1, t2)
        conn.execute(
            """INSERT OR REPLACE INTO pending_vetos
               (match_id, source, map_order, action, team_id, team_name, map_name)
               VALUES (?, 'vlr', ?, ?, ?, ?, ?)""",
            (match_id, pick_order, action_obj.action, team_id, team_name, action_obj.map),
        )

    if info.remaining:
        pick_order += 1
        conn.execute(
            """INSERT OR REPLACE INTO pending_vetos
               (match_id, source, map_order, action, team_name, map_name)
               VALUES (?, 'vlr', ?, 'decider', NULL, ?)""",
            (match_id, pick_order, info.remaining),
        )


def _resolve_team_id(team_name: str, t1, t2) -> Optional[int]:
    """Try to match a team name from veto to one of the two teams."""
    if not team_name:
        return None
    tn = team_name.lower().strip()
    for t in (t1, t2):
        t_name = (t.name or "").lower().strip()
        t_short = (t.short or "").lower().strip()
        if t_name and (t_name in tn or tn in t_name):
            return t.id
        if t_short and (t_short in tn or tn in t_short):
            return t.id
    return None


def _build_pick_map(info) -> dict[str, int | None]:
    """Build a dict of map_name -> picking_team_id from picks."""
    result: dict[str, int | None] = {}
    t1, t2 = info.teams
    for p in (info.picks or []):
        tid = _resolve_team_id(p.team, t1, t2)
        result[p.map.lower()] = tid
    return result


def _sync_single_map(conn, match_id: int, map_data, map_order: int, t1, t2, pick_map: dict) -> None:
    """Sync a single map's data (scores, rounds, compositions, player stats)."""
    map_name = map_data.map_name
    game_id = str(map_data.game_id) if map_data.game_id else None

    mt1, mt2 = (None, None)
    if map_data.teams:
        mt1, mt2 = map_data.teams

    team1_id = mt1.id if mt1 and mt1.id else (t1.id if t1 else None)
    team2_id = mt2.id if mt2 and mt2.id else (t2.id if t2 else None)
    team1_score = mt1.score if mt1 else None
    team2_score = mt2.score if mt2 else None
    t1_atk = mt1.attacker_rounds if mt1 else None
    t1_def = mt1.defender_rounds if mt1 else None
    t2_atk = mt2.attacker_rounds if mt2 else None
    t2_def = mt2.defender_rounds if mt2 else None

    is_ot = 0
    if team1_score is not None and team2_score is not None:
        is_ot = 1 if (team1_score + team2_score) > 24 else 0

    round_diff = None
    if team1_score is not None and team2_score is not None:
        round_diff = team1_score - team2_score

    winner_id = None
    if mt1 and mt1.is_winner:
        winner_id = team1_id
    elif mt2 and mt2.is_winner:
        winner_id = team2_id

    pick_team_id = pick_map.get((map_name or "").lower())

    rounds = map_data.rounds or []
    t1_start_side = None
    t1_pistols = 0
    t2_pistols = 0
    t1_conversions = 0
    t2_conversions = 0

    if rounds:
        pistol_info = _derive_pistol_and_sides(rounds, team1_id, team2_id)
        t1_start_side = pistol_info["t1_start_side"]
        t1_pistols = pistol_info["t1_pistols"]
        t2_pistols = pistol_info["t2_pistols"]
        t1_conversions = pistol_info["t1_conversions"]
        t2_conversions = pistol_info["t2_conversions"]

    conn.execute(
        """INSERT INTO maps
           (match_id, game_id, map_name, map_order, pick_team_id,
            team1_id, team2_id, team1_score, team2_score,
            team1_atk_rounds, team1_def_rounds, team2_atk_rounds, team2_def_rounds,
            team1_start_side, team1_pistols_won, team2_pistols_won,
            team1_pistol_conversions, team2_pistol_conversions,
            is_ot, round_diff, winner_team_id)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(match_id, game_id) DO UPDATE SET
             map_name=excluded.map_name, map_order=excluded.map_order,
             pick_team_id=excluded.pick_team_id,
             team1_id=excluded.team1_id, team2_id=excluded.team2_id,
             team1_score=excluded.team1_score, team2_score=excluded.team2_score,
             team1_atk_rounds=excluded.team1_atk_rounds, team1_def_rounds=excluded.team1_def_rounds,
             team2_atk_rounds=excluded.team2_atk_rounds, team2_def_rounds=excluded.team2_def_rounds,
             team1_start_side=excluded.team1_start_side,
             team1_pistols_won=excluded.team1_pistols_won, team2_pistols_won=excluded.team2_pistols_won,
             team1_pistol_conversions=excluded.team1_pistol_conversions,
             team2_pistol_conversions=excluded.team2_pistol_conversions,
             is_ot=excluded.is_ot, round_diff=excluded.round_diff,
             winner_team_id=excluded.winner_team_id""",
        (
            match_id, game_id, map_name, map_order, pick_team_id,
            team1_id, team2_id, team1_score, team2_score,
            t1_atk, t1_def, t2_atk, t2_def,
            t1_start_side, t1_pistols, t2_pistols,
            t1_conversions, t2_conversions,
            is_ot, round_diff, winner_id,
        ),
    )

    if t1_start_side and map_name:
        pick_side = t1_start_side
        if pick_team_id != team1_id and pick_team_id is not None and team1_id is not None:
            pick_side = "Defender" if ("attack" in (t1_start_side or "").lower()) else "Attacker"
        conn.execute(
            """UPDATE pending_vetos SET start_side = ?
               WHERE match_id = ? AND LOWER(TRIM(map_name)) = LOWER(TRIM(?)) AND source = 'vlr'""",
            (pick_side, match_id, map_name),
        )

    row = conn.execute(
        "SELECT id FROM maps WHERE match_id = ? AND game_id = ?",
        (match_id, game_id),
    ).fetchone()
    if not row:
        return
    map_id = row["id"]

    _sync_rounds(conn, map_id, rounds)

    mt1_short = mt1.short if mt1 else (t1.short if hasattr(t1, 'short') else None)
    mt2_short = mt2.short if mt2 else (t2.short if hasattr(t2, 'short') else None)
    _sync_players_and_comps(conn, map_id, map_data.players, team1_id, team2_id,
                            mt1_short=mt1_short, mt2_short=mt2_short)


def _derive_pistol_and_sides(rounds: list, team1_id: int | None, team2_id: int | None) -> dict:
    """Derive pistol wins, conversions, and starting side from round-by-round data."""
    result = {
        "t1_start_side": None,
        "t1_pistols": 0,
        "t2_pistols": 0,
        "t1_conversions": 0,
        "t2_conversions": 0,
    }

    round_map = {r.number: r for r in rounds}

    r1 = round_map.get(1)
    if r1:
        if r1.winner_team_id == team1_id:
            result["t1_start_side"] = r1.winner_side
            result["t1_pistols"] += 1
            r2 = round_map.get(2)
            if r2 and r2.winner_team_id == team1_id:
                result["t1_conversions"] += 1
        elif r1.winner_team_id == team2_id:
            if r1.winner_side == "Attacker":
                result["t1_start_side"] = "Defender"
            elif r1.winner_side == "Defender":
                result["t1_start_side"] = "Attacker"
            result["t2_pistols"] += 1
            r2 = round_map.get(2)
            if r2 and r2.winner_team_id == team2_id:
                result["t2_conversions"] += 1

    r13 = round_map.get(13)
    if r13:
        if r13.winner_team_id == team1_id:
            result["t1_pistols"] += 1
            r14 = round_map.get(14)
            if r14 and r14.winner_team_id == team1_id:
                result["t1_conversions"] += 1
        elif r13.winner_team_id == team2_id:
            result["t2_pistols"] += 1
            r14 = round_map.get(14)
            if r14 and r14.winner_team_id == team2_id:
                result["t2_conversions"] += 1

    return result


def _sync_rounds(conn, map_id: int, rounds: list) -> None:
    """Insert round-by-round data."""
    conn.execute("DELETE FROM rounds WHERE map_id = ?", (map_id,))
    for r in rounds:
        score = r.score if r.score else (None, None)
        conn.execute(
            """INSERT OR REPLACE INTO rounds
               (map_id, round_number, winner_team_id, winner_team_short,
                winner_side, method, score_t1, score_t2)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                map_id, r.number, r.winner_team_id,
                r.winner_team_short, r.winner_side, r.method,
                score[0] if score else None,
                score[1] if score else None,
            ),
        )


def _sync_players_and_comps(conn, map_id: int, players: list, team1_id, team2_id,
                            mt1_short: str | None = None, mt2_short: str | None = None) -> None:
    """Sync player stats and derive team compositions."""
    conn.execute("DELETE FROM player_map_stats WHERE map_id = ?", (map_id,))
    conn.execute("DELETE FROM map_compositions WHERE map_id = ?", (map_id,))

    short_to_id: dict[str, int] = {}
    if mt1_short and team1_id:
        short_to_id[mt1_short.upper()] = team1_id
    if mt2_short and team2_id:
        short_to_id[mt2_short.upper()] = team2_id

    team_agents: dict[int, list[str]] = {}

    for p in players:
        agent = p.agents[0] if p.agents else None
        player_team_id = p.team_id

        if not player_team_id and p.team_short:
            player_team_id = short_to_id.get(p.team_short.upper())

        conn.execute(
            """INSERT OR REPLACE INTO player_map_stats
               (map_id, player_id, player_name, team_id, agent,
                rating, acs, kills, deaths, assists, kd_diff,
                kast, adr, hs_pct, fk, fd, fk_diff)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                map_id, p.player_id, p.name, player_team_id, agent,
                p.r, p.acs, p.k, p.d, p.a, p.kd_diff,
                p.kast, p.adr, p.hs_pct, p.fk, p.fd, p.fk_diff,
            ),
        )

        if player_team_id and agent:
            team_agents.setdefault(player_team_id, []).append(agent)

    for tid, agents in team_agents.items():
        sorted_agents = sorted(agents)[:5]
        while len(sorted_agents) < 5:
            sorted_agents.append(None)
        comp_hash = hashlib.md5("|".join(a or "" for a in sorted_agents).encode()).hexdigest()[:12]
        conn.execute(
            """INSERT OR REPLACE INTO map_compositions
               (map_id, team_id, agent1, agent2, agent3, agent4, agent5, comp_hash)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (map_id, tid, *sorted_agents, comp_hash),
        )


def full_sync(event_id: int | None = None, deep: bool = True, event_status: str | None = None) -> None:
    """Full sync pipeline: events -> stages -> matches -> (optionally) deep series data.

    event_status: None = ongoing + upcoming (default). Use 'all' or 'completed' to include past events.
    """
    if event_id:
        event_ids = [event_id]
        with get_db() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO events (id, name) VALUES (?, ?)",
                (event_id, f"Event {event_id}"),
            )
    else:
        event_ids = sync_events(status=event_status)

    if not event_ids:
        console.print("[red]No events to sync.[/red]")
        return

    for eid in event_ids:
        stages = sync_stages(eid)
        match_ids = sync_matches(eid)

        if deep:
            completed = []
            with get_db() as conn:
                rows = conn.execute(
                    "SELECT id, status FROM matches WHERE event_id = ? AND status = 'completed'",
                    (eid,),
                ).fetchall()
                completed = [r["id"] for r in rows]

            console.print(f"[cyan]Deep syncing {len(completed)} completed matches...[/cyan]")
            for mid in completed:
                try:
                    sync_series_detail(mid)
                except Exception as e:
                    console.print(f"  [red]Error syncing match {mid}: {e}[/red]")
