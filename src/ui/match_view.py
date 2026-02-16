"""Detailed match analysis view rendered as Rich panels."""

from __future__ import annotations

from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table
from rich.columns import Columns
from rich.text import Text

from src.config import config
from src.models.data_models import MatchAnalysis, MapAnalysis, EdgeResult, MultiBetOpportunity
from src.ui.styles import VCT_THEME, EDGE_LABELS, STRATEGY_LABELS

console = Console(theme=VCT_THEME)


def render_match_header(analysis: MatchAnalysis) -> Panel:
    """Render the match overview header."""
    lines = []
    lines.append(f"[header] {analysis.team_a_name} vs {analysis.team_b_name} [/header]")
    lines.append(f"[subheader]{analysis.event_name}[/subheader] | {analysis.stage_name}")
    lines.append(f"Format: {analysis.bo_type} | H2H this event: {analysis.h2h_event[0]}-{analysis.h2h_event[1]}")

    filt = config.data_filter
    if filt.is_active:
        lines.append(f"[filter_active]Filtro ativo:[/filter_active] [filter_label]{filt.description}[/filter_label]")
    else:
        lines.append("[warning]Sem filtro de dados — usando todos os dados disponíveis[/warning]")

    return Panel("\n".join(lines), title="Match Overview", border_style="panel_border")


def render_veto(maps: list[MapAnalysis], team_a: str, team_b: str) -> Panel:
    """Render the veto / map picks."""
    table = Table(show_header=True, header_style="bold", expand=True)
    table.add_column("#", width=4)
    table.add_column("Map", style="map_name")
    table.add_column("Pick")
    table.add_column(f"{team_a} WR", justify="center")
    table.add_column(f"{team_b} WR", justify="center")
    table.add_column("P(A win)", justify="center")
    table.add_column("P(OT)", justify="center")
    table.add_column("Conf", justify="center")

    for m in maps:
        a_wr = f"{m.team_a_stats.winrate:.0%}" if m.team_a_stats and m.team_a_stats.games_played else "N/A"
        b_wr = f"{m.team_b_stats.winrate:.0%}" if m.team_b_stats and m.team_b_stats.games_played else "N/A"
        a_sample = f"({m.team_a_stats.games_played})" if m.team_a_stats else ""
        b_sample = f"({m.team_b_stats.games_played})" if m.team_b_stats else ""

        p_a = f"{m.p_team_a_win:.1%}"
        p_ot = f"{m.p_ot:.1%}" if m.p_ot > 0 else "-"
        pick = m.pick_team or "decider"

        table.add_row(
            f"Map {m.map_order}",
            m.map_name,
            pick,
            f"{a_wr} {a_sample}",
            f"{b_wr} {b_sample}",
            p_a,
            p_ot,
            m.confidence,
        )

    return Panel(table, title="Veto & Map Analysis", border_style="panel_border")


def render_map_detail(m: MapAnalysis, team_a: str, team_b: str) -> Panel:
    """Render detailed stats for a single map."""
    lines = []
    lines.append(f"[map_name]{m.map_name}[/map_name] (Map {m.map_order}) — pick: {m.pick_team or 'decider'}")
    lines.append("")

    if m.team_a_stats and m.team_a_stats.games_played:
        a = m.team_a_stats
        lines.append(f"[team_a]{team_a}[/team_a] on {m.map_name}: "
                      f"{a.wins}W-{a.losses}L ({a.winrate:.0%}) | "
                      f"ATK {a.atk_round_rate:.0%} DEF {a.def_round_rate:.0%} | "
                      f"Pistol {a.pistol_rate:.0%} Conv {a.pistol_conversion_rate:.0%} | "
                      f"OT rate {a.ot_rate:.0%} | Close {a.close_rate:.0%} | "
                      f"Avg RD {a.avg_round_diff:+.1f}")

    if m.team_b_stats and m.team_b_stats.games_played:
        b = m.team_b_stats
        lines.append(f"[team_b]{team_b}[/team_b] on {m.map_name}: "
                      f"{b.wins}W-{b.losses}L ({b.winrate:.0%}) | "
                      f"ATK {b.atk_round_rate:.0%} DEF {b.def_round_rate:.0%} | "
                      f"Pistol {b.pistol_rate:.0%} Conv {b.pistol_conversion_rate:.0%} | "
                      f"OT rate {b.ot_rate:.0%} | Close {b.close_rate:.0%} | "
                      f"Avg RD {b.avg_round_diff:+.1f}")

    if not (m.team_a_stats and m.team_a_stats.games_played) and \
       not (m.team_b_stats and m.team_b_stats.games_played):
        lines.append("[warning]Sem dados suficientes para este mapa no filtro atual.[/warning]")

    if m.factors:
        lines.append("")
        lines.append("[dim]Fatores do modelo:[/dim]")
        for k, v in m.factors.items():
            if k == "filter":
                continue
            lines.append(f"  [stat_label]{k}:[/stat_label] [stat_value]{v}[/stat_value]")

    return Panel("\n".join(lines), border_style="panel_border")


