"""Interactive VCT +EV Terminal — single-app experience.

Run once, navigate with menus, paste data, ask questions.
No commands to memorize.
"""

from __future__ import annotations

import sys
from typing import Optional

from InquirerPy import inquirer
from InquirerPy.separator import Separator
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from src.config import config, DataFilter, ALL_MARKET_TYPES, MARKET_LABELS
from src.db.schema import init_db
from src.db.connection import get_db
from src.ui.styles import VCT_THEME

console = Console(theme=VCT_THEME)



def _print_header():
    filt = config.data_filter
    f_text = filt.description if filt.is_active else "sem filtro"
    b = config.bankroll
    console.print()
    console.print(Panel(
        f"[bold bright_red] VCT +EV Terminal [/bold bright_red]  |  "
        f"Filtro: [cyan]{f_text}[/cyan]  |  "
        f"Bankroll: [green]R${b.total:.0f}[/green]",
        border_style="bright_red",
    ))



def run_interactive():
    """Main interactive loop."""
    init_db()
    _print_header()

    while True:
        try:
            choice = inquirer.select(
                message="Menu principal:",
                choices=[
                    {"name": "Selecionar partida", "value": "match"},
                    {"name": "Consultar estatisticas", "value": "query"},
                    {"name": "Configuracoes", "value": "settings"},
                    {"name": "Sync dados do VLR.gg", "value": "sync"},
                    Separator(),
                    {"name": "Sair", "value": "exit"},
                ],
                default="match",
            ).execute()

            if choice == "match":
                _match_flow()
            elif choice == "query":
                _query_flow()
            elif choice == "settings":
                _settings_flow()
            elif choice == "sync":
                _sync_flow()
            elif choice == "exit":
                console.print("\n[dim]Ate a proxima. Sem edge = sem bet.[/dim]\n")
                break

        except KeyboardInterrupt:
            console.print("\n[dim]Ate a proxima.[/dim]\n")
            break
        except Exception as e:
            console.print(f"\n[red]Erro: {e}[/red]\n")



def _match_flow():
    """Select a match, input veto + odds, run analysis."""
    matches = _get_matches_list()
    if not matches:
        console.print("[yellow]Nenhuma partida no DB. Rode 'Sync' primeiro.[/yellow]")
        return

    choices = []
    for m in matches:
        status_icon = {"ongoing": "[cyan]LIVE[/cyan]", "upcoming": "[yellow]UP[/yellow]"}.get(
            m["status"], "[dim]OK[/dim]"
        )
        label = (
            f"{m['t1_name'] or '?'} vs {m['t2_name'] or '?'}  "
            f"| {m['bo_type'] or '??'}  | {m['date'] or '??'}  "
            f"| {m['status'] or ''}"
        )
        if m["score1"] is not None:
            label += f"  ({m['score1']}-{m['score2']})"
        choices.append({"name": label, "value": m["id"]})

    choices.append(Separator())
    choices.append({"name": "<< Voltar", "value": None})

    match_id = inquirer.select(
        message="Selecione a partida:",
        choices=choices,
        max_height="70%",
    ).execute()

    if match_id is None:
        return

    _analyze_match_interactive(match_id)


def _analyze_match_interactive(match_id: int):
    """Full interactive analysis flow for a match."""
    match_info = _get_match_info(match_id)
    if not match_info:
        console.print("[red]Partida nao encontrada.[/red]")
        return

    t1 = match_info["t1_name"] or "Team 1"
    t2 = match_info["t2_name"] or "Team 2"
    console.print(f"\n[bold]{t1} vs {t2}[/bold] — {match_info['event_name'] or ''}")

    has_veto = _check_veto(match_id)

    while True:
        actions = [
            {"name": f"Analise completa", "value": "analyze"},
        ]
        if not has_veto:
            actions.insert(0, {"name": "Colar veto (picks/bans)", "value": "veto"})
        else:
            actions.insert(0, {"name": "Refazer veto", "value": "veto"})

        actions.extend([
            {"name": "Inserir odds (batch)", "value": "odds"},
            {"name": "Live / in-play (durante a partida)", "value": "live"},
            {"name": "Consultar stats desse matchup", "value": "matchup_query"},
            Separator(),
            {"name": "<< Voltar ao menu", "value": "back"},
        ])

        action = inquirer.select(
            message=f"[{t1} vs {t2}] O que fazer?",
            choices=actions,
        ).execute()

        if action == "back":
            break
        elif action == "veto":
            has_veto = _input_veto(match_id, t1, t2, match_info)
        elif action == "odds":
            _input_odds(match_id)
        elif action == "analyze":
            _run_analysis(match_id)
        elif action == "live":
            _live_flow(match_id, match_info)
        elif action == "matchup_query":
            _matchup_query(match_id, match_info)


