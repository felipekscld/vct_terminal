"""Natural language stat query engine.

Parses questions in Portuguese/English about teams, maps, and stats,
then queries the DB and returns formatted answers.
"""

from __future__ import annotations

import re
from typing import Optional

from InquirerPy import inquirer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from src.config import config
from src.db.connection import get_db
from src.ui.styles import VCT_THEME

console = Console(theme=VCT_THEME)

STAT_KEYWORDS = {
    "ot": "ot",
    "overtime": "ot",
    "pistol": "pistol",
    "pistols": "pistol",
    "winrate": "winrate",
    "win rate": "winrate",
    "taxa de vitoria": "winrate",
    "placar": "scores",
    "placares": "scores",
    "score": "scores",
    "scores": "scores",
    "resultado": "scores",
    "resultados": "scores",
    "close": "close",
    "apertado": "close",
    "apertados": "close",
    "stomp": "stomp",
    "stomps": "stomp",
    "atk": "sides",
    "def": "sides",
    "attack": "sides",
    "defense": "sides",
    "lado": "sides",
    "sides": "sides",
    "comp": "comp",
    "composicao": "comp",
    "composicoes": "comp",
    "agents": "comp",
    "agentes": "comp",
    "h2h": "h2h",
    "head to head": "h2h",
    "historico": "h2h",
    "stats": "overview",
    "estatisticas": "overview",
    "overview": "overview",
    "geral": "overview",
    "round": "rounds",
    "rounds": "rounds",
}


def run_query_loop(context: dict | None = None):
    """Interactive query loop. Type questions, get answers."""
    console.print("\n[bold cyan]Consultar Estatisticas[/bold cyan]")
    console.print("[dim]Pergunte em PT ou EN. Ex: 'ot MIBR', 'pistol NRG Abyss', 'h2h FURIA G2'[/dim]")
    console.print("[dim]Digite 'sair' para voltar.[/dim]\n")

    while True:
        query = inquirer.text(message="Pergunta:").execute()
        if query.lower().strip() in ("sair", "exit", "back", "voltar", "q"):
            break
        if not query.strip():
            continue

        try:
            answer = process_query(query, context)
            if answer:
                console.print(answer)
            else:
                console.print("[yellow]Nao entendi a pergunta. Tente: 'ot MIBR', 'pistol NRG Abyss', 'h2h FURIA G2'[/yellow]")
        except Exception as e:
            console.print(f"[red]Erro: {e}[/red]")

        console.print()


def process_query(query: str, context: dict | None = None) -> Optional[str | Panel | Table]:
    """Parse a query and return a formatted answer."""
    q = query.lower().strip()

    stat_type = None
    for keyword, stype in STAT_KEYWORDS.items():
        if keyword in q:
            stat_type = stype
            break

    teams = _find_teams(q, context)
    map_name = _find_map(q)

    if not stat_type and not teams:
        return None

    if not stat_type and teams:
        stat_type = "overview"

    if stat_type == "ot":
        return _query_ot(teams, map_name)
    elif stat_type == "pistol":
        return _query_pistol(teams, map_name)
    elif stat_type == "winrate":
        return _query_winrate(teams, map_name)
    elif stat_type == "scores":
        return _query_scores(teams, map_name)
    elif stat_type == "close":
        return _query_close(teams, map_name)
    elif stat_type == "sides":
        return _query_sides(teams, map_name)
    elif stat_type == "comp":
        return _query_comps(teams, map_name)
    elif stat_type == "h2h":
        return _query_h2h(teams, map_name)
    elif stat_type == "overview":
        return _query_overview(teams, map_name)
    elif stat_type == "rounds":
        return _query_rounds(teams, map_name)

    return None



