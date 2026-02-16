"""VCT +EV Terminal — entry point.

Default: runs the interactive terminal (menus, prompts, no commands to memorize).
With --legacy: runs the old CLI commands for scripting/automation.
"""

from __future__ import annotations

import sys
from typing import Optional, List

import typer
from rich.console import Console

from src.config import config, DataFilter
from src.db.schema import init_db
from src.db.connection import get_db
from src.ui.styles import VCT_THEME

console = Console(theme=VCT_THEME)

legacy_app = typer.Typer(name="vct-legacy", add_completion=False, help="Legacy CLI commands")



def main():
    """Entry point: interactive mode by default, --legacy for old commands."""
    if len(sys.argv) > 1 and sys.argv[1] == "--legacy":
        sys.argv.pop(1)
        legacy_app()
    else:
        init_db()
        from src.ui.interactive import run_interactive
        run_interactive()



@legacy_app.command()
def sync(
    event_id: Optional[int] = typer.Option(None, "--event", "-e"),
    deep: bool = typer.Option(True, "--deep/--shallow"),
):
    """Sync VCT data from VLR.gg."""
    init_db()
    from src.collectors.vlr_collector import full_sync
    full_sync(event_id=event_id, deep=deep)


@legacy_app.command()
def analyze(
    match_id: int = typer.Argument(...),
    events: Optional[List[int]] = typer.Option(None, "--events", "-e"),
    stages: Optional[List[str]] = typer.Option(None, "--stages", "-s"),
    date_from: Optional[str] = typer.Option(None, "--from"),
    date_to: Optional[str] = typer.Option(None, "--to"),
):
    """Run full analysis on a match."""
    init_db()
    _apply_filters(events, stages, date_from, date_to)
    from src.ui.interactive import _run_analysis
    _run_analysis(match_id)


@legacy_app.command(name="odds")
def odds_cmd(
    match_id: int = typer.Argument(...),
    manual: bool = typer.Option(False, "--manual", "-m"),
    quick: Optional[str] = typer.Option(None, "--quick", "-q"),
    file: Optional[str] = typer.Option(None, "--file", "-f"),
):
    """Collect odds for a match."""
    init_db()
    if quick:
        from src.collectors.manual_input import quick_odds_entry
        quick_odds_entry(match_id, quick)
    elif file:
        from src.collectors.manual_input import file_odds_entry
        file_odds_entry(match_id, file)
    elif manual:
        from src.collectors.manual_input import manual_odds_entry
        manual_odds_entry(match_id)
    else:
        from src.collectors.odds_collector import collect_odds_clawdbot, get_match_description
        desc = get_match_description(match_id) or f"Match {match_id}"
        collect_odds_clawdbot(match_id, desc)


@legacy_app.command()
def veto(
    match_id: int = typer.Argument(...),
    paste: Optional[str] = typer.Option(None, "--paste", "-p"),
    no_sides: bool = typer.Option(False, "--no-sides"),
):
    """Input veto (picks/bans)."""
    init_db()
    from src.collectors.manual_input import manual_veto_input
    manual_veto_input(match_id, paste=paste, skip_sides=no_sides)


@legacy_app.command()
def hedge(
    original_stake: float = typer.Argument(...),
    original_odds: float = typer.Argument(...),
    hedge_odds: float = typer.Argument(...),
):
    """Hedge calculator."""
    from src.analysis.multibets import hedge_calculator
    result = hedge_calculator(original_stake, original_odds, hedge_odds)
    for k, v in result.items():
        console.print(f"  {k}: {v}")


@legacy_app.command()
def dashboard(
    events: Optional[List[int]] = typer.Option(None, "--events", "-e"),
):
    """Show dashboard."""
    init_db()
    if events:
        config.data_filter = DataFilter(event_ids=list(events))
    from src.ui.dashboard import render_dashboard
    render_dashboard()



def _apply_filters(events, stages, date_from, date_to):
    if events or stages or date_from or date_to:
        config.data_filter = DataFilter(
            event_ids=list(events) if events else [],
            stage_names=list(stages) if stages else [],
            date_from=date_from,
            date_to=date_to,
        )


if __name__ == "__main__":
    main()