def _input_veto(match_id: int, t1: str, t2: str, info: dict) -> bool:
    """Input veto by pasting VLR string or step-by-step."""
    from src.collectors.manual_input import parse_veto_string, _save_veto, _display_veto_summary

    mode = inquirer.select(
        message="Como inserir o veto?",
        choices=[
            {"name": "Colar string do VLR (ex: MIBR ban Pearl; NRG pick Bind; ...)", "value": "paste"},
            {"name": "Passo a passo", "value": "step"},
            {"name": "<< Voltar", "value": "back"},
        ],
    ).execute()

    if mode == "back":
        return False

    t1_id = info.get("t1_id")
    t2_id = info.get("t2_id")

    if mode == "paste":
        veto_str = inquirer.text(
            message="Cole o veto do VLR.gg:",
        ).execute()

        actions = parse_veto_string(veto_str, t1, t2, t1_id, t2_id)
        if not actions:
            console.print("[red]Nao consegui parsear. Formato esperado:[/red]")
            console.print("[dim]MIBR ban Pearl; NRG ban Breeze; MIBR pick Bind; ... Haven remains[/dim]")
            return False

        _save_veto(match_id, actions)
        console.print("[green]Veto salvo![/green]")
        _display_veto_summary(actions)
        return True

    else:
        from src.collectors.manual_input import _interactive_veto, _save_veto, _display_veto_summary
        bo = info.get("bo_type", "bo3")
        actions = _interactive_veto(t1, t2, t1_id, t2_id, bo)
        if actions:
            _save_veto(match_id, actions)
            console.print("[green]Veto salvo![/green]")
            _display_veto_summary(actions)
            return True
        return False


def _input_odds(match_id: int):
    """Input odds via batch paste or one-by-one."""
    from src.collectors.manual_input import parse_odds_string, batch_odds_insert

    mode = inquirer.select(
        message="Como inserir odds?",
        choices=[
            {"name": "Colar batch (betano map1_winner MIBR 1.75; bet365 map1_ot Yes 5.00; ...)", "value": "batch"},
            {"name": "Uma por uma (interativo)", "value": "manual"},
            {"name": "<< Voltar", "value": "back"},
        ],
    ).execute()

    if mode == "back":
        return

    if mode == "batch":
        odds_str = inquirer.text(
            message="Cole as odds (bookmaker mercado selecao odds; ...):",
        ).execute()

        entries = parse_odds_string(odds_str)
        if not entries:
            console.print("[red]Nenhuma odd parseada. Formato: betano map1_winner MIBR 1.75[/red]")
            return

        count = batch_odds_insert(match_id, entries)
        table = Table(title=f"{count} odds adicionadas")
        table.add_column("Casa")
        table.add_column("Mercado")
        table.add_column("Selecao")
        table.add_column("Odds", justify="right")
        for o in entries:
            table.add_row(o["bookmaker"], o["market_type"], o["selection"], f"{o['odds_value']:.2f}")
        console.print(table)

    else:
        from src.collectors.manual_input import manual_odds_entry
        manual_odds_entry(match_id)