def _query_ot(teams: list[dict], map_name: str | None) -> Panel:
    filt = config.data_filter
    lines = []
    for t in teams:
        with get_db() as conn:
            conds = ["(m.team1_id = ? OR m.team2_id = ?)", "m.team1_score IS NOT NULL"]
            params: list = [t["id"], t["id"]]
            fc, fp = filt.build_sql_conditions("mt")
            conds.extend(fc)
            params.extend(fp)
            if map_name:
                conds.append("m.map_name = ?")
                params.append(map_name)
            where = " AND ".join(conds)
            rows = conn.execute(
                f"SELECT m.* FROM maps m JOIN matches mt ON m.match_id = mt.id WHERE {where}",
                params,
            ).fetchall()

        total = len(rows)
        ots = sum(1 for r in rows if r["is_ot"])
        map_label = f" em {map_name}" if map_name else ""
        lines.append(f"[bold]{t['name']}[/bold]{map_label}: {ots} OTs em {total} mapas ({ots/total:.0%})" if total else f"[bold]{t['name']}[/bold]{map_label}: sem dados")

        if total and not map_name:
            map_breakdown = {}
            for r in rows:
                mn = r["map_name"] or "?"
                map_breakdown.setdefault(mn, {"total": 0, "ot": 0})
                map_breakdown[mn]["total"] += 1
                if r["is_ot"]:
                    map_breakdown[mn]["ot"] += 1
            for mn, data in sorted(map_breakdown.items()):
                if data["ot"] > 0:
                    lines.append(f"  {mn}: {data['ot']}/{data['total']} OTs")

    return Panel("\n".join(lines), title="Overtime Stats", border_style="cyan")


def _query_pistol(teams: list[dict], map_name: str | None) -> Panel:
    filt = config.data_filter
    lines = []
    for t in teams:
        with get_db() as conn:
            conds = ["(m.team1_id = ? OR m.team2_id = ?)", "m.team1_score IS NOT NULL"]
            params: list = [t["id"], t["id"]]
            fc, fp = filt.build_sql_conditions("mt")
            conds.extend(fc)
            params.extend(fp)
            if map_name:
                conds.append("m.map_name = ?")
                params.append(map_name)
            where = " AND ".join(conds)
            rows = conn.execute(
                f"SELECT m.* FROM maps m JOIN matches mt ON m.match_id = mt.id WHERE {where}",
                params,
            ).fetchall()

        total_pistols = 0
        won_pistols = 0
        conversions = 0
        for r in rows:
            is_t1 = r["team1_id"] == t["id"]
            pw = r["team1_pistols_won"] if is_t1 else r["team2_pistols_won"]
            pc = r["team1_pistol_conversions"] if is_t1 else r["team2_pistol_conversions"]
            total_pistols += 2
            won_pistols += pw or 0
            conversions += pc or 0

        map_label = f" em {map_name}" if map_name else ""
        rate = won_pistols / total_pistols if total_pistols else 0
        conv_rate = conversions / won_pistols if won_pistols else 0
        lines.append(
            f"[bold]{t['name']}[/bold]{map_label}: "
            f"{won_pistols}/{total_pistols} pistols ganhos ({rate:.0%}) | "
            f"Conversao: {conversions}/{won_pistols} ({conv_rate:.0%})"
        )

    return Panel("\n".join(lines), title="Pistol Stats", border_style="cyan")


def _query_winrate(teams: list[dict], map_name: str | None) -> Table:
    from src.analysis.maps import get_team_map_stats
    from src.config import VALORANT_MAP_POOL

    maps = [map_name] if map_name else VALORANT_MAP_POOL
    table = Table(title="Win Rates", show_header=True)
    table.add_column("Time")
    for mn in maps:
        table.add_column(mn, justify="center")

    for t in teams:
        row = [f"[bold]{t['name']}[/bold]"]
        for mn in maps:
            stats = get_team_map_stats(t["id"], mn)
            if stats.games_played:
                row.append(f"{stats.winrate:.0%} ({stats.games_played})")
            else:
                row.append("-")
        table.add_row(*row)

    return table


