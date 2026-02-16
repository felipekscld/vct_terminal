"""Manual input module: odds entry, live veto input, and opinion/notes."""

from __future__ import annotations

from typing import Optional

from rich.console import Console
from rich.prompt import Prompt, FloatPrompt, IntPrompt, Confirm
from rich.table import Table

from src.config import config, VALORANT_MAP_POOL
from src.db.connection import get_db

console = Console()



MARKET_TYPES = [
    "match_winner",
    "map1_winner", "map2_winner", "map3_winner", "map4_winner", "map5_winner",
    "map1_ot", "map2_ot", "map3_ot", "map4_ot", "map5_ot",
    "map1_handicap", "map2_handicap", "map3_handicap",
    "map1_total_rounds", "map2_total_rounds", "map3_total_rounds",
    "correct_score",
    "over_3.5_maps",
]

BOOKMAKERS = ["betano", "bet365"]


def parse_odds_string(odds_str: str) -> list[dict]:
    """Parse a batch odds string into a list of odds dicts.

    Accepted formats (separated by ; or newlines):
        "betano map1_winner MIBR 1.75; bet365 map1_winner MIBR 1.80; betano map1_ot Yes 4.50"

    Each entry: "bookmaker market selection odds"
    """
    entries = []
    raw_parts = odds_str.replace("\n", ";").split(";")

    for part in raw_parts:
        part = part.strip()
        if not part:
            continue

        tokens = part.split()
        if len(tokens) < 4:
            continue

        bookmaker = tokens[0].lower().strip()
        market = tokens[1].lower().strip()
        selection = " ".join(tokens[2:-1])
        try:
            odds_val = float(tokens[-1])
        except ValueError:
            continue

        if odds_val <= 1.0:
            continue

        map_num = None
        if "map" in market:
            digits = "".join(c for c in market if c.isdigit())
            if digits:
                map_num = int(digits)

        entries.append({
            "bookmaker": bookmaker,
            "market_type": market,
            "selection": selection,
            "odds_value": odds_val,
            "map_number": map_num,
        })

    return entries


def batch_odds_insert(match_id: int, entries: list[dict]) -> int:
    """Insert a list of parsed odds entries into the DB. Returns count."""
    count = 0
    with get_db() as conn:
        for o in entries:
            conn.execute(
                """INSERT INTO odds_snapshots
                   (match_id, map_number, bookmaker, market_type, selection, odds_value)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (match_id, o.get("map_number"), o["bookmaker"],
                 o["market_type"], o["selection"], o["odds_value"]),
            )
            count += 1
    return count


def quick_odds_entry(match_id: int, odds_str: str) -> int:
    """Parse and insert odds from a batch string. Returns count."""
    console.print(f"\n[bold cyan]Quick Odds Entry — Match {match_id}[/bold cyan]")
    _show_match_info(match_id)

    entries = parse_odds_string(odds_str)
    if not entries:
        console.print("[red]Could not parse any odds from the string.[/red]")
        console.print("[dim]Format: 'bookmaker market selection odds; ...'[/dim]")
        console.print("[dim]Example: 'betano map1_winner MIBR 1.75; bet365 map1_ot Yes 5.00'[/dim]")
        return 0

    count = batch_odds_insert(match_id, entries)

    table = Table(title=f"{count} odds added", show_header=True)
    table.add_column("Bookmaker")
    table.add_column("Market")
    table.add_column("Selection")
    table.add_column("Odds", justify="right")
    for o in entries:
        table.add_row(o["bookmaker"], o["market_type"], o["selection"], f"{o['odds_value']:.2f}")
    console.print(table)

    return count


def file_odds_entry(match_id: int, file_path: str) -> int:
    """Load odds from a JSON file and insert. Returns count."""
    import json
    from pathlib import Path

    console.print(f"\n[bold cyan]File Odds Entry — Match {match_id}[/bold cyan]")
    _show_match_info(match_id)

    path = Path(file_path)
    if not path.exists():
        console.print(f"[red]File not found: {file_path}[/red]")
        return 0

    with open(path) as f:
        data = json.load(f)

    if not isinstance(data, list):
        console.print("[red]Expected a JSON array of odds objects.[/red]")
        return 0

    entries = []
    for item in data:
        market = str(item.get("market", item.get("market_type", ""))).lower()
        bookmaker = str(item.get("bookmaker", "")).lower()
        selection = str(item.get("selection", ""))
        odds_val = float(item.get("odds", item.get("odds_value", 0)))

        if not bookmaker or not market or odds_val <= 1.0:
            continue

        map_num = None
        if "map" in market:
            digits = "".join(c for c in market if c.isdigit())
            if digits:
                map_num = int(digits)

        entries.append({
            "bookmaker": bookmaker,
            "market_type": market,
            "selection": selection,
            "odds_value": odds_val,
            "map_number": map_num,
        })

    count = batch_odds_insert(match_id, entries)
    console.print(f"[green]Loaded {count} odds from {file_path}.[/green]")
    return count


def manual_odds_entry(match_id: int) -> int:
    """Interactive prompt to manually enter odds for a match. Returns count."""
    console.print(f"\n[bold cyan]Manual Odds Entry — Match {match_id}[/bold cyan]")
    _show_match_info(match_id)

    count = 0
    while True:
        console.print(f"\n[dim]Available markets: {', '.join(MARKET_TYPES)}[/dim]")
        market = Prompt.ask("Market type (or 'done')", default="done")
        if market.lower() == "done":
            break

        bookmaker = Prompt.ask("Bookmaker", choices=BOOKMAKERS, default="betano")
        selection = Prompt.ask("Selection (e.g., 'Fnatic', 'Yes', 'Over 24.5')")
        odds_val = FloatPrompt.ask("Odds (decimal)")

        map_num = None
        if "map" in market.lower():
            try:
                map_num = int("".join(c for c in market if c.isdigit()))
            except ValueError:
                pass

        with get_db() as conn:
            conn.execute(
                """INSERT INTO odds_snapshots
                   (match_id, map_number, bookmaker, market_type, selection, odds_value)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (match_id, map_num, bookmaker, market, selection, odds_val),
            )
        count += 1
        console.print(f"  [green]Added: {bookmaker} {market} {selection} @ {odds_val}[/green]")

    console.print(f"\n[green]Entered {count} odds.[/green]")
    return count



