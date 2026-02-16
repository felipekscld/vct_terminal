"""Color theme and style constants for the terminal UI."""

from rich.theme import Theme

VCT_THEME = Theme({
    "header": "bold white on dark_red",
    "subheader": "bold cyan",
    "edge.strong": "bold green",
    "edge.weak": "yellow",
    "edge.none": "dim white",
    "arb": "bold magenta",
    "team_a": "bold bright_cyan",
    "team_b": "bold bright_yellow",
    "map_name": "bold white",
    "filter_active": "bold green",
    "filter_label": "dim cyan",
    "odds.betano": "bright_green",
    "odds.bet365": "bright_yellow",
    "stat_value": "white",
    "stat_label": "dim",
    "panel_border": "bright_black",
    "warning": "bold yellow",
    "error": "bold red",
    "success": "bold green",
    "multi.spread": "bold blue",
    "multi.parlay": "bold magenta",
    "multi.hedge": "bold cyan",
    "bankroll": "bold green",
})

EDGE_LABELS = {
    "EDGE FORTE": "[edge.strong]EDGE FORTE[/edge.strong]",
    "OBSERVAR": "[edge.weak]OBSERVAR[/edge.weak]",
    "SEM EDGE": "[edge.none]SEM EDGE[/edge.none]",
}

STRATEGY_LABELS = {
    "spread": "[multi.spread]SPREAD[/multi.spread]",
    "parlay": "[multi.parlay]PARLAY[/multi.parlay]",
    "hedge": "[multi.hedge]HEDGE[/multi.hedge]",
    "correct_score": "[multi.parlay]CORRECT SCORE[/multi.parlay]",
}