def _query_scores(teams: list[dict], map_name: str | None) -> Table:
    filt = config.data_filter
    table = Table(title="Placares Recentes", show_header=True)
    table.add_column("Data")
    table.add_column("Mapa")
    table.add_column("Time")
    table.add_column("Placar")
    table.add_column("OT")

    for t in teams:
        with get_db() as conn:
            conds = ["(m.team1_id = ? OR m.team2_id = ?)", "m.team1_score IS NOT NULL"]
            params: list = [t["id"], t["id"]]
            fc, fp = filt.build_sql_conditions("mt")
            conds.extend(fc)
            params.extend(fp)
            if map_name:
                conds.append("m.map_name = ?")
                params.append(map_name)
            where = " AND ".join(conds)
            rows = conn.execute(
                f"""SELECT m.*, mt.date, t1.name as t1n, t2.name as t2n
                    FROM maps m JOIN matches mt ON m.match_id = mt.id
                    LEFT JOIN teams t1 ON m.team1_id = t1.id
                    LEFT JOIN teams t2 ON m.team2_id = t2.id
                    WHERE {where} ORDER BY mt.date DESC LIMIT 15""",
                params,
            ).fetchall()

        for r in rows:
            score = f"{r['team1_score']}-{r['team2_score']}"
            winner = r["t1n"] if r["winner_team_id"] == r["team1_id"] else r["t2n"]
            ot = "SIM" if r["is_ot"] else ""
            matchup = f"{r['t1n']} vs {r['t2n']}"
            table.add_row(r["date"] or "?", r["map_name"] or "?", matchup, score, ot)

    return table


def _query_close(teams: list[dict], map_name: str | None) -> Panel:
    from src.analysis.maps import get_team_map_stats
    lines = []
    for t in teams:
        if map_name:
            stats = get_team_map_stats(t["id"], map_name)
            lines.append(f"[bold]{t['name']}[/bold] em {map_name}: {stats.close_maps}/{stats.games_played} mapas apertados ({stats.close_rate:.0%})")
        else:
            total_games = 0
            total_close = 0
            from src.config import VALORANT_MAP_POOL
            for mn in VALORANT_MAP_POOL:
                stats = get_team_map_stats(t["id"], mn)
                total_games += stats.games_played
                total_close += stats.close_maps
            rate = total_close / total_games if total_games else 0
            lines.append(f"[bold]{t['name']}[/bold]: {total_close}/{total_games} mapas apertados ({rate:.0%})")

    return Panel("\n".join(lines), title="Close Maps", border_style="cyan")


def _query_sides(teams: list[dict], map_name: str | None) -> Table:
    from src.analysis.maps import get_team_map_stats
    from src.config import VALORANT_MAP_POOL

    maps = [map_name] if map_name else VALORANT_MAP_POOL
    table = Table(title="ATK/DEF Performance", show_header=True)
    table.add_column("Time")
    table.add_column("Mapa")
    table.add_column("ATK WR")
    table.add_column("DEF WR")

    for t in teams:
        for mn in maps:
            stats = get_team_map_stats(t["id"], mn)
            if stats.games_played:
                table.add_row(
                    t["name"], mn,
                    f"{stats.atk_round_rate:.0%}", f"{stats.def_round_rate:.0%}",
                )

    return table


def _query_comps(teams: list[dict], map_name: str | None) -> Panel:
    from src.analysis.compositions import get_team_likely_comp
    from src.config import VALORANT_MAP_POOL

    maps = [map_name] if map_name else VALORANT_MAP_POOL
    lines = []
    for t in teams:
        lines.append(f"[bold]{t['name']}[/bold]")
        for mn in maps:
            comps = get_team_likely_comp(t["id"], mn, limit=2)
            if comps:
                for c in comps:
                    agents = ", ".join(c["agents"])
                    lines.append(f"  {mn}: {agents} ({c['used']}x, WR {c['winrate']:.0%})")
        lines.append("")

    return Panel("\n".join(lines), title="Composicoes", border_style="cyan")


