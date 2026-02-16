"""Parse Clawdbot odds output into structured data and insert into DB."""

from __future__ import annotations

import json
from typing import Any

from src.db.connection import get_db


def _extract_json_array(raw: str) -> str:
    """Extract a JSON array from text that may contain markdown or wrapper text."""
    raw = raw.strip()
    if "```" in raw:
        lines = raw.split("\n")
        out = []
        in_block = False
        for line in lines:
            if line.strip().startswith("```"):
                in_block = not in_block
                continue
            if in_block or not line.strip().startswith("```"):
                out.append(line)
        raw = "\n".join(out)
    start = raw.find("[")
    if start == -1:
        return raw
    depth = 0
    in_string = None
    escape = False
    for i in range(start, len(raw)):
        c = raw[i]
        if escape:
            escape = False
            continue
        if c == "\\" and in_string:
            escape = True
            continue
        if in_string:
            if c == in_string:
                in_string = None
            continue
        if c in ('"', "'"):
            in_string = c
            continue
        if c == "[":
            depth += 1
        elif c == "]":
            depth -= 1
            if depth == 0:
                return raw[start : i + 1]
    return raw[start:]


def parse_odds_json(raw: str) -> list[dict[str, Any]]:
    """Parse JSON string from OpenClaw/Clawdbot output into a list of odds dicts."""
    raw = raw.strip()
    raw = _extract_json_array(raw)

    data = json.loads(raw)
    if not isinstance(data, list):
        raise ValueError("Expected a JSON array of odds objects.")

    validated = []
    for item in data:
        entry = {
            "bookmaker": str(item.get("bookmaker", "")).lower().strip(),
            "market_type": str(item.get("market_type", "")).lower().strip(),
            "selection": str(item.get("selection", "")),
            "odds_value": float(item.get("odds_value", 0)),
            "map_number": item.get("map_number"),
        }
        if entry["bookmaker"] and entry["market_type"] and entry["odds_value"] > 0:
            validated.append(entry)

    return validated


def insert_odds(match_id: int, odds_list: list[dict[str, Any]]) -> int:
    """Insert parsed odds into the odds_snapshots table. Returns count inserted."""
    count = 0
    with get_db() as conn:
        for o in odds_list:
            try:
                conn.execute(
                    """INSERT INTO odds_snapshots
                       (match_id, map_number, bookmaker, market_type, selection, odds_value)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (
                        match_id,
                        o.get("map_number"),
                        o["bookmaker"],
                        o["market_type"],
                        o["selection"],
                        o["odds_value"],
                    ),
                )
                count += 1
            except Exception as e:
                print(f"Failed to insert odds {o}: {e}")
    return count
