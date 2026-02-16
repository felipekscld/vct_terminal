"""Live / in-play analysis during a match.

Key difference: Betano supports live Valorant betting, Bet365 does NOT.
This module handles:
- Inputting map results as they happen
- Recalculating series probabilities with updated info
- Showing which bets are still available on which platform
- Hedge opportunities mid-series
"""

from __future__ import annotations

from InquirerPy import inquirer
from InquirerPy.separator import Separator
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from src.config import config
from src.db.connection import get_db
from src.analysis.probability import simulate_series
from src.analysis.multibets import hedge_calculator
from src.ui.styles import VCT_THEME

console = Console(theme=VCT_THEME)


def live_analysis_menu(match_id: int, info: dict):
    """Live analysis flow during a match."""
    t1 = info.get("t1_name", "Team A")
    t2 = info.get("t2_name", "Team B")
    bo_type = info.get("bo_type", "bo3")
    maps_to_win = 3 if "5" in str(bo_type) else 2

    console.print(f"\n[bold cyan]Live Analysis — {t1} vs {t2} ({bo_type})[/bold cyan]")
    console.print(Panel(
        f"[odds.betano]Betano[/odds.betano]: aceita apostas AO VIVO durante a partida\n"
        f"[odds.bet365]Bet365[/odds.bet365]: NAO aceita apostas ao vivo em Valorant\n\n"
        f"[dim]Isso significa que odds live so estao disponiveis na Betano.[/dim]\n"
        f"[dim]Se voce apostou pre-match na Bet365, pode hedgear ao vivo na Betano.[/dim]",
        title="Plataformas Live",
        border_style="yellow",
    ))

    map_results: list[dict] = []
    a_score = 0
    b_score = 0

    veto_maps = _get_veto_map_names(match_id, bo_type)

    while True:
        status_str = f"  Placar atual: {t1} {a_score} - {b_score} {t2}"
        if a_score == maps_to_win:
            status_str += f"  [green]{t1} venceu a serie![/green]"
        elif b_score == maps_to_win:
            status_str += f"  [green]{t2} venceu a serie![/green]"

        console.print(f"\n{status_str}")

        choices = [
            {"name": f"Registrar resultado de mapa (Map {len(map_results) + 1})", "value": "map_result"},
            {"name": "Ver probabilidades atualizadas da serie", "value": "series_prob"},
            {"name": "Calcular hedge (apostei pre-match, quero proteger)", "value": "hedge"},
            {"name": "Mercados live disponiveis (Betano)", "value": "live_markets"},
            Separator(),
            {"name": "<< Voltar", "value": "back"},
        ]

        action = inquirer.select(
            message=f"[LIVE {a_score}-{b_score}] O que fazer?",
            choices=choices,
        ).execute()

        if action == "back":
            break

        elif action == "map_result":
            map_num = len(map_results) + 1
            map_name = veto_maps[map_num - 1] if map_num <= len(veto_maps) else f"Map {map_num}"

            winner = inquirer.select(
                message=f"Quem ganhou {map_name} (Map {map_num})?",
                choices=[
                    {"name": t1, "value": "a"},
                    {"name": t2, "value": "b"},
                ],
            ).execute()

            score_str = inquirer.text(
                message=f"Placar do mapa (ex: 13-10):",
                default="13-0",
            ).execute()

            map_results.append({
                "map_num": map_num,
                "map_name": map_name,
                "winner": "a" if winner == "a" else "b",
                "score": score_str,
            })

            if winner == "a":
                a_score += 1
            else:
                b_score += 1

            console.print(f"[green]Map {map_num} ({map_name}): "
                          f"{'[bold]' + t1 + '[/bold]' if winner == 'a' else t1} "
                          f"{score_str} "
                          f"{'[bold]' + t2 + '[/bold]' if winner == 'b' else t2}[/green]")

        elif action == "series_prob":
            _show_live_series_prob(
                match_id, a_score, b_score, maps_to_win,
                t1, t2, bo_type, map_results, veto_maps,
            )

        elif action == "hedge":
            _live_hedge(t1, t2, a_score, b_score, maps_to_win)

        elif action == "live_markets":
            _show_live_markets(a_score, b_score, maps_to_win, t1, t2, map_results, veto_maps)


