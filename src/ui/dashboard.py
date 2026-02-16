"""Main Rich dashboard layout for the VCT +EV Terminal."""

from __future__ import annotations

from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from src.config import config
from src.db.connection import get_db
from src.ui.styles import VCT_THEME

console = Console(theme=VCT_THEME)


def render_dashboard() -> None:
    """Render the main dashboard with match list and overview."""
    console.clear()
    console.print()

    filt = config.data_filter
    filter_text = f"[filter_active]{filt.description}[/filter_active]" if filt.is_active else "[warning]sem filtro[/warning]"
    console.print(Panel(
        f"[header] VCT +EV Terminal [/header]  |  Filtro: {filter_text}",
        border_style="bright_red",
    ))

    matches_table = _build_matches_table()
    console.print(Panel(matches_table, title="Matches", border_style="panel_border"))

    stats = _build_quick_stats()
    if stats:
        console.print(Panel(stats, title="DB Overview", border_style="panel_border"))

    b = config.bankroll
    console.print(Panel(
        f"[bankroll]Bankroll: R${b.total:.0f}[/bankroll] | "
        f"Max stake/bet: R${b.total * b.max_stake_pct:.0f} | "
        f"Kelly: {b.kelly_fraction:.0%}",
        border_style="panel_border",
    ))

    console.print()
    console.print("[dim]Use 'vct analyze <match_id>' to analyze a match.[/dim]")
    console.print("[dim]Use 'vct filter --events 2682 2700' to set data filters.[/dim]")


def _build_matches_table() -> Table:
    """Build the table of upcoming/recent matches."""
    table = Table(show_header=True, header_style="bold", expand=True)
    table.add_column("ID", width=8)
    table.add_column("Match")
    table.add_column("Event")
    table.add_column("Stage")
    table.add_column("Format")
    table.add_column("Date")
    table.add_column("Status")
    table.add_column("Score")

    with get_db() as conn:
        filt = config.data_filter
        conditions = ["1=1"]
        params: list = []

        filter_conds, filter_params = filt.build_sql_conditions("m")
        conditions.extend(filter_conds)
        params.extend(filter_params)

        where = " AND ".join(conditions)

        rows = conn.execute(
            f"""SELECT m.id, m.date, m.status, m.bo_type, m.score1, m.score2,
                       m.stage_name, m.phase,
                       t1.name as t1_name, t2.name as t2_name,
                       e.name as event_name
                FROM matches m
                LEFT JOIN teams t1 ON m.team1_id = t1.id
                LEFT JOIN teams t2 ON m.team2_id = t2.id
                LEFT JOIN events e ON m.event_id = e.id
                WHERE {where}
                ORDER BY
                    CASE m.status
                        WHEN 'ongoing' THEN 0
                        WHEN 'upcoming' THEN 1
                        ELSE 2
                    END,
                    m.date DESC
                LIMIT 25""",
            params,
        ).fetchall()

    for r in rows:
        match_str = f"{r['t1_name'] or '?'} vs {r['t2_name'] or '?'}"
        score = ""
        if r["score1"] is not None and r["score2"] is not None:
            score = f"{r['score1']}-{r['score2']}"

        status_style = "green" if r["status"] == "completed" else \
                       "yellow" if r["status"] == "upcoming" else "cyan"

        table.add_row(
            str(r["id"]),
            match_str,
            r["event_name"] or "",
            r["stage_name"] or "",
            r["bo_type"] or "",
            r["date"] or "",
            f"[{status_style}]{r['status'] or ''}[/{status_style}]",
            score,
        )

    return table


def _build_quick_stats() -> str:
    """Quick DB overview stats."""
    with get_db() as conn:
        events_count = conn.execute("SELECT COUNT(*) as c FROM events").fetchone()["c"]
        matches_count = conn.execute("SELECT COUNT(*) as c FROM matches").fetchone()["c"]
        maps_count = conn.execute("SELECT COUNT(*) as c FROM maps WHERE team1_score IS NOT NULL").fetchone()["c"]
        odds_count = conn.execute("SELECT COUNT(*) as c FROM odds_snapshots").fetchone()["c"]
        comps_count = conn.execute("SELECT COUNT(DISTINCT comp_hash) as c FROM map_compositions").fetchone()["c"]

    return (
        f"Events: {events_count} | "
        f"Matches: {matches_count} | "
        f"Maps played: {maps_count} | "
        f"Compositions: {comps_count} | "
        f"Odds snapshots: {odds_count}"
    )