import re

_VETO_PATTERN = re.compile(
    r"([A-Za-z0-9\s\-_ÀÁÂÃÉÊÍÓÔÕÚÜüúùûöòóôõëèéêïìíîäàáâãçñ]+?)\s+"
    r"(ban|pick)\s+"
    r"([A-Za-z0-9\s\-_]+?)(?:\s*;|$)",
    re.IGNORECASE,
)
_REMAINS_PATTERN = re.compile(
    r"([A-Za-z0-9\s\-_]+?)\s+remains\b",
    re.IGNORECASE,
)


def parse_veto_string(
    veto_str: str,
    t1_name: str | None = None,
    t2_name: str | None = None,
    t1_id: int | None = None,
    t2_id: int | None = None,
) -> list[dict]:
    """Parse a VLR-style veto string into a list of actions.

    Accepts the format copied from VLR.gg match pages:
        "MIBR ban Pearl; NRG ban Breeze; MIBR pick Bind; NRG pick Corrode; Haven remains"

    Also handles multi-line (one action per line) and various separators.

    Returns list of dicts with keys: map_order, action, team_id, team_name, map_name
    """
    text = veto_str.replace("\n", "; ").strip()

    actions: list[dict] = []
    order = 0

    team_lookup: dict[str, int | None] = {}
    if t1_name:
        team_lookup[t1_name.lower().strip()] = t1_id
    if t2_name:
        team_lookup[t2_name.lower().strip()] = t2_id

    def resolve_team(raw_name: str) -> tuple[str, int | None]:
        clean = raw_name.strip()
        lower = clean.lower()
        if lower in team_lookup:
            return clean, team_lookup[lower]
        for full_name, tid in team_lookup.items():
            if lower in full_name or full_name in lower:
                return clean, tid
        return clean, None

    for m in _VETO_PATTERN.finditer(text):
        raw_team = m.group(1).strip()
        action = m.group(2).strip().lower()
        map_name = m.group(3).strip()
        start_side = None
        if map_name.endswith(" (Attacker)"):
            map_name = map_name[:-11].strip()
            start_side = "Attacker"
        elif map_name.endswith(" (Defender)"):
            map_name = map_name[:-11].strip()
            start_side = "Defender"

        team_name, team_id = resolve_team(raw_team)
        order += 1
        action_dict = {
            "map_order": order,
            "action": action,
            "team_id": team_id,
            "team_name": team_name,
            "map_name": map_name,
        }
        if start_side:
            action_dict["start_side"] = start_side
        actions.append(action_dict)

    rem = _REMAINS_PATTERN.search(text)
    if rem:
        map_name = rem.group(1).strip()
        order += 1
        actions.append({
            "map_order": order,
            "action": "decider",
            "team_id": None,
            "team_name": "Decider",
            "map_name": map_name,
        })

    return actions