def render_edges_table(edges: list[EdgeResult]) -> Panel:
    """Render the markets & edge comparison table."""
    table = Table(show_header=True, header_style="bold", expand=True)
    table.add_column("Market")
    table.add_column("Selection")
    table.add_column("Bookmaker")
    table.add_column("Odds", justify="right")
    table.add_column("p_impl", justify="center")
    table.add_column("p_model", justify="center")
    table.add_column("Edge", justify="center")
    table.add_column("Rec")
    table.add_column("Stake", justify="right")

    for e in edges:
        edge_color = "edge.strong" if e.edge >= config.edge.strong_edge else \
                     "edge.weak" if e.edge >= config.edge.min_edge else "edge.none"
        bk_style = "odds.betano" if "betano" in e.bookmaker else "odds.bet365"

        map_label = f" M{e.map_number}" if e.map_number else ""
        table.add_row(
            f"{e.market}{map_label}",
            e.selection,
            f"[{bk_style}]{e.bookmaker}[/{bk_style}]",
            f"{e.odds:.2f}",
            f"{e.p_impl:.1%}",
            f"{e.p_model:.1%}",
            f"[{edge_color}]{e.edge:+.1%}[/{edge_color}]",
            EDGE_LABELS.get(e.recommendation, e.recommendation),
            f"R${e.suggested_stake:.0f}" if e.suggested_stake > 0 else "-",
        )

    return Panel(table, title="Markets & Edge", border_style="panel_border")


def render_multibets(multibets: list[MultiBetOpportunity]) -> Panel:
    """Render multi-bet opportunities panel."""
    if not multibets:
        return Panel("[dim]Nenhuma oportunidade multi-bet encontrada.[/dim]",
                     title="Multi-Bets", border_style="panel_border")

    lines = []
    for mb in multibets:
        label = STRATEGY_LABELS.get(mb.strategy, mb.strategy.upper())
        lines.append(f"[{label}] {mb.description}")

        if mb.strategy == "spread":
            d = mb.details
            lines.append(
                f"  R${d.get('stake_per_map', 0):.0f} x {d.get('maps', 0)} mapas = "
                f"R${mb.total_stake:.0f} | min return R${mb.min_payout:.0f}"
            )
            lines.append(
                f"  P(>=1) = {d.get('p_at_least_1', 0):.1%} | "
                f"P(>=2) = {d.get('p_at_least_2', 0):.1%} | "
                f"EV: R${mb.ev:+.2f} ({mb.edge:+.1%})"
            )
        elif mb.strategy == "parlay":
            lines.append(
                f"  odds combinada: {mb.combined_odds:.2f} | "
                f"p_model: {mb.p_model:.1%} | p_impl: {mb.p_impl:.1%} | "
                f"edge: {mb.edge:+.1%}"
            )
        elif mb.strategy == "correct_score":
            d = mb.details
            lines.append(
                f"  Total: R${mb.total_stake:.0f} | "
                f"Expected return: R${d.get('expected_return', 0):.0f} | "
                f"EV: R${mb.ev:+.2f} ({mb.edge:+.1%})"
            )
        lines.append("")

    return Panel("\n".join(lines), title="Multi-Bet Opportunities", border_style="panel_border")


def render_recommendations(edges: list[EdgeResult]) -> Panel:
    """Render summary recommendations."""
    strong = [e for e in edges if e.recommendation == "EDGE FORTE"]
    weak = [e for e in edges if e.recommendation == "OBSERVAR"]

    lines = []
    for e in strong:
        map_label = f" Map{e.map_number}" if e.map_number else ""
        lines.append(
            f"[edge.strong]EDGE FORTE[/edge.strong] {e.market}{map_label} "
            f"{e.selection} @ {e.bookmaker} {e.odds:.2f}"
        )
        lines.append(
            f"  edge={e.edge:+.1%}, conf={e.confidence}, sample={e.sample_size} | "
            f"Stake: R${e.suggested_stake:.0f}"
        )

    for e in weak:
        map_label = f" Map{e.map_number}" if e.map_number else ""
        lines.append(
            f"[edge.weak]OBSERVAR[/edge.weak] {e.market}{map_label} "
            f"{e.selection} @ {e.bookmaker} {e.odds:.2f}"
        )
        lines.append(f"  edge={e.edge:+.1%}, conf={e.confidence}, sample={e.sample_size}")

    if not strong and not weak:
        lines.append("[edge.none]Nenhum edge encontrado nos mercados atuais.[/edge.none]")

    return Panel("\n".join(lines), title="Recommendations", border_style="panel_border")


def render_bankroll() -> Panel:
    """Render bankroll / risk management bar."""
    b = config.bankroll
    return Panel(
        f"[bankroll]Bankroll: R${b.total:.0f}[/bankroll] | "
        f"Max stake: {b.max_stake_pct:.0%} (R${b.total * b.max_stake_pct:.0f}) | "
        f"Kelly frac: {b.kelly_fraction:.0%} | "
        f"Daily limit: R${b.daily_limit:.0f} | "
        f"Event limit: R${b.event_limit:.0f}",
        border_style="panel_border",
    )


def render_full_analysis(analysis: MatchAnalysis) -> None:
    """Render the complete analysis for a match to the terminal."""
    console.print()
    console.print(render_match_header(analysis))
    console.print(render_veto(analysis.maps, analysis.team_a_name, analysis.team_b_name))

    for m in analysis.maps:
        console.print(render_map_detail(m, analysis.team_a_name, analysis.team_b_name))

    if analysis.single_edges:
        console.print(render_edges_table(analysis.single_edges))
        console.print(render_recommendations(analysis.single_edges))

    if analysis.multi_bets:
        console.print(render_multibets(analysis.multi_bets))

    if analysis.score_probs:
        table = Table(title="Series Score Distribution", show_header=True, expand=False)
        table.add_column("Score")
        table.add_column("Probability", justify="center")
        for score, prob in sorted(analysis.score_probs.items(), key=lambda x: -x[1]):
            table.add_row(score, f"{prob:.1%}")
        console.print(Panel(table, border_style="panel_border"))

    console.print(render_bankroll())
