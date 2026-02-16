"""OpenClaw/Clawdbot integration for odds collection from Betano and Bet365."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Optional

from rich.console import Console

from src.clawdbot.odds_parser import parse_odds_json, insert_odds
from src.db.connection import get_db

console = Console()

SKILL_PATH = Path(__file__).resolve().parent.parent / "clawdbot" / "skill_odds.md"

OPENCLAW_CMD = "openclaw"


def collect_odds_clawdbot(match_id: int, match_description: str) -> int:
    """Use OpenClaw agent to collect odds for a match (Betano/Bet365).
    Returns number of odds entries collected."""
    console.print(f"[cyan]Launching OpenClaw for odds: {match_description}[/cyan]")

    if not SKILL_PATH.exists():
        console.print(f"[red]Skill file not found: {SKILL_PATH}[/red]")
        console.print("[yellow]Falling back to manual input.[/yellow]")
        return 0

    prompt = (
        f"Follow the skill instructions in {SKILL_PATH} to extract odds for:\n"
        f"{match_description}\n\n"
        f"Return ONLY the JSON array as described in the skill."
    )

    try:
        result = subprocess.run(
            [OPENCLAW_CMD, "--session-id", "main", "--message", prompt],
            capture_output=True,
            text=True,
            timeout=180,
        )

        if result.returncode != 0:
            console.print(f"[red]OpenClaw error: {result.stderr}[/red]")
            console.print("[yellow]Falling back to manual input.[/yellow]")
            return 0

        odds_list = parse_odds_json(result.stdout)
        count = insert_odds(match_id, odds_list)
        console.print(f"[green]Collected {count} odds entries via OpenClaw.[/green]")
        return count

    except FileNotFoundError:
        console.print("[yellow]OpenClaw not found (openclaw not in PATH). Use manual odds or batch paste.[/yellow]")
        return 0
    except subprocess.TimeoutExpired:
        console.print("[red]OpenClaw timed out after 180s.[/red]")
        return 0
    except Exception as e:
        console.print(f"[red]Error running OpenClaw: {e}[/red]")
        return 0


def get_match_description(match_id: int) -> Optional[str]:
    """Build a human-readable match description from DB."""
    with get_db() as conn:
        row = conn.execute(
            """SELECT m.id, t1.name as t1_name, t2.name as t2_name,
                      e.name as event_name, m.stage_name, m.bo_type
               FROM matches m
               LEFT JOIN teams t1 ON m.team1_id = t1.id
               LEFT JOIN teams t2 ON m.team2_id = t2.id
               LEFT JOIN events e ON m.event_id = e.id
               WHERE m.id = ?""",
            (match_id,),
        ).fetchone()

        if not row:
            return None

        parts = []
        if row["t1_name"] and row["t2_name"]:
            parts.append(f"{row['t1_name']} vs {row['t2_name']}")
        if row["event_name"]:
            parts.append(row["event_name"])
        if row["stage_name"]:
            parts.append(row["stage_name"])
        if row["bo_type"]:
            parts.append(row["bo_type"])

        return " - ".join(parts) if parts else f"Match {match_id}"