def _query_h2h(teams: list[dict], map_name: str | None) -> Panel:
    from src.analysis.maps import get_h2h_stats
    if len(teams) < 2:
        return Panel("[yellow]Preciso de 2 times para H2H. Ex: 'h2h MIBR NRG'[/yellow]", border_style="yellow")

    h2h = get_h2h_stats(teams[0]["id"], teams[1]["id"], map_name=map_name)
    map_label = f" em {map_name}" if map_name else ""
    lines = [
        f"[bold]{teams[0]['name']} vs {teams[1]['name']}[/bold]{map_label}",
        f"  Mapas jogados: {h2h['total_maps']}",
        f"  {teams[0]['name']}: {h2h['a_wins']} vitoria(s)",
        f"  {teams[1]['name']}: {h2h['b_wins']} vitoria(s)",
        f"  OTs: {h2h['ot_count']} ({h2h['ot_rate']:.0%})",
    ]
    return Panel("\n".join(lines), title="Head to Head", border_style="cyan")


def _query_overview(teams: list[dict], map_name: str | None) -> Panel:
    from src.analysis.maps import get_team_map_stats
    from src.config import VALORANT_MAP_POOL

    maps = [map_name] if map_name else VALORANT_MAP_POOL
    lines = []
    for t in teams:
        lines.append(f"[bold]{t['name']}[/bold]")
        for mn in maps:
            s = get_team_map_stats(t["id"], mn)
            if s.games_played:
                lines.append(
                    f"  {mn}: {s.wins}W-{s.losses}L ({s.winrate:.0%}) | "
                    f"ATK {s.atk_round_rate:.0%} DEF {s.def_round_rate:.0%} | "
                    f"Pistol {s.pistol_rate:.0%} | OT {s.ot_rate:.0%} | "
                    f"RD {s.avg_round_diff:+.1f}"
                )
        lines.append("")

    return Panel("\n".join(lines), title="Overview", border_style="cyan")


def _query_rounds(teams: list[dict], map_name: str | None) -> Panel:
    from src.analysis.maps import get_team_map_stats, get_global_map_stats
    from src.config import VALORANT_MAP_POOL

    maps = [map_name] if map_name else VALORANT_MAP_POOL
    lines = []

    if not teams:
        for mn in maps:
            gs = get_global_map_stats(mn)
            if gs["total_maps"]:
                lines.append(f"  {mn}: avg {gs['avg_total_rounds']:.1f} rounds/mapa ({gs['total_maps']} mapas)")
    else:
        for t in teams:
            lines.append(f"[bold]{t['name']}[/bold]")
            for mn in maps:
                s = get_team_map_stats(t["id"], mn)
                if s.games_played:
                    lines.append(
                        f"  {mn}: avg {s.avg_rounds_won:.1f} ganhos, {s.avg_rounds_lost:.1f} perdidos "
                        f"(diff {s.avg_round_diff:+.1f})"
                    )
            lines.append("")

    return Panel("\n".join(lines), title="Rounds", border_style="cyan")



def _find_teams(query: str, context: dict | None = None) -> list[dict]:
    """Find team names mentioned in the query."""
    with get_db() as conn:
        all_teams = conn.execute("SELECT id, name, tag FROM teams").fetchall()

    found = []
    q_lower = query.lower()

    for t in all_teams:
        name_lower = (t["name"] or "").lower()
        tag_lower = (t["tag"] or "").lower()
        if name_lower and (name_lower in q_lower or q_lower in name_lower):
            found.append({"id": t["id"], "name": t["name"]})
        elif tag_lower and len(tag_lower) >= 2 and tag_lower in q_lower:
            found.append({"id": t["id"], "name": t["name"]})

    if not found and context:
        if context.get("team_a_id") and context.get("team_b_id"):
            found = [
                {"id": context["team_a_id"], "name": context.get("team_a", "Team A")},
                {"id": context["team_b_id"], "name": context.get("team_b", "Team B")},
            ]

    seen = set()
    unique = []
    for t in found:
        if t["id"] not in seen:
            seen.add(t["id"])
            unique.append(t)

    return unique


def _find_map(query: str) -> Optional[str]:
    """Find a map name in the query."""
    from src.config import VALORANT_MAP_POOL
    q_lower = query.lower()
    for m in VALORANT_MAP_POOL:
        if m.lower() in q_lower:
            return m
    return None