def _show_live_series_prob(
    match_id, a_score, b_score, maps_to_win,
    t1, t2, bo_type, map_results, veto_maps,
):
    """Recalculate series probabilities given maps already played."""
    from src.analysis.probability import estimate_map_win

    maps_played = len(map_results)
    max_remaining = (2 * maps_to_win - 1) - maps_played
    a_needs = maps_to_win - a_score
    b_needs = maps_to_win - b_score

    if a_needs <= 0 or b_needs <= 0:
        winner = t1 if a_needs <= 0 else t2
        console.print(f"\n[green]{winner} ja venceu a serie![/green]")
        return

    remaining_probs = []
    info = None
    with get_db() as conn:
        row = conn.execute(
            """SELECT t1.id as t1_id, t2.id as t2_id FROM matches m
               LEFT JOIN teams t1 ON m.team1_id = t1.id
               LEFT JOIN teams t2 ON m.team2_id = t2.id
               WHERE m.id = ?""",
            (match_id,),
        ).fetchone()
        if row:
            t1_id, t2_id = row["t1_id"], row["t2_id"]
        else:
            t1_id, t2_id = None, None

    if t1_id and t2_id:
        for i in range(maps_played, maps_played + max_remaining):
            map_name = veto_maps[i] if i < len(veto_maps) else "Unknown"
            if map_name != "Unknown":
                ma = estimate_map_win(
                    t1_id, t2_id, map_name,
                    data_filter=config.data_filter,
                    bo_type=bo_type,
                )
                remaining_probs.append(ma.p_team_a_win)
            else:
                remaining_probs.append(0.5)
    else:
        remaining_probs = [0.5] * max_remaining

    series = simulate_series(remaining_probs, maps_to_win=a_needs, seed=match_id)

    p_a_wins = series["p_a_series"]
    p_b_wins = 1 - p_a_wins

    console.print(Panel(
        f"[bold]Apos {maps_played} mapas: {t1} {a_score} - {b_score} {t2}[/bold]\n\n"
        f"  {t1} precisa de mais {a_needs} mapa(s)\n"
        f"  {t2} precisa de mais {b_needs} mapa(s)\n\n"
        f"  P({t1} vence a serie) = [bold]{p_a_wins:.1%}[/bold]\n"
        f"  P({t2} vence a serie) = [bold]{p_b_wins:.1%}[/bold]\n\n"
        f"  Mapas restantes: {', '.join(veto_maps[maps_played:maps_played+max_remaining]) if veto_maps else '?'}",
        title="Serie Atualizada",
        border_style="cyan",
    ))


def _live_hedge(t1, t2, a_score, b_score, maps_to_win):
    """Hedge calculator for live scenario."""
    console.print("\n[bold]Hedge ao Vivo[/bold]")
    console.print("[dim]Voce apostou pre-match e quer proteger agora.[/dim]")
    console.print("[dim]Lembre: odds live so disponiveis na Betano![/dim]\n")

    bet_on = inquirer.select(
        message="Em quem voce apostou pre-match?",
        choices=[
            {"name": t1, "value": "a"},
            {"name": t2, "value": "b"},
        ],
    ).execute()

    stake_str = inquirer.text(message="Quanto apostou (R$):").execute()
    odds_str = inquirer.text(message="Odds da aposta original:").execute()
    live_odds_str = inquirer.text(
        message=f"Odds LIVE no oponente (Betano):",
    ).execute()

    try:
        result = hedge_calculator(float(stake_str), float(odds_str), float(live_odds_str))
    except (ValueError, ZeroDivisionError):
        console.print("[red]Valores invalidos.[/red]")
        return

    bet_team = t1 if bet_on == "a" else t2
    hedge_team = t2 if bet_on == "a" else t1

    console.print(Panel(
        f"[bold]Aposta original:[/bold] R${result['original_stake']:.2f} em {bet_team} @ {result['original_odds']}\n"
        f"[bold]Hedge sugerido:[/bold] R${result['hedge_stake']:.2f} em {hedge_team} @ {result['hedge_odds']} [odds.betano](Betano live)[/odds.betano]\n\n"
        f"  Se {bet_team} ganha: R${result['profit_if_original_wins']:+.2f}\n"
        f"  Se {hedge_team} ganha: R${result['profit_if_hedge_wins']:+.2f}\n"
        f"  Total investido: R${result['total_invested']:.2f}\n"
        f"  [{'green' if result['guaranteed_profit'] > 0 else 'red'}]"
        f"Lucro garantido: R${result['guaranteed_profit']:+.2f}[/]",
        title="Hedge Calculator (Live)",
        border_style="yellow",
    ))


def _show_live_markets(a_score, b_score, maps_to_win, t1, t2, map_results, veto_maps):
    """Show which markets are still available for live betting."""
    maps_played = len(map_results)
    remaining = (2 * maps_to_win - 1) - maps_played

    lines = []
    lines.append("[bold]Mercados disponiveis AO VIVO:[/bold]\n")
    lines.append(f"[odds.betano]BETANO (aceita live):[/odds.betano]")

    if a_score < maps_to_win and b_score < maps_to_win:
        lines.append(f"  - Match Winner (serie)")
        for i in range(maps_played, maps_played + remaining):
            map_name = veto_maps[i] if i < len(veto_maps) else f"Map {i+1}"
            lines.append(f"  - Map {i+1} ({map_name}) Winner")
            lines.append(f"  - Map {i+1} ({map_name}) OT")
            lines.append(f"  - Map {i+1} ({map_name}) Handicap")
            lines.append(f"  - Map {i+1} ({map_name}) Total Rounds")
        if maps_to_win == 3:
            lines.append(f"  - Correct Score (serie)")
    else:
        lines.append(f"  [dim]Serie ja encerrada[/dim]")

    lines.append(f"\n[odds.bet365]BET365 (NAO aceita live):[/odds.bet365]")
    lines.append(f"  [dim]Nenhum mercado live disponivel.[/dim]")
    lines.append(f"  [dim]Se apostou pre-match na Bet365, use o hedge na Betano.[/dim]")

    console.print(Panel("\n".join(lines), title="Live Markets", border_style="yellow"))


def _get_veto_map_names(match_id: int, bo_type: str) -> list[str]:
    """Get the list of map names from veto."""
    with get_db() as conn:
        rows = conn.execute(
            """SELECT map_name FROM pending_vetos
               WHERE match_id = ? AND action IN ('pick', 'decider')
               ORDER BY map_order""",
            (match_id,),
        ).fetchall()

    if rows:
        return [r["map_name"] for r in rows]

    n = 5 if "5" in str(bo_type) else 3
    return [f"Map {i+1}" for i in range(n)]
