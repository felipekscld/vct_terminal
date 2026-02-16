"""Recommendations view: standalone edge/multi-bet summary."""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from src.config import config
from src.models.data_models import EdgeResult, MultiBetOpportunity
from src.ui.styles import VCT_THEME

console = Console(theme=VCT_THEME)


def render_action_summary(
    edges: list[EdgeResult],
    multibets: list[MultiBetOpportunity],
    arbs: list[dict],
) -> None:
    """Render a concise action summary: what to bet and why."""
    console.print()
    console.print(Panel("[header] Action Summary [/header]", border_style="bright_red"))

    if arbs:
        for arb in arbs:
            if arb.get("is_arb"):
                console.print(f"  [arb]ARBITRAGEM[/arb] {arb['description']}")
                for sel, info in arb.get("selections", {}).items():
                    console.print(f"    {sel}: {info['bookmaker']} @ {info['odds']}")

    strong = [e for e in edges if e.recommendation == "EDGE FORTE"]
    if strong:
        console.print("\n[edge.strong]--- Apostas recomendadas ---[/edge.strong]")
        for e in strong:
            map_label = f" Map{e.map_number}" if e.map_number else ""
            console.print(
                f"  {e.market}{map_label} {e.selection} @ "
                f"[odds.{e.bookmaker}]{e.bookmaker}[/odds.{e.bookmaker}] {e.odds:.2f} | "
                f"edge={e.edge:+.1%} | stake=R${e.suggested_stake:.0f}"
            )

    if multibets:
        console.print("\n[multi.spread]--- Multi-bets ---[/multi.spread]")
        for mb in multibets:
            console.print(f"  [{mb.strategy.upper()}] {mb.description}")
            console.print(f"    EV: R${mb.ev:+.2f} | edge: {mb.edge:+.1%}")

    weak = [e for e in edges if e.recommendation == "OBSERVAR"]
    if weak:
        console.print("\n[edge.weak]--- Observar ---[/edge.weak]")
        for e in weak:
            map_label = f" Map{e.map_number}" if e.map_number else ""
            console.print(
                f"  {e.market}{map_label} {e.selection} @ {e.bookmaker} {e.odds:.2f} | "
                f"edge={e.edge:+.1%}"
            )

    if not strong and not weak and not multibets and not arbs:
        console.print("\n[edge.none]Nenhuma oportunidade encontrada. Sem edge = sem bet.[/edge.none]")

    console.print()