def manual_veto_input(match_id: int, paste: str | None = None, skip_sides: bool = False) -> None:
    """Enter veto for a match.

    If `paste` is provided, parses it directly (VLR copy-paste format).
    Otherwise, opens interactive step-by-step prompt.

    Paste format (copy from VLR.gg):
        "MIBR ban Pearl; NRG ban Breeze; MIBR pick Bind; NRG pick Corrode; Haven remains"
    """
    console.print(f"\n[bold cyan]Manual Veto Input — Match {match_id}[/bold cyan]")

    info = _show_match_info(match_id)
    if not info:
        return

    t1_name = info.get("t1_name", "Team 1")
    t2_name = info.get("t2_name", "Team 2")
    t1_id = info.get("t1_id")
    t2_id = info.get("t2_id")
    bo = info.get("bo_type", "bo3")

    if paste:
        actions = parse_veto_string(paste, t1_name, t2_name, t1_id, t2_id)
        if not actions:
            console.print("[red]Could not parse veto string. Check the format.[/red]")
            console.print("[dim]Expected: 'Team1 ban Map; Team2 ban Map; Team1 pick Map; ... MapX remains'[/dim]")
            return
    else:
        console.print("\n[bold]Options:[/bold]")
        console.print("  [cyan]1)[/cyan] Paste VLR veto string (e.g. 'MIBR ban Pearl; NRG ban Breeze; ...')")
        console.print("  [cyan]2)[/cyan] Enter step by step")
        choice = Prompt.ask("Choose", choices=["1", "2"], default="1")

        if choice == "1":
            console.print("\n[bold]Paste the veto string from VLR.gg:[/bold]")
            paste_input = Prompt.ask("Veto")
            actions = parse_veto_string(paste_input, t1_name, t2_name, t1_id, t2_id)
            if not actions:
                console.print("[red]Could not parse veto string.[/red]")
                return
        else:
            actions = _interactive_veto(t1_name, t2_name, t1_id, t2_id, bo)
            if not actions:
                return

    if not skip_sides:
        picks = [a for a in actions if a["action"] in ("pick", "decider")]
        if picks:
            console.print("\n[bold]Starting sides (optional — press Enter to skip all):[/bold]")
            for i, pick in enumerate(picks, 1):
                label = f"  Map {i} ({pick['map_name']}"
                if pick["action"] == "pick":
                    label += f", {pick['team_name']} pick"
                else:
                    label += ", decider"
                label += ")"

                side = Prompt.ask(f"{label} [ATK/DEF/skip]", default="skip")
                if side.upper() in ("ATK", "DEF", "ATTACKER", "DEFENDER"):
                    pick["start_side"] = "Attacker" if side.upper().startswith("A") else "Defender"

    _save_veto(match_id, actions)

    console.print("\n[green]Veto saved![/green]")
    _display_veto_summary(actions)


def _interactive_veto(
    t1_name: str, t2_name: str,
    t1_id: int | None, t2_id: int | None,
    bo: str,
) -> list[dict]:
    """Step-by-step interactive veto input."""
    available = VALORANT_MAP_POOL.copy()
    actions: list[dict] = []
    order = 0

    console.print(f"\n[bold]Map Pool:[/bold] {', '.join(available)}")

    if "5" in str(bo):
        veto_sequence = [
            ("ban", t1_name, t1_id), ("ban", t2_name, t2_id),
            ("pick", t1_name, t1_id), ("pick", t2_name, t2_id),
            ("pick", t2_name, t2_id), ("pick", t1_name, t1_id),
            ("decider", None, None),
        ]
    else:
        veto_sequence = [
            ("ban", t1_name, t1_id), ("ban", t2_name, t2_id),
            ("pick", t1_name, t1_id), ("pick", t2_name, t2_id),
            ("ban", t1_name, t1_id), ("ban", t2_name, t2_id),
            ("decider", None, None),
        ]

    console.print("\n[bold]Enter veto step by step:[/bold]")
    for action, team_name, team_id in veto_sequence:
        if not available:
            break

        if action == "decider":
            if len(available) == 1:
                map_name = available[0]
                console.print(f"  [yellow]Decider:[/yellow] {map_name}")
            else:
                console.print(f"  Available: {', '.join(available)}")
                map_name = Prompt.ask("  Decider map", choices=available)
        else:
            label = f"  {team_name} {action}"
            console.print(f"  Available: {', '.join(available)}")
            map_name = Prompt.ask(label, choices=available)

        available.remove(map_name)
        order += 1
        actions.append({
            "map_order": order,
            "action": action,
            "team_id": team_id,
            "team_name": team_name or "Decider",
            "map_name": map_name,
        })

    return actions