def _run_analysis(match_id: int):
    """Run full analysis and display results."""
    from src.analysis.probability import estimate_map_win, estimate_ot_prob, simulate_series
    from src.analysis.edge import analyze_market_edges, build_market_probs
    from src.analysis.arbitrage import detect_arbitrage
    from src.analysis.multibets import analyze_spread, find_profitable_parlays, correct_score_coverage
    from src.analysis.maps import get_h2h_stats
    from src.models.data_models import MatchAnalysis
    from src.ui.match_view import render_full_analysis
    from src.ui.recommendations import render_action_summary

    info = _get_match_info(match_id)
    if not info:
        return

    team_a_id = info["t1_id"]
    team_b_id = info["t2_id"]
    team_a_name = info["t1_name"] or "Team A"
    team_b_name = info["t2_name"] or "Team B"
    bo_type = info["bo_type"] or "bo3"

    map_list = _get_veto_maps(match_id, bo_type)

    map_analyses = []
    ot_results = []
    map_probs_a = []

    for m in map_list:
        ma = estimate_map_win(
            team_a_id, team_b_id, m["map_name"],
            starting_side_a=m.get("start_side"),
            data_filter=config.data_filter,
            bo_type=bo_type,
        )
        ma.map_order = m["map_order"]
        ma.pick_team = m.get("pick_team")

        ot = estimate_ot_prob(
            team_a_id, team_b_id, m["map_name"],
            data_filter=config.data_filter,
            bo_type=bo_type,
        )
        ma.p_ot = ot["p_ot"]

        map_analyses.append(ma)
        ot_results.append(ot)
        map_probs_a.append(ma.p_team_a_win)

    maps_to_win = 3 if "5" in str(bo_type) else 2
    series_result = simulate_series(map_probs_a, maps_to_win=maps_to_win, seed=match_id)

    team_a_aliases = [x for x in [info.get("t1_name"), info.get("t1_tag")] if x]
    team_b_aliases = [x for x in [info.get("t2_name"), info.get("t2_tag")] if x]
    market_probs = build_market_probs(
        map_analyses, series_result, ot_results,
        team_a_aliases=team_a_aliases or None,
        team_b_aliases=team_b_aliases or None,
    )
    single_edges = analyze_market_edges(match_id, market_probs)
    arbs = detect_arbitrage(match_id)

    ot_probs = [ot["p_ot"] for ot in ot_results]
    ot_odds_list = _get_ot_odds(match_id, len(map_list))
    multi_bets = []
    if ot_odds_list and len(ot_odds_list) == len(ot_probs):
        spread = analyze_spread(
            ot_probs, ot_odds_list, market_label="OT",
            stake_per_map=config.multibet.default_spread_stake,
        )
        if spread:
            multi_bets.append(spread)

    positive = [
        {"market": e.market, "selection": e.selection, "p_model": e.p_model,
         "odds": e.odds, "bookmaker": e.bookmaker, "confidence": e.confidence}
        for e in single_edges if e.edge > 0
    ]
    parlays = find_profitable_parlays(positive, max_legs=3)
    multi_bets.extend(parlays)

    score_odds = _get_score_odds(match_id)
    if score_odds and series_result.get("score_probs"):
        cs = correct_score_coverage(series_result["score_probs"], score_odds)
        if cs:
            multi_bets.append(cs)

    h2h = get_h2h_stats(team_a_id, team_b_id, data_filter=config.data_filter)

    analysis = MatchAnalysis(
        match_id=match_id,
        event_name=info.get("event_name") or "",
        stage_name=info.get("stage_name") or "",
        bo_type=bo_type,
        team_a_name=team_a_name,
        team_b_name=team_b_name,
        team_a_id=team_a_id,
        team_b_id=team_b_id,
        h2h_event=(h2h["a_wins"], h2h["b_wins"]),
        maps=map_analyses,
        series_p_a_win=series_result["p_a_series"],
        score_probs=series_result.get("score_probs", {}),
        single_edges=single_edges,
        multi_bets=multi_bets,
    )

    render_full_analysis(analysis)
    render_action_summary(single_edges, multi_bets, arbs)

    _post_analysis_menu(match_id, analysis, single_edges, ot_results, map_list)


def _post_analysis_menu(match_id, analysis, edges, ot_results, map_list):
    """After analysis, offer additional actions."""
    while True:
        action = inquirer.select(
            message="Apos a analise:",
            choices=[
                {"name": "Calcular spread OT personalizado (stake por mapa)", "value": "spread"},
                {"name": "Calculadora de hedge", "value": "hedge"},
                {"name": "Atualizar odds", "value": "odds"},
                {"name": "Refazer analise", "value": "rerun"},
                Separator(),
                {"name": "<< Voltar", "value": "back"},
            ],
        ).execute()

        if action == "back":
            break
        elif action == "spread":
            _custom_spread(ot_results, match_id, map_list)
        elif action == "hedge":
            _hedge_interactive()
        elif action == "odds":
            _input_odds(match_id)
        elif action == "rerun":
            _run_analysis(match_id)
            break


