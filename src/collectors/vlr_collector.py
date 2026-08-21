"""VLR.gg data collector using vlrdevapi."""

from __future__ import annotations

import hashlib
from typing import Optional

import vlrdevapi as vlr
from rich.console import Console

from src.db.connection import get_db

console = Console()


def _format_prize(prize) -> str | None:
    """Format an EventPrize into a display string, or None if TBD."""
    if prize is None or prize.amount is None:
        return None
    symbol = prize.currency_symbol or ""
    return f"{symbol}{prize.amount}"


def sync_events(tier: str = "vct", status: str | None = None, max_pages: int = 3) -> list[int]:
    """Sync VCT events into the database. Returns list of event IDs.

    vlrdevapi already fetches region='all' by default (Americas, EMEA, Pacific, China).
    If status is None, fetches only 'ongoing' and 'upcoming' (fast, for current/future events).
    Pass status='all' to include 'completed' (past events). Pass 'ongoing'/'upcoming'/'completed' to limit to one.
    """
    if status == "all":
        statuses_to_fetch = ["ongoing", "upcoming", "completed"]
    elif status:
        statuses_to_fetch = [status]
    else:
        statuses_to_fetch = ["ongoing", "upcoming"]

    all_events: list = []
    seen_ids: set[int] = set()

    for st in statuses_to_fetch:
        console.print(f"[cyan]Buscando eventos {tier} status={st} (todas as regiões)...[/cyan]")
        result = vlr.event.list(tier=tier, status=st, page=1, max_page=max_pages)
        for ev in result.events:
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
                (ev.id, ev.name, ev.region or None, tier,
                 ev.status, _format_prize(ev.prize),
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
    result = vlr.event.stages(event_id)
    if not result.stages:
        console.print("[yellow]No stages found.[/yellow]")
        return []

    stage_names = []
    with get_db() as conn:
        for s in result.stages:
            conn.execute(
                "INSERT OR IGNORE INTO stages (event_id, name) VALUES (?, ?)",
                (event_id, s.name),
            )
            stage_names.append(s.name)
            console.print(f"  [green]Stage:[/green] {s.name}")

    return stage_names


def _resolve_stage_id(event_id: int, stage_name: str) -> str | None:
    """Look up a stage's vlr.gg stage_id by its display name."""
    result = vlr.event.stages(event_id)
    for s in result.stages:
        if s.name.lower() == stage_name.lower():
            return s.id
    return None


def sync_matches(event_id: int, stage: str | None = None) -> list[int]:
    """Sync all matches for an event (optionally filtered by stage). Returns match IDs."""
    label = f"event {event_id}" + (f" stage '{stage}'" if stage else "")
    console.print(f"[cyan]Fetching matches for {label}...[/cyan]")

    stage_id = _resolve_stage_id(event_id, stage) if stage else None
    result = vlr.event.matches(event_id, stage_id=stage_id, state="all")
    if not result.matches:
        console.print("[yellow]No matches found.[/yellow]")
        return []

    match_ids = []
    with get_db() as conn:
        for m in result.matches:
            t1 = m.teams[0] if m.teams else None
            t2 = m.teams[1] if m.teams and len(m.teams) > 1 else None

            if t1 and t1.id:
                _upsert_team(conn, t1.id, t1.name)
            if t2 and t2.id:
                _upsert_team(conn, t2.id, t2.name)

            date_str = str(m.match_date) if m.match_date else None
            time_str = str(m.match_time) if m.match_time else None
            status_val = m.status.value if hasattr(m.status, "value") else str(m.status)

            conn.execute(
                """INSERT OR REPLACE INTO matches
                   (id, event_id, stage_name, phase, date, time,
                    team1_id, team2_id, score1, score2, status, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))""",
                (
                    m.match_id, event_id,
                    m.stage or stage or None,
                    m.phase or None,
                    date_str, time_str,
                    t1.id if t1 else None,
                    t2.id if t2 else None,
                    t1.score if t1 else None,
                    t2.score if t2 else None,
                    status_val,
                ),
            )
            match_ids.append(m.match_id)

    console.print(f"  [green]Synced {len(match_ids)} matches.[/green]")
    return match_ids


def sync_series_detail(match_id: int) -> bool:
    """Deep sync a single match: veto, per-map stats, rounds, compositions.
    Returns True if successful."""
    console.print(f"[cyan]Deep syncing match {match_id}...[/cyan]")

    info = vlr.series.info(match_id)
    if not info or not info.team1.id or not info.team2.id:
        console.print(f"[yellow]No series info for match {match_id}.[/yellow]")
        return False

    t1, t2 = info.team1, info.team2

    with get_db() as conn:
        _upsert_team(conn, t1.id, t1.name, tag=t1.tag or None)
        _upsert_team(conn, t2.id, t2.name, tag=t2.tag or None)

        date_str = str(info.datetime.date()) if info.datetime else None
        time_str = str(info.datetime.time()) if info.datetime else None

        conn.execute(
            """UPDATE matches SET
                bo_type = COALESCE(?, bo_type), patch = COALESCE(?, patch),
                date = COALESCE(?, date), time = COALESCE(?, time),
                status = COALESCE(?, status), updated_at = datetime('now')
               WHERE id = ?""",
            (f"bo{info.best_of}" if info.best_of else None, info.patch or None,
             date_str, time_str, info.status or None, match_id),
        )

        _sync_veto(conn, match_id, info, t1, t2)

        real_map_order = 0
        for game in info.games:
            if not game.played:
                continue
            real_map_order += 1
            _sync_single_map(conn, match_id, game, real_map_order, t1, t2)

    console.print(f"  [green]Deep sync complete for match {match_id}.[/green]")
    try:
        from src.db.outcomes import register_match_outcome
        if register_match_outcome(match_id):
            console.print(f"  [dim]Registered match outcome for {match_id}.[/dim]")
    except Exception:
        pass
    return True


def _upsert_team(conn, team_id: int | None, name: str, tag: str | None = None,
                  country: str | None = None, country_code: str | None = None) -> None:
    """Insert or update a team record."""
    if not team_id:
        return
    conn.execute(
        """INSERT INTO teams (id, name, tag, country, country_code, updated_at)
           VALUES (?, ?, ?, ?, ?, datetime('now'))
           ON CONFLICT(id) DO UPDATE SET
             name=excluded.name,
             tag=COALESCE(excluded.tag, teams.tag),
             country=COALESCE(excluded.country, teams.country),
             country_code=COALESCE(excluded.country_code, teams.country_code),
             updated_at=datetime('now')""",
        (team_id, name or "", tag, country, country_code),
    )


def _sync_veto(conn, match_id: int, info, t1, t2) -> None:
    """Sync veto (picks/bans) from series.info() into pending_vetos (source='vlr')."""
    conn.execute(
        "DELETE FROM pending_vetos WHERE match_id = ? AND source = 'vlr'",
        (match_id,),
    )
    for pick_order, v in enumerate(info.veto or [], start=1):
        team_id = _resolve_team_id(v.team, t1, t2) if v.team else None
        conn.execute(
            """INSERT OR REPLACE INTO pending_vetos
               (match_id, source, map_order, action, team_id, team_name, map_name)
               VALUES (?, 'vlr', ?, ?, ?, ?, ?)""",
            (match_id, pick_order, v.veto_type, team_id, v.team or None, v.map_name),
        )


def _resolve_team_id(label: str | None, t1, t2) -> Optional[int]:
    """Match a team tag/name (e.g. from veto or map pick) to one of the two series teams."""
    if not label:
        return None
    lbl = label.lower().strip()
    for t in (t1, t2):
        tag = (t.tag or "").lower().strip()
        name = (t.name or "").lower().strip()
        if tag and (tag == lbl or tag in lbl or lbl in tag):
            return t.id
        if name and (name in lbl or lbl in name):
            return t.id
    return None


def _sync_single_map(conn, match_id: int, game, map_order: int, t1, t2) -> None:
    """Sync a single map's data (scores, rounds, compositions, player stats)."""
    map_name = game.map_name
    game_id = str(game.game_id) if game.game_id else None

    team1_id, team2_id = t1.id, t2.id
    team1_score, team2_score = game.team1_score, game.team2_score

    is_ot = 0
    if team1_score is not None and team2_score is not None:
        is_ot = 1 if (team1_score + team2_score) > 24 else 0

    round_diff = None
    if team1_score is not None and team2_score is not None:
        round_diff = team1_score - team2_score

    winner_id = None
    if team1_score is not None and team2_score is not None:
        if team1_score > team2_score:
            winner_id = team1_id
        elif team2_score > team1_score:
            winner_id = team2_id

    pick_team_id = _resolve_team_id(game.picked_by, t1, t2) if game.picked_by else None

    rounds: list = []
    try:
        rounds_data = vlr.series.rounds(match_id, game.game_id)
        rounds = rounds_data.rounds or []
    except Exception as e:
        console.print(f"  [yellow]No round data for map {map_name} ({game.game_id}): {e}[/yellow]")

    t1_start_side = None
    t1_pistols = t2_pistols = t1_conversions = t2_conversions = 0
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
            game.team1_attack_rounds, game.team1_defense_rounds,
            game.team2_attack_rounds, game.team2_defense_rounds,
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

    _sync_rounds(conn, map_id, rounds, t1, t2)
    _sync_players_and_comps(conn, map_id, match_id, game.game_id, team1_id, team2_id)


def _normalize_side(side: str | None) -> str | None:
    """Map vlrdevapi's raw side label ('Attack'/'Defense') to the app's vocabulary
    ('Attacker'/'Defender'), which downstream code (e.g. probability.py's exact
    'attacker'/'atk' check) expects."""
    if not side:
        return None
    s = side.lower()
    if s.startswith("attack"):
        return "Attacker"
    if s.startswith("defen"):
        return "Defender"
    return side


def _derive_pistol_and_sides(rounds: list, team1_id: int | None, team2_id: int | None) -> dict:
    """Derive pistol wins, conversions, and starting side from round-by-round data."""
    result = {
        "t1_start_side": None,
        "t1_pistols": 0,
        "t2_pistols": 0,
        "t1_conversions": 0,
        "t2_conversions": 0,
    }

    round_map = {r.round_number: r for r in rounds}

    r1 = round_map.get(1)
    if r1:
        if r1.winner_team_id == team1_id:
            result["t1_start_side"] = _normalize_side(r1.side)
            result["t1_pistols"] += 1
            r2 = round_map.get(2)
            if r2 and r2.winner_team_id == team1_id:
                result["t1_conversions"] += 1
        elif r1.winner_team_id == team2_id:
            side = (r1.side or "").lower()
            if side.startswith("attack"):
                result["t1_start_side"] = "Defender"
            elif side.startswith("defen"):
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


def _sync_rounds(conn, map_id: int, rounds: list, t1, t2) -> None:
    """Insert round-by-round data."""
    conn.execute("DELETE FROM rounds WHERE map_id = ?", (map_id,))
    for r in rounds:
        winner_short = None
        if r.winner_team_id == t1.id:
            winner_short = t1.tag
        elif r.winner_team_id == t2.id:
            winner_short = t2.tag
        conn.execute(
            """INSERT OR REPLACE INTO rounds
               (map_id, round_number, winner_team_id, winner_team_short,
                winner_side, method, score_t1, score_t2)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                map_id, r.round_number, r.winner_team_id or None,
                winner_short, _normalize_side(r.side), r.win_type,
                r.team1_score, r.team2_score,
            ),
        )


def _sync_players_and_comps(conn, map_id: int, match_id: int, game_id, team1_id, team2_id) -> None:
    """Sync player stats and derive team compositions."""
    conn.execute("DELETE FROM player_map_stats WHERE map_id = ?", (map_id,))
    conn.execute("DELETE FROM map_compositions WHERE map_id = ?", (map_id,))

    try:
        stats = vlr.series.players(match_id, game_id)
    except Exception as e:
        console.print(f"  [yellow]No player stats for game {game_id}: {e}[/yellow]")
        return

    team_agents: dict[int, list[str]] = {}

    for team_players, fallback_team_id in ((stats.team1, team1_id), (stats.team2, team2_id)):
        tid = team_players.team_id or fallback_team_id
        for p in team_players.players:
            agent = p.agents[0] if p.agents else None
            o = p.stats.overall
            conn.execute(
                """INSERT OR REPLACE INTO player_map_stats
                   (map_id, player_id, player_name, team_id, agent,
                    rating, acs, kills, deaths, assists, kd_diff,
                    kast, adr, hs_pct, fk, fd, fk_diff)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    map_id, p.player_id, p.name, tid, agent,
                    o.rating, o.acs, o.kills, o.deaths, o.assists, o.kd_diff,
                    o.kast, o.adr, o.hs_percent, o.first_kills, o.first_deaths, o.fk_fd_diff,
                ),
            )
            if tid and agent:
                team_agents.setdefault(tid, []).append(agent)

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