def _save_veto(match_id: int, actions: list[dict]) -> None:
    """Save veto actions to DB."""
    with get_db() as conn:
        conn.execute(
            "DELETE FROM pending_vetos WHERE match_id = ? AND source = 'manual'",
            (match_id,),
        )
        for a in actions:
            conn.execute(
                """INSERT INTO pending_vetos
                   (match_id, source, map_order, action, team_id, team_name, map_name, start_side)
                   VALUES (?, 'manual', ?, ?, ?, ?, ?, ?)""",
                (
                    match_id, a["map_order"], a["action"],
                    a.get("team_id"), a["team_name"], a["map_name"],
                    a.get("start_side"),
                ),
            )


def update_side(match_id: int, map_name: str, team_name: str, side: str) -> None:
    """Update the starting side for a specific map in the veto."""
    side_val = "Attacker" if side.upper().startswith("A") else "Defender"
    with get_db() as conn:
        conn.execute(
            """UPDATE pending_vetos SET start_side = ?
               WHERE match_id = ? AND map_name = ? AND action IN ('pick', 'decider')""",
            (side_val, match_id, map_name),
        )
    console.print(f"[green]Updated {map_name}: {team_name} starts {side_val}[/green]")



def add_opinion(match_id: int, map_id: int | None = None) -> None:
    """Add a manual opinion/note for a match or map."""
    console.print(f"\n[bold cyan]Add Opinion — Match {match_id}[/bold cyan]")
    note = Prompt.ask("Your note")
    confidence = Prompt.ask("Confidence", choices=["low", "medium", "high"], default="medium")

    with get_db() as conn:
        conn.execute(
            "INSERT INTO manual_opinions (match_id, map_id, note, confidence) VALUES (?, ?, ?, ?)",
            (match_id, map_id, note, confidence),
        )
    console.print("[green]Opinion saved.[/green]")



def _show_match_info(match_id: int) -> Optional[dict]:
    """Display match info and return dict with key fields."""
    with get_db() as conn:
        row = conn.execute(
            """SELECT m.id, m.bo_type, m.date, m.status,
                      t1.name as t1_name, t1.id as t1_id,
                      t2.name as t2_name, t2.id as t2_id,
                      e.name as event_name, m.stage_name
               FROM matches m
               LEFT JOIN teams t1 ON m.team1_id = t1.id
               LEFT JOIN teams t2 ON m.team2_id = t2.id
               LEFT JOIN events e ON m.event_id = e.id
               WHERE m.id = ?""",
            (match_id,),
        ).fetchone()

    if not row:
        console.print(f"[red]Match {match_id} not found in DB.[/red]")
        return None

    console.print(f"  [bold]{row['t1_name']} vs {row['t2_name']}[/bold]")
    console.print(f"  Event: {row['event_name'] or 'N/A'} | Stage: {row['stage_name'] or 'N/A'}")
    console.print(f"  Format: {row['bo_type'] or 'N/A'} | Date: {row['date'] or 'N/A'}")

    return dict(row)


def _display_veto_summary(actions: list[dict]) -> None:
    """Pretty-print the veto summary."""
    table = Table(title="Veto Summary")
    table.add_column("#", style="dim")
    table.add_column("Action")
    table.add_column("Team")
    table.add_column("Map")
    table.add_column("Side")

    pick_num = 0
    for a in actions:
        side = a.get("start_side", "")
        if a["action"] in ("pick", "decider"):
            pick_num += 1
            table.add_row(
                f"Map {pick_num}", a["action"].upper(), a["team_name"],
                a["map_name"], side or "-",
            )
        else:
            table.add_row("-", a["action"].upper(), a["team_name"], a["map_name"], "-")

    console.print(table)