def _custom_spread(ot_results, match_id, map_list):
    """Custom OT spread with user-defined stake."""
    from src.analysis.multibets import analyze_spread

    stake_str = inquirer.text(
        message="Stake por mapa (R$):",
        default=str(config.multibet.default_spread_stake),
    ).execute()

    try:
        stake = float(stake_str)
    except ValueError:
        console.print("[red]Valor invalido.[/red]")
        return

    ot_probs = [ot["p_ot"] for ot in ot_results]
    ot_odds = _get_ot_odds(match_id, len(map_list))

    if not ot_odds or len(ot_odds) != len(ot_probs):
        console.print("[yellow]Sem odds de OT para todos os mapas. Insira odds primeiro.[/yellow]")
        return

    spread = analyze_spread(ot_probs, ot_odds, market_label="OT", stake_per_map=stake)
    if spread:
        from src.ui.match_view import render_multibets
        console.print(render_multibets([spread]))
    else:
        console.print("[yellow]Spread nao e +EV com esses parametros.[/yellow]")
        n = len(ot_probs)
        total = stake * n
        p_zero = 1.0
        for p in ot_probs:
            p_zero *= (1 - p)
        p_at_least_1 = 1 - p_zero
        console.print(f"  R${stake:.0f} x {n} mapas = R${total:.0f}")
        console.print(f"  P(>=1 OT) = {p_at_least_1:.1%}")
        console.print(f"  [dim]EV negativo — nao recomendado[/dim]")


def _hedge_interactive():
    """Interactive hedge calculator."""
    from src.analysis.multibets import hedge_calculator

    stake_str = inquirer.text(message="Stake original (R$):").execute()
    odds_str = inquirer.text(message="Odds original:").execute()
    hedge_str = inquirer.text(message="Odds do hedge (oponente):").execute()

    try:
        result = hedge_calculator(float(stake_str), float(odds_str), float(hedge_str))
    except (ValueError, ZeroDivisionError):
        console.print("[red]Valores invalidos.[/red]")
        return

    console.print(Panel("[bold]Hedge Calculator[/bold]", border_style="cyan"))
    console.print(f"  Aposta original: R${result['original_stake']:.2f} @ {result['original_odds']}")
    console.print(f"  Payout original: R${result['original_payout']:.2f}")
    console.print(f"  [bold]Hedge: R${result['hedge_stake']:.2f} @ {result['hedge_odds']}[/bold]")
    console.print(f"  Se original ganha: R${result['profit_if_original_wins']:.2f}")
    console.print(f"  Se hedge ganha: R${result['profit_if_hedge_wins']:.2f}")
    console.print(f"  Total investido: R${result['total_invested']:.2f}")
    console.print(f"  [{'green' if result['guaranteed_profit'] > 0 else 'red'}]"
                  f"Lucro garantido: R${result['guaranteed_profit']:.2f}[/]")


def _live_flow(match_id: int, info: dict):
    """Live/in-play analysis during a match."""
    from src.ui.live_analysis import live_analysis_menu
    live_analysis_menu(match_id, info)


def _matchup_query(match_id: int, info: dict):
    """Quick stat queries about the specific matchup."""
    from src.ui.query_engine import run_query_loop
    context = {
        "match_id": match_id,
        "team_a": info.get("t1_name"),
        "team_b": info.get("t2_name"),
        "team_a_id": info.get("t1_id"),
        "team_b_id": info.get("t2_id"),
    }
    run_query_loop(context=context)



def _query_flow():
    """Open-ended stat queries."""
    from src.ui.query_engine import run_query_loop
    run_query_loop()



