"""Market preference selector.

Interactive checkbox UI for choosing which betting markets to analyze.
"""

from __future__ import annotations

from InquirerPy import inquirer
from rich.console import Console

from src.config import config, ALL_MARKET_TYPES, MARKET_LABELS
from src.ui.styles import VCT_THEME

console = Console(theme=VCT_THEME)


def market_selector():
    """Interactive market preference selector."""
    console.print("\n[bold cyan]Mercados Preferidos[/bold cyan]")
    console.print("[dim]Selecione quais mercados voce quer ver na analise.[/dim]\n")

    choices = []
    for m in ALL_MARKET_TYPES:
        label = MARKET_LABELS.get(m, m)
        enabled = m in config.markets.enabled_markets
        choices.append({"name": label, "value": m, "enabled": enabled})

    selected = inquirer.checkbox(
        message="Marque os mercados (SPACE para marcar/desmarcar, ENTER para confirmar):",
        choices=choices,
    ).execute()

    config.markets.enabled_markets = selected

    console.print(f"\n[green]Mercados ativos ({len(selected)}):[/green]")
    for m in selected:
        console.print(f"  [cyan]{MARKET_LABELS.get(m, m)}[/cyan]")


def filter_edges_by_market(edges: list, market_prefs=None) -> list:
    """Filter edge results to only show enabled markets."""
    if market_prefs is None:
        market_prefs = config.markets

    filtered = []
    for e in edges:
        market = getattr(e, "market", "")
        pref_key = _market_to_pref_key(market)
        if pref_key and market_prefs.is_enabled(pref_key):
            filtered.append(e)
        elif not pref_key:
            filtered.append(e)

    return filtered


def _market_to_pref_key(market_type: str) -> str | None:
    """Map a specific market_type (like 'map1_winner') to a preference key."""
    mt = market_type.lower()
    if "winner" in mt and "match" in mt:
        return "match_winner"
    if "winner" in mt and "map" in mt:
        return "map_winner"
    if "ot" in mt:
        return "map_ot"
    if "pistol" in mt:
        return "map_pistol"
    if "handicap" in mt:
        return "map_handicap"
    if "total_rounds" in mt or "over" in mt or "under" in mt:
        return "map_total_rounds"
    if "correct_score" in mt:
        return "correct_score"
    if "3.5" in mt or "over_maps" in mt:
        return "over_maps"
    if "2.5" in mt and "over" in mt:
        return "over_maps_2_5"
    if "2.5" in mt and "under" in mt:
        return "under_maps_2_5"
    if "4.5" in mt and "over" in mt:
        return "over_maps_4_5"
    if "4.5" in mt and "under" in mt:
        return "under_maps_4_5"
    return None