def _settings_flow():
    """Settings menu."""
    while True:
        action = inquirer.select(
            message="Configuracoes:",
            choices=[
                {"name": f"Bankroll (atual: R${config.bankroll.total:.0f})", "value": "bankroll"},
                {"name": f"Edge thresholds (min: {config.edge.min_edge:.0%}, forte: {config.edge.strong_edge:.0%})", "value": "edge"},
                {"name": "Mercados preferidos", "value": "markets"},
                {"name": "Filtro de dados (eventos/datas)", "value": "filter"},
                {"name": f"Stake spread default (R${config.multibet.default_spread_stake:.0f})", "value": "spread_stake"},
                {"name": "Live betting (Betano/Bet365)", "value": "live_cfg"},
                Separator(),
                {"name": "<< Voltar", "value": "back"},
            ],
        ).execute()

        if action == "back":
            break
        elif action == "bankroll":
            _config_bankroll()
        elif action == "edge":
            _config_edge()
        elif action == "markets":
            _config_markets()
        elif action == "filter":
            _config_filter()
        elif action == "spread_stake":
            _config_spread_stake()
        elif action == "live_cfg":
            _config_live()


def _config_bankroll():
    val = inquirer.text(message="Bankroll total (R$):", default=str(config.bankroll.total)).execute()
    try:
        config.bankroll.total = float(val)
    except ValueError:
        pass

    val = inquirer.text(message="Max stake % (ex: 0.03 = 3%):", default=str(config.bankroll.max_stake_pct)).execute()
    try:
        config.bankroll.max_stake_pct = float(val)
    except ValueError:
        pass

    val = inquirer.text(message="Kelly fraction (ex: 0.25):", default=str(config.bankroll.kelly_fraction)).execute()
    try:
        config.bankroll.kelly_fraction = float(val)
    except ValueError:
        pass

    console.print(f"[green]Bankroll: R${config.bankroll.total:.0f} | "
                  f"Max stake: {config.bankroll.max_stake_pct:.0%} | "
                  f"Kelly: {config.bankroll.kelly_fraction:.0%}[/green]")


def _config_edge():
    val = inquirer.text(message="Min edge (ex: 0.03 = 3%):", default=str(config.edge.min_edge)).execute()
    try:
        config.edge.min_edge = float(val)
    except ValueError:
        pass

    val = inquirer.text(message="Edge forte (ex: 0.08 = 8%):", default=str(config.edge.strong_edge)).execute()
    try:
        config.edge.strong_edge = float(val)
    except ValueError:
        pass

    console.print(f"[green]Min edge: {config.edge.min_edge:.0%} | Forte: {config.edge.strong_edge:.0%}[/green]")


def _config_markets():
    from src.ui.market_selector import market_selector
    market_selector()


def _config_filter():
    """Configure data filter interactively."""
    with get_db() as conn:
        events = conn.execute("SELECT id, name, status FROM events ORDER BY id DESC").fetchall()

    if not events:
        console.print("[yellow]Nenhum evento no DB. Sync primeiro.[/yellow]")
        return

    choices = [{"name": f"{e['id']}: {e['name']} ({e['status'] or ''})", "value": e['id']}
               for e in events]

    selected = inquirer.checkbox(
        message="Selecione os eventos para filtrar (SPACE para marcar, ENTER para confirmar):",
        choices=choices,
        default=[e["id"] for e in events if config.data_filter.event_ids and e["id"] in config.data_filter.event_ids],
    ).execute()

    date_from = inquirer.text(
        message="Data inicio (YYYY-MM-DD, vazio = sem limite):",
        default=config.data_filter.date_from or "",
    ).execute()

    config.data_filter = DataFilter(
        event_ids=selected if selected else [],
        date_from=date_from if date_from.strip() else None,
    )

    console.print(f"[green]Filtro: {config.data_filter.description}[/green]")


def _config_spread_stake():
    val = inquirer.text(
        message="Stake default por mapa no spread (R$):",
        default=str(config.multibet.default_spread_stake),
    ).execute()
    try:
        config.multibet.default_spread_stake = float(val)
    except ValueError:
        pass
    console.print(f"[green]Spread stake: R${config.multibet.default_spread_stake:.0f}[/green]")


def _config_live():
    console.print(f"\n[bold]Live Betting Config[/bold]")
    console.print(f"  [odds.betano]Betano[/odds.betano]: suporta apostas ao vivo em Valorant")
    console.print(f"  [odds.bet365]Bet365[/odds.bet365]: NAO suporta apostas ao vivo em Valorant")

    config.live.show_live_opportunities = inquirer.confirm(
        message="Mostrar oportunidades live na analise?",
        default=config.live.show_live_opportunities,
    ).execute()

    console.print(f"[green]Live opportunities: {'ativado' if config.live.show_live_opportunities else 'desativado'}[/green]")



def _sync_flow():
    """Sync data from VLR.gg."""
    from src.collectors.vlr_collector import full_sync, sync_events

    mode = inquirer.select(
        message="Sync:",
        choices=[
            {"name": "Sync completo (eventos + matches + deep)", "value": "full"},
            {"name": "Apenas eventos e matches (rapido)", "value": "shallow"},
            {"name": "<< Voltar", "value": "back"},
        ],
    ).execute()

    if mode == "back":
        return

    console.print("[cyan]Sincronizando...[/cyan]")
    full_sync(deep=(mode == "full"))
    console.print("[green]Sync completo![/green]")
    _print_header()



def _get_matches_list() -> list[dict]:
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
                       m.stage_name, t1.name as t1_name, t2.name as t2_name,
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
                LIMIT 30""",
            params,
        ).fetchall()
    return [dict(r) for r in rows]


def _get_match_info(match_id: int) -> Optional[dict]:
    with get_db() as conn:
        row = conn.execute(
            """SELECT m.*, t1.name as t1_name, t1.id as t1_id, t1.tag as t1_tag,
                      t2.name as t2_name, t2.id as t2_id, t2.tag as t2_tag,
                      e.name as event_name
               FROM matches m
               LEFT JOIN teams t1 ON m.team1_id = t1.id
               LEFT JOIN teams t2 ON m.team2_id = t2.id
               LEFT JOIN events e ON m.event_id = e.id
               WHERE m.id = ?""",
            (match_id,),
        ).fetchone()
    return dict(row) if row else None


def _check_veto(match_id: int) -> bool:
    with get_db() as conn:
        row = conn.execute(
            "SELECT COUNT(*) as c FROM pending_vetos WHERE match_id = ? AND action IN ('pick', 'decider')",
            (match_id,),
        ).fetchone()
    return row["c"] > 0 if row else False


def _get_veto_maps(match_id: int, bo_type: str) -> list[dict]:
    with get_db() as conn:
        veto_rows = conn.execute(
            """SELECT * FROM pending_vetos WHERE match_id = ?
               ORDER BY CASE source WHEN 'manual' THEN 0 ELSE 1 END, map_order""",
            (match_id,),
        ).fetchall()

    map_list = []
    seen_sources = set()
    for v in veto_rows:
        if v["action"] in ("pick", "decider"):
            if v["source"] == "vlr" and "manual" in seen_sources:
                continue
            map_list.append({
                "map_name": v["map_name"],
                "map_order": len(map_list) + 1,
                "pick_team": v["team_name"],
                "start_side": v["start_side"] if "start_side" in v.keys() else None,
            })
        seen_sources.add(v["source"])

    if not map_list:
        n = 5 if "5" in str(bo_type) else 3
        map_list = [{"map_name": "Unknown", "map_order": i + 1, "pick_team": None, "start_side": None}
                    for i in range(n)]

    return map_list


def _get_ot_odds(match_id: int, n_maps: int) -> list[float]:
    with get_db() as conn:
        odds = []
        for i in range(1, n_maps + 1):
            row = conn.execute(
                """SELECT odds_value FROM odds_snapshots
                   WHERE match_id = ? AND market_type LIKE ? AND LOWER(selection) LIKE '%yes%'
                   ORDER BY timestamp DESC LIMIT 1""",
                (match_id, f"%map{i}_ot%"),
            ).fetchone()
            if row:
                odds.append(row["odds_value"])
    return odds if len(odds) == n_maps else []


def _get_score_odds(match_id: int) -> dict[str, float]:
    with get_db() as conn:
        rows = conn.execute(
            """SELECT selection, odds_value FROM odds_snapshots
               WHERE match_id = ? AND market_type = 'correct_score'
               ORDER BY timestamp DESC""",
            (match_id,),
        ).fetchall()
    result = {}
    for r in rows:
        sel = r["selection"].strip()
        if sel not in result:
            result[sel] = r["odds_value"]
    return result
