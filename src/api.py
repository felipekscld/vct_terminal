"""FastAPI backend for the VCT Web App.

This API wraps the existing analysis engine, collectors, and SQLite data.
"""

from __future__ import annotations

import json
import re
import shutil
import time
from dataclasses import asdict, is_dataclass
from datetime import datetime
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, model_validator

from src.analysis.arbitrage import detect_arbitrage
from src.analysis.compositions import get_team_likely_comp
from src.analysis.edge import analyze_market_edges, build_market_probs
from src.analysis.maps import get_h2h_stats, get_team_map_stats
from src.analysis.multibets import (
    analyze_spread,
    correct_score_coverage,
    find_cross_match_parlays,
    find_profitable_parlays,
    hedge_calculator,
)
from src.analysis.probability import estimate_map_win, estimate_ot_prob, simulate_series
from src.collectors.manual_input import parse_veto_string
from src.collectors.odds_collector import collect_odds_clawdbot, get_match_description
from src.collectors.vlr_collector import full_sync
from src.config import ALL_MARKET_TYPES, MARKET_LABELS, VALORANT_MAP_POOL, config, DataFilter
from src.db.connection import get_db
from src.db.schema import init_db


APP_CONFIG_KEY = "app_config"


class VetoActionIn(BaseModel):
    map_order: int
    action: str
    team_id: int | None = None
    team_name: str | None = None
    map_name: str
    start_side: str | None = None


class VetoUpsertRequest(BaseModel):
    veto_text: str | None = None
    actions: list[VetoActionIn] | None = None

    @model_validator(mode="after")
    def validate_payload(self) -> "VetoUpsertRequest":
        if not self.veto_text and not self.actions:
            raise ValueError("Provide veto_text or actions")
        return self


class OddsEntryIn(BaseModel):
    bookmaker: str
    market_type: str
    selection: str
    odds_value: float = Field(gt=1.0)
    map_number: int | None = None


class OddsBatchRequest(BaseModel):
    entries: list[OddsEntryIn] = Field(default_factory=list)


class OddsAutoRequest(BaseModel):
    force: bool = False


class LiveMapResultRequest(BaseModel):
    map_number: int = Field(ge=1)
    map_name: str | None = None
    winner_side: Literal["a", "b"]
    score_a: int | None = Field(default=None, ge=0)
    score_b: int | None = Field(default=None, ge=0)


class SyncRequest(BaseModel):
    event_id: int | None = None
    deep: bool = True
    event_status: str | None = None


class DataFilterUpdate(BaseModel):
    event_ids: list[int] | None = None
    stage_names: list[str] | None = None
    date_from: str | None = None
    date_to: str | None = None


class BankrollUpdate(BaseModel):
    total: float | None = None
    max_stake_pct: float | None = None
    daily_limit: float | None = None
    event_limit: float | None = None
    kelly_fraction: float | None = None


class EdgeUpdate(BaseModel):
    min_edge: float | None = None
    strong_edge: float | None = None
    min_confidence: str | None = None
    min_sample_map: int | None = None
    min_sample_general: int | None = None


class MarketsUpdate(BaseModel):
    enabled_markets: list[str] | None = None


class LiveUpdate(BaseModel):
    betano_live: bool | None = None
    bet365_live: bool | None = None
    show_live_opportunities: bool | None = None
    auto_recalc_on_map_result: bool | None = None


class AppConfigUpdateRequest(BaseModel):
    data_filter: DataFilterUpdate | None = None
    bankroll: BankrollUpdate | None = None
    edge: EdgeUpdate | None = None
    markets: MarketsUpdate | None = None
    live: LiveUpdate | None = None


app = FastAPI(title="VCT Web API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:4173",
        "http://127.0.0.1:4173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup() -> None:
    init_db()
    _load_persisted_config()


@app.exception_handler(HTTPException)
async def http_exception_handler(_, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": "http_error", "detail": exc.detail},
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(_, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={"error": "validation_error", "detail": exc.errors()},
    )


@app.exception_handler(Exception)
async def generic_exception_handler(_, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"error": "internal_error", "detail": str(exc)},
    )


@app.get("/api/health")
def health() -> dict[str, Any]:
    try:
        with get_db() as conn:
            conn.execute("SELECT 1")
        return {"status": "ok", "db_ok": True}
    except Exception:
        return {"status": "error", "db_ok": False}


@app.get("/api/events")
def events(from_year: int | None = Query(None, description="Show events from this year onward; default 2026")) -> dict[str, Any]:
    year = from_year if from_year is not None else 2026
    date_cutoff = f"{year}-01-01"
    with get_db() as conn:
        rows = conn.execute(
            """SELECT id, name, region, tier, status, start_date, end_date, prize
               FROM events
               WHERE (start_date IS NULL OR start_date >= ?)
               ORDER BY start_date DESC, id DESC""",
            (date_cutoff,),
        ).fetchall()
    return {"items": [dict(r) for r in rows]}


REGION_TEAM_NAMES_2026: dict[str, list[str]] = {
    "Americas": [
        "100 thieves", "cloud9", "evil geniuses", "furia", "kru esports", "leviatan",
        "loud", "mibr", "nrg", "sentinels", "g2 esports", "envy",
    ],
    "China": [
        "all gamers", "bilibili gaming", "edward gaming", "funplus phoenix", "jd gaming",
        "nova esports", "titan esports club", "trace esports", "tyloo", "wolves esports",
        "dragon ranger gaming", "xlg esports",
    ],
    "EMEA": [
        "bbl esports", "fnatic", "fut esports", "karmine corp", "natus vincere",
        "team heretics", "team liquid", "team vitality", "giantx", "gentle mates",
        "ulf esports", "pcific esports",
    ],
    "Pacific": [
        "detonation focusme", "drx", "gen.g", "gen.g esports", "global esports", "paper rex",
        "rex regum qeon", "t1", "team secret", "zeta division", "full sense",
        "nongshim redforce", "varrel",
    ],
}

TEAM_NAME_TO_TAG: dict[str, str] = {
    "100 thieves": "100T", "cloud9": "C9", "evil geniuses": "EG", "furia": "FURIA",
    "kru esports": "KRU", "leviatan": "LEV", "loud": "LOUD", "mibr": "MIBR",
    "nrg": "NRG", "sentinels": "SEN", "g2 esports": "G2", "envy": "ENVY",
    "all gamers": "AG", "bilibili gaming": "BLG", "edward gaming": "EDG",
    "funplus phoenix": "FPX", "jd gaming": "JDG", "nova esports": "NOVA",
    "titan esports club": "TEC", "trace esports": "TRC", "tyloo": "TYLOO",
    "wolves esports": "WOLVES", "dragon ranger gaming": "DRG", "xlg esports": "XLG",
    "bbl esports": "BBL", "fnatic": "FNC", "fut esports": "FUT", "karmine corp": "KC",
    "natus vincere": "NAVI", "team heretics": "TH", "team liquid": "TL",
    "team vitality": "VIT", "giantx": "GX", "gentle mates": "GM",
    "ulf esports": "ULF", "pcific esports": "PCF",
    "detonation focusme": "DFM", "drx": "DRX", "gen.g": "GEN", "gen.g esports": "GEN",
    "global esports": "GE", "paper rex": "PRX", "rex regum qeon": "RRQ", "t1": "T1",
    "team secret": "TS", "zeta division": "ZETA", "full sense": "FS",
    "nongshim redforce": "NS", "varrel": "VARREL",
}


def _team_display_tag(name: str | None, tag: str | None) -> str:
    """Return tag for display; use canonical sigla when DB tag is missing."""
    if tag and str(tag).strip():
        return str(tag).strip()
    if name:
        key = name.strip().lower()
        return TEAM_NAME_TO_TAG.get(key) or name.strip()
    return "?"


@app.get("/api/teams")
def list_teams(region: str | None = None) -> dict[str, Any]:
    """List teams (id, name, tag) for dropdowns. tag is always a sigla (from DB or canonical map)."""
    with get_db() as conn:
        if region and region.lower() != "all":
            names = REGION_TEAM_NAMES_2026.get(region)
            if names:
                placeholders = ",".join("?" for _ in names)
                rows = conn.execute(
                    f"""SELECT id, name, tag FROM teams
                       WHERE LOWER(TRIM(name)) IN ({placeholders})
                       ORDER BY name""",
                    names,
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT id, name, tag FROM teams ORDER BY name"
                ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, name, tag FROM teams ORDER BY name"
            ).fetchall()
    items = []
    for r in rows:
        d = dict(r)
        d["tag"] = _team_display_tag(d.get("name"), d.get("tag"))
        items.append(d)
    return {"items": items}


@app.get("/api/maps")
def list_maps() -> dict[str, Any]:
    """List Valorant map pool for dropdowns."""
    return {"items": list(VALORANT_MAP_POOL)}


@app.get("/api/markets")
def list_markets() -> dict[str, Any]:
    """List available betting market types (id + label) for Settings."""
    return {
        "items": [{"id": m, "label": MARKET_LABELS.get(m, m)} for m in ALL_MARKET_TYPES],
    }


@app.get("/api/matches")
def list_matches(
    event_id: list[int] = Query(default_factory=list),
    status: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    from_year: int | None = Query(None, description="Show matches from this year onward; default 2026"),
    limit: int = Query(default=50, ge=1, le=500),
) -> dict[str, Any]:
    conditions = ["1=1"]
    params: list[Any] = []

    if event_id:
        placeholders = ",".join("?" for _ in event_id)
        conditions.append(f"m.event_id IN ({placeholders})")
        params.extend(event_id)
    if status:
        conditions.append("m.status = ?")
        params.append(status)
    if date_from:
        conditions.append("m.date >= ?")
        params.append(date_from)
    if date_to:
        conditions.append("m.date <= ?")
        params.append(date_to)

    year = from_year if from_year is not None else 2026
    date_cutoff = f"{year}-01-01"
    conditions.append("(m.date IS NULL OR m.date >= ?)")
    params.append(date_cutoff)

    where = " AND ".join(conditions)

    with get_db() as conn:
        rows = conn.execute(
            f"""SELECT m.id, m.event_id, m.stage_name, m.phase, m.date, m.time,
                       m.bo_type, m.status, m.score1, m.score2,
                       t1.id AS team1_id, t1.name AS team1_name, t1.tag AS team1_tag,
                       t2.id AS team2_id, t2.name AS team2_name, t2.tag AS team2_tag,
                       e.name AS event_name
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
                    m.date DESC,
                    m.id DESC
                LIMIT ?""",
            [*params, limit],
        ).fetchall()

    items = []
    for r in rows:
        d = dict(r)
        d["team1_tag"] = _team_display_tag(d.get("team1_name"), d.get("team1_tag"))
        d["team2_tag"] = _team_display_tag(d.get("team2_name"), d.get("team2_tag"))
        items.append(d)
    return {"items": items}


@app.get("/api/matches/{match_id}")
def match_detail(match_id: int) -> dict[str, Any]:
    info = _get_match_info(match_id)
    if not info:
        raise HTTPException(status_code=404, detail=f"Match {match_id} not found")

    with get_db() as conn:
        veto_rows = conn.execute(
            """SELECT source, map_order, action, team_id, team_name, map_name, start_side
               FROM pending_vetos
               WHERE match_id = ?
               ORDER BY CASE source WHEN 'manual' THEN 0 ELSE 1 END, map_order""",
            (match_id,),
        ).fetchall()

        odds_count = conn.execute(
            "SELECT COUNT(*) AS c FROM odds_snapshots WHERE match_id = ?",
            (match_id,),
        ).fetchone()["c"]

        veto_list = [dict(v) for v in veto_rows]
        _enrich_veto_with_start_side(match_id, veto_list, conn=conn)
        veto_markdown = _veto_to_markdown(veto_list) if veto_list else ""

    return {
        "match": info,
        "veto": veto_list,
        "veto_markdown": veto_markdown,
        "odds_count": odds_count,
    }


@app.get("/api/matches/{match_id}/analysis")
def match_analysis(match_id: int) -> dict[str, Any]:
    return _build_match_analysis(match_id)


@app.get("/api/analysis/cross-match-parlays")
def cross_match_parlays(
    date_from: str | None = Query(None, description="From date (YYYY-MM-DD); default today"),
    date_to: str | None = Query(None, description="To date (YYYY-MM-DD); default tomorrow"),
    max_legs: int = Query(4, ge=2, le=5, description="Max legs (matches) per parlay"),
) -> dict[str, Any]:
    """Suggest parlays with one leg per game (different matches). Uses upcoming matches that have odds."""
    from datetime import date, timedelta

    today = date.today().isoformat()
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    d_from = date_from or today
    d_to = date_to or tomorrow

    with get_db() as conn:
        rows = conn.execute(
            """SELECT DISTINCT m.id
               FROM matches m
               WHERE m.date >= ? AND m.date <= ?
                 AND m.status IN ('upcoming', 'ongoing')
                 AND EXISTS (SELECT 1 FROM odds_snapshots o WHERE o.match_id = m.id)
               ORDER BY m.date, m.id
               LIMIT 20""",
            (d_from, d_to),
        ).fetchall()
    match_ids = [r["id"] for r in rows]

    matches_edges = []
    for mid in match_ids:
        label, edges = _get_match_edges_for_cross_parlay(mid)
        if label and edges:
            matches_edges.append({"match_id": mid, "match_label": label, "edges": edges})

    parlays = find_cross_match_parlays(matches_edges, max_legs=max_legs)

    with get_db() as conn2:
        upcoming = []
        for mid in match_ids:
            row = conn2.execute(
                """SELECT m.id, m.date, m.time, m.bo_type, m.status,
                          t1.name AS t1_name, t1.tag AS t1_tag,
                          t2.name AS t2_name, t2.tag AS t2_tag,
                          e.name AS event_name
                   FROM matches m
                   LEFT JOIN teams t1 ON m.team1_id = t1.id
                   LEFT JOIN teams t2 ON m.team2_id = t2.id
                   LEFT JOIN events e ON m.event_id = e.id
                   WHERE m.id = ?""",
                (mid,),
            ).fetchone()
            if row:
                r = dict(row)
                r["team1_display"] = r.get("t1_tag") or r.get("t1_name") or "?"
                r["team2_display"] = r.get("t2_tag") or r.get("t2_name") or "?"
                upcoming.append(r)

    return {
        "date_from": d_from,
        "date_to": d_to,
        "upcoming_matches": upcoming,
        "matches_with_edges": len(matches_edges),
        "cross_match_parlays": _serialize(parlays),
    }


def _get_match_edges_for_cross_parlay(match_id: int) -> tuple[str | None, list[dict[str, Any]]]:
    """Return (match_label, list of positive edge dicts) for use in cross-match parlays. None if no info/odds."""
    info = _get_match_info(match_id)
    if not info:
        return None, []
    t1 = info.get("team1_tag") or info.get("team1_name") or "?"
    t2 = info.get("team2_tag") or info.get("team2_name") or "?"
    label = f"{t1} vs {t2}"
    bo_type = info.get("bo_type") or "bo3"
    map_list = _get_veto_maps(match_id, bo_type)
    team_a_id = info["team1_id"]
    team_b_id = info["team2_id"]

    map_analyses = []
    ot_results = []
    map_probs_a = []
    for m in map_list:
        map_name = m["map_name"]
        ma = estimate_map_win(
            team_a_id,
            team_b_id,
            map_name,
            starting_side_a=m.get("start_side"),
            data_filter=config.data_filter,
            bo_type=bo_type,
        )
        ot = estimate_ot_prob(
            team_a_id, team_b_id, map_name,
            data_filter=config.data_filter,
            bo_type=bo_type,
        )
        map_analyses.append(ma)
        ot_results.append(ot)
        map_probs_a.append(ma.p_team_a_win)

    maps_to_win = 3 if "5" in str(bo_type).lower() else 2
    series_result = simulate_series(map_probs_a, maps_to_win=maps_to_win)
    market_probs = build_market_probs(map_analyses, series_result, ot_results)
    single_edges = analyze_market_edges(match_id, market_probs)

    positive = []
    for e in single_edges:
        if getattr(e, "edge", 0) and float(getattr(e, "edge", 0)) > 0:
            positive.append({
                "market": getattr(e, "market", ""),
                "selection": getattr(e, "selection", ""),
                "p_model": float(getattr(e, "p_model", 0)),
                "odds": float(getattr(e, "odds", 0)),
                "bookmaker": getattr(e, "bookmaker", ""),
                "confidence": getattr(e, "confidence", ""),
                "edge": float(getattr(e, "edge", 0)),
            })
    return label, positive


@app.post("/api/matches/{match_id}/veto")
def upsert_veto(match_id: int, payload: VetoUpsertRequest) -> dict[str, Any]:
    info = _get_match_info(match_id)
    if not info:
        raise HTTPException(status_code=404, detail=f"Match {match_id} not found")

    if payload.veto_text:
        actions_raw = parse_veto_string(
            payload.veto_text,
            info.get("team1_name"),
            info.get("team2_name"),
            info.get("team1_id"),
            info.get("team2_id"),
        )
        if not actions_raw:
            raise HTTPException(status_code=422, detail="Unable to parse veto_text")
        actions = [VetoActionIn(**a) for a in actions_raw]
    else:
        actions = payload.actions or []

    saved = _save_manual_veto(match_id, actions)
    maps = [
        {
            "map_order": a.map_order,
            "map_name": a.map_name,
            "action": a.action,
            "pick_team": a.team_name,
            "start_side": a.start_side,
        }
        for a in actions
        if a.action.lower() in ("pick", "decider")
    ]
    return {"saved_count": saved, "maps": maps}


@app.post("/api/matches/{match_id}/odds")
def upsert_odds(match_id: int, payload: OddsBatchRequest) -> dict[str, Any]:
    if not _match_exists(match_id):
        raise HTTPException(status_code=404, detail=f"Match {match_id} not found")

    inserted = 0
    with get_db() as conn:
        for entry in payload.entries:
            map_number = entry.map_number or _infer_map_number(entry.market_type)
            conn.execute(
                """INSERT INTO odds_snapshots
                   (match_id, map_number, bookmaker, market_type, selection, odds_value)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    match_id,
                    map_number,
                    entry.bookmaker.lower().strip(),
                    entry.market_type.lower().strip(),
                    entry.selection.strip(),
                    entry.odds_value,
                ),
            )
            inserted += 1
    return {"inserted": inserted}


@app.get("/api/matches/{match_id}/odds")
def get_odds(
    match_id: int,
    latest_only: str = Query("true", description="Deduplicate to latest odds per market"),
) -> dict[str, Any]:
    if not _match_exists(match_id):
        raise HTTPException(status_code=404, detail=f"Match {match_id} not found")

    with get_db() as conn:
        rows = conn.execute(
            """SELECT id, match_id, map_number, bookmaker, market_type, selection,
                      odds_value, timestamp
               FROM odds_snapshots
               WHERE match_id = ?
               ORDER BY timestamp DESC, id DESC""",
            (match_id,),
        ).fetchall()

    items = [dict(r) for r in rows]
    dedup_latest = latest_only.lower() not in ("0", "false", "no")
    if dedup_latest:
        dedup: dict[tuple[Any, ...], dict[str, Any]] = {}
        for item in items:
            key = (
                item["map_number"],
                item["bookmaker"],
                item["market_type"],
                item["selection"],
            )
            if key not in dedup:
                dedup[key] = item
        items = list(dedup.values())

    return {"items": items}


@app.post("/api/matches/{match_id}/odds/auto")
def auto_odds(match_id: int, payload: OddsAutoRequest | None = None):
    if not _match_exists(match_id):
        raise HTTPException(status_code=404, detail=f"Match {match_id} not found")

    force = payload.force if payload else False

    if not shutil.which("openclaw"):
        raise HTTPException(
            status_code=503,
            detail="openclaw command is not installed or not in PATH. Use POST /api/matches/{id}/odds with manual entries or batch paste in the web Odds Form.",
        )

    desc = get_match_description(match_id) or f"Match {match_id}"
    start = time.perf_counter()

    inserted = collect_odds_clawdbot(match_id, desc)
    duration_ms = round((time.perf_counter() - start) * 1000, 2)

    if inserted <= 0 and not force:
        return JSONResponse(
            status_code=502,
            content={
                "error": "openclaw_failed",
                "detail": "No odds were inserted from OpenClaw output",
                "fallback_steps": [
                    "Confirm OpenClaw can access bookmaker pages",
                    "Retry endpoint with {\"force\": true} if you only want timing",
                    "Fallback to POST /api/matches/{id}/odds manual batch",
                ],
            },
        )

    return {
        "inserted": inserted,
        "source": "openclaw",
        "duration_ms": duration_ms,
    }


@app.post("/api/matches/{match_id}/live/map-result")
def save_live_map_result(match_id: int, payload: LiveMapResultRequest) -> dict[str, Any]:
    info = _get_match_info(match_id)
    if not info:
        raise HTTPException(status_code=404, detail=f"Match {match_id} not found")

    map_name = payload.map_name
    if not map_name:
        veto_maps = _get_veto_maps(match_id, info.get("bo_type") or "bo3")
        idx = payload.map_number - 1
        map_name = veto_maps[idx]["map_name"] if idx < len(veto_maps) else f"Map {payload.map_number}"

    winner_team_id = info["team1_id"] if payload.winner_side == "a" else info["team2_id"]

    with get_db() as conn:
        conn.execute(
            """INSERT INTO live_map_results
               (match_id, map_number, map_name, winner_team_id, winner_team_side, score_a, score_b, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))
               ON CONFLICT(match_id, map_number) DO UPDATE SET
                 map_name=excluded.map_name,
                 winner_team_id=excluded.winner_team_id,
                 winner_team_side=excluded.winner_team_side,
                 score_a=excluded.score_a,
                 score_b=excluded.score_b,
                 updated_at=datetime('now')""",
            (
                match_id,
                payload.map_number,
                map_name,
                winner_team_id,
                payload.winner_side,
                payload.score_a,
                payload.score_b,
            ),
        )

    return {
        "saved": True,
        "state": _get_live_state(match_id),
    }


@app.get("/api/matches/{match_id}/live/series-prob")
def live_series_prob(match_id: int) -> dict[str, Any]:
    if not _match_exists(match_id):
        raise HTTPException(status_code=404, detail=f"Match {match_id} not found")
    return _calculate_live_series_prob(match_id)


@app.get("/api/stats/team/{team_id}")
def team_stats(team_id: int, map_name: str | None = None) -> dict[str, Any]:
    with get_db() as conn:
        team = conn.execute("SELECT id, name, tag FROM teams WHERE id = ?", (team_id,)).fetchone()
    if not team:
        raise HTTPException(status_code=404, detail=f"Team {team_id} not found")

    maps = [map_name] if map_name else VALORANT_MAP_POOL
    all_data = DataFilter()
    map_stats = []
    for mn in maps:
        stats = get_team_map_stats(team_id, mn, data_filter=all_data)
        d = asdict(stats)
        if d["games_played"] > 0 or map_name:
            likely_comps = get_team_likely_comp(team_id, mn, data_filter=all_data, limit=2)
            d["likely_compositions"] = likely_comps
            map_stats.append(d)

    overall = _aggregate_team_stats(team_id, None, data_filter=all_data)
    return {
        "team": dict(team),
        "overall": overall,
        "map_stats": map_stats,
    }


@app.get("/api/stats/query")
def stats_query(q: str) -> dict[str, Any]:
    stat_type = _detect_stat_type(q)
    teams = _find_teams(q)
    map_name = _find_map(q)

    if not stat_type and teams:
        stat_type = "overview"

    if not stat_type and not teams:
        return {"intent": None, "teams": [], "map_name": map_name, "result": None}

    result = _run_stats_query(stat_type or "overview", teams, map_name)
    return {
        "intent": stat_type,
        "teams": teams,
        "map_name": map_name,
        "result": result,
    }


@app.get("/api/stats/h2h")
def stats_h2h(a: int, b: int, map_name: str | None = None) -> dict[str, Any]:
    return get_h2h_stats(a, b, map_name=map_name, data_filter=DataFilter())


@app.post("/api/sync")
def sync(payload: SyncRequest) -> dict[str, Any]:
    before = _db_counts()
    full_sync(event_id=payload.event_id, deep=payload.deep, event_status=payload.event_status)
    after = _db_counts()

    return {
        "ok": True,
        "synced_events": max(0, after["events"] - before["events"]),
        "synced_matches": max(0, after["matches"] - before["matches"]),
        "synced_maps": max(0, after["maps"] - before["maps"]),
    }


@app.get("/api/config")
def get_config() -> dict[str, Any]:
    _load_persisted_config()
    return _export_config()


@app.put("/api/config")
def put_config(payload: AppConfigUpdateRequest) -> dict[str, Any]:
    _load_persisted_config()

    if payload.data_filter:
        df = payload.data_filter
        if df.event_ids is not None:
            config.data_filter.event_ids = list(df.event_ids)
        if df.stage_names is not None:
            config.data_filter.stage_names = list(df.stage_names)
        if df.date_from is not None:
            config.data_filter.date_from = df.date_from or None
        if df.date_to is not None:
            config.data_filter.date_to = df.date_to or None

    if payload.bankroll:
        b = payload.bankroll
        for key in ("total", "max_stake_pct", "daily_limit", "event_limit", "kelly_fraction"):
            val = getattr(b, key)
            if val is not None:
                setattr(config.bankroll, key, val)

    if payload.edge:
        e = payload.edge
        for key in ("min_edge", "strong_edge", "min_confidence", "min_sample_map", "min_sample_general"):
            val = getattr(e, key)
            if val is not None:
                setattr(config.edge, key, val)

    if payload.markets and payload.markets.enabled_markets is not None:
        config.markets.enabled_markets = list(payload.markets.enabled_markets)

    if payload.live:
        l = payload.live
        for key in ("betano_live", "bet365_live", "show_live_opportunities", "auto_recalc_on_map_result"):
            val = getattr(l, key)
            if val is not None:
                setattr(config.live, key, val)

    _persist_config(_export_config())
    return _export_config()


@app.get("/api/hedge")
def hedge(
    stake: float = Query(..., gt=0),
    odds: float = Query(..., gt=1.0),
    hedge_odds: float = Query(..., gt=1.0),
    lock_profit: bool = True,
) -> dict[str, Any]:
    return hedge_calculator(stake, odds, hedge_odds, lock_profit=lock_profit)


def _match_exists(match_id: int) -> bool:
    with get_db() as conn:
        row = conn.execute("SELECT 1 FROM matches WHERE id = ?", (match_id,)).fetchone()
    return bool(row)


def _enrich_veto_with_start_side(
    match_id: int,
    veto_rows: list[dict[str, Any]],
    conn: Any,
) -> None:
    """Fill start_side on veto rows from maps table when map was played (e.g. from VLR)."""
    map_sides = conn.execute(
        """SELECT map_name, team1_start_side, pick_team_id, team1_id
           FROM maps
           WHERE match_id = ? AND team1_start_side IS NOT NULL AND pick_team_id IS NOT NULL""",
        (match_id,),
    ).fetchall()
    by_map: dict[str, tuple[str | None, int | None, int | None]] = {}
    for r in map_sides:
        by_map[(r["map_name"] or "").strip().lower()] = (
            r["team1_start_side"],
            r["pick_team_id"],
            r["team1_id"],
        )
    for v in veto_rows:
        if v.get("start_side") or (v.get("action") or "").lower() not in ("pick", "decider"):
            continue
        key = (v.get("map_name") or "").strip().lower()
        if key not in by_map:
            continue
        t1_side, pick_id, t1_id = by_map[key]
        if not t1_side or pick_id is None:
            continue
        if pick_id == t1_id:
            v["start_side"] = t1_side
        else:
            v["start_side"] = "Defender" if (t1_side and "attack" in t1_side.lower()) else "Attacker"


def _veto_to_markdown(veto_rows: list[dict[str, Any]]) -> str:
    """Build VLR-style veto string from veto rows (same format as paste)."""
    parts = []
    for v in veto_rows:
        action = (v.get("action") or "").lower()
        team_name = (v.get("team_name") or "").strip() or "?"
        map_name = (v.get("map_name") or "").strip() or "?"
        start_side = (v.get("start_side") or "").strip()
        if action == "decider":
            parts.append(f"{map_name} remains")
            continue
        seg = f"{team_name} {action} {map_name}"
        if start_side and action == "pick":
            seg += f" ({start_side})"
        parts.append(seg)
    return "; ".join(parts)


def _get_match_info(match_id: int) -> dict[str, Any] | None:
    with get_db() as conn:
        row = conn.execute(
            """SELECT m.id, m.event_id, m.stage_name, m.phase, m.date, m.time,
                      m.bo_type, m.patch, m.status, m.score1, m.score2,
                      t1.id AS team1_id, t1.name AS team1_name, t1.tag AS team1_tag,
                      t2.id AS team2_id, t2.name AS team2_name, t2.tag AS team2_tag,
                      e.name AS event_name
               FROM matches m
               LEFT JOIN teams t1 ON m.team1_id = t1.id
               LEFT JOIN teams t2 ON m.team2_id = t2.id
               LEFT JOIN events e ON m.event_id = e.id
               WHERE m.id = ?""",
            (match_id,),
        ).fetchone()
    if not row:
        return None
    info = dict(row)
    info["team1_tag"] = _team_display_tag(info.get("team1_name"), info.get("team1_tag"))
    info["team2_tag"] = _team_display_tag(info.get("team2_name"), info.get("team2_tag"))
    return info


def _save_manual_veto(match_id: int, actions: list[VetoActionIn]) -> int:
    saved = 0
    with get_db() as conn:
        conn.execute(
            "DELETE FROM pending_vetos WHERE match_id = ? AND source = 'manual'",
            (match_id,),
        )
        for action in actions:
            conn.execute(
                """INSERT INTO pending_vetos
                   (match_id, source, map_order, action, team_id, team_name, map_name, start_side)
                   VALUES (?, 'manual', ?, ?, ?, ?, ?, ?)""",
                (
                    match_id,
                    action.map_order,
                    action.action.lower().strip(),
                    action.team_id,
                    action.team_name,
                    action.map_name,
                    action.start_side,
                ),
            )
            saved += 1
    return saved


def _infer_map_number(market_type: str) -> int | None:
    digits = "".join(c for c in market_type if c.isdigit())
    return int(digits) if digits else None


def _get_veto_maps(match_id: int, bo_type: str) -> list[dict[str, Any]]:
    with get_db() as conn:
        rows = conn.execute(
            """SELECT source, map_order, action, team_name, map_name, start_side
               FROM pending_vetos
               WHERE match_id = ?
               ORDER BY CASE source WHEN 'manual' THEN 0 ELSE 1 END, map_order""",
            (match_id,),
        ).fetchall()

    maps: list[dict[str, Any]] = []
    seen_sources: set[str] = set()
    for row in rows:
        if row["action"] in ("pick", "decider"):
            if row["source"] == "vlr" and "manual" in seen_sources:
                continue
            maps.append(
                {
                    "map_name": row["map_name"],
                    "map_order": len(maps) + 1,
                    "pick_team": row["team_name"],
                    "start_side": row["start_side"],
                }
            )
        seen_sources.add(row["source"])

    if not maps:
        n = 5 if "5" in str(bo_type).lower() else 3
        maps = [
            {
                "map_name": "Unknown",
                "map_order": i + 1,
                "pick_team": None,
                "start_side": None,
            }
            for i in range(n)
        ]

    return maps


def _get_ot_odds(match_id: int, n_maps: int) -> list[float]:
    odds: list[float] = []
    with get_db() as conn:
        for i in range(1, n_maps + 1):
            row = conn.execute(
                """SELECT odds_value
                   FROM odds_snapshots
                   WHERE match_id = ?
                     AND market_type LIKE ?
                     AND LOWER(selection) LIKE '%yes%'
                   ORDER BY timestamp DESC
                   LIMIT 1""",
                (match_id, f"%map{i}_ot%"),
            ).fetchone()
            if row:
                odds.append(float(row["odds_value"]))
    return odds if len(odds) == n_maps else []


def _get_score_odds(match_id: int) -> dict[str, float]:
    with get_db() as conn:
        rows = conn.execute(
            """SELECT selection, odds_value
               FROM odds_snapshots
               WHERE match_id = ?
                 AND market_type = 'correct_score'
               ORDER BY timestamp DESC""",
            (match_id,),
        ).fetchall()

    result: dict[str, float] = {}
    for row in rows:
        selection = row["selection"].strip()
        if selection not in result:
            result[selection] = float(row["odds_value"])
    return result


def _serialize(value: Any) -> Any:
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, list):
        return [_serialize(v) for v in value]
    if isinstance(value, dict):
        return {k: _serialize(v) for k, v in value.items()}
    return value


def _build_match_analysis(match_id: int) -> dict[str, Any]:
    info = _get_match_info(match_id)
    if not info:
        raise HTTPException(status_code=404, detail=f"Match {match_id} not found")

    team_a_id = info["team1_id"]
    team_b_id = info["team2_id"]
    team_a_name = info.get("team1_name") or "Team A"
    team_b_name = info.get("team2_name") or "Team B"
    team_a_tag = info.get("team1_tag")
    team_b_tag = info.get("team2_tag")
    bo_type = info.get("bo_type") or "bo3"
    if not info.get("bo_type"):
        try:
            s1, s2 = info.get("score1"), info.get("score2")
            if s1 is not None and s2 is not None and (int(s1) + int(s2)) > 3:
                bo_type = "bo5"
        except (TypeError, ValueError):
            pass

    map_list = _get_veto_maps(match_id, bo_type)
    if not info.get("bo_type") and len(map_list) == 5:
        bo_type = "bo5"

    map_analyses = []
    ot_results = []
    map_probs_a = []

    for m in map_list:
        map_name = m["map_name"]
        ma = estimate_map_win(
            team_a_id,
            team_b_id,
            map_name,
            starting_side_a=m.get("start_side"),
            data_filter=config.data_filter,
            bo_type=bo_type,
        )
        ma.map_order = m["map_order"]
        ma.pick_team = m.get("pick_team")

        ot = estimate_ot_prob(
            team_a_id,
            team_b_id,
            map_name,
            data_filter=config.data_filter,
            bo_type=bo_type,
        )
        ma.p_ot = ot["p_ot"]

        map_analyses.append(ma)
        ot_results.append(ot)
        map_probs_a.append(ma.p_team_a_win)

    maps_to_win = 3 if "5" in str(bo_type).lower() else 2
    series_result = simulate_series(map_probs_a, maps_to_win=maps_to_win)

    market_probs = build_market_probs(map_analyses, series_result, ot_results)
    single_edges = analyze_market_edges(match_id, market_probs)
    arbs = detect_arbitrage(match_id)

    ot_probs = [ot["p_ot"] for ot in ot_results]
    ot_odds = _get_ot_odds(match_id, len(map_list))
    multi_bets = []
    if ot_odds and len(ot_odds) == len(ot_probs):
        spread = analyze_spread(
            ot_probs,
            ot_odds,
            market_label="OT",
            stake_per_map=config.multibet.default_spread_stake,
        )
        if spread:
            multi_bets.append(spread)

    positive = [
        {
            "market": e.market,
            "selection": e.selection,
            "p_model": e.p_model,
            "odds": e.odds,
            "bookmaker": e.bookmaker,
            "confidence": e.confidence,
        }
        for e in single_edges
        if e.edge > 0
    ]

    multi_bets.extend(find_profitable_parlays(positive, max_legs=3))

    score_odds = _get_score_odds(match_id)
    if score_odds and series_result.get("score_probs"):
        cs = correct_score_coverage(series_result["score_probs"], score_odds)
        if cs:
            multi_bets.append(cs)

    h2h = get_h2h_stats(team_a_id, team_b_id, data_filter=config.data_filter)

    with get_db() as conn:
        odds_count = conn.execute(
            "SELECT COUNT(*) AS c FROM odds_snapshots WHERE match_id = ?",
            (match_id,),
        ).fetchone()["c"]

    return {
        "match": info,
        "h2h": h2h,
        "bo_type": bo_type,
        "maps": _serialize(map_analyses),
        "ot": ot_results,
        "series": series_result,
        "single_edges": _serialize(single_edges),
        "multi_bets": _serialize(multi_bets),
        "arbitrage": arbs,
        "odds_count": odds_count,
        "filter": {
            "description": config.data_filter.description,
            "is_active": config.data_filter.is_active,
        },
        "teams": {
            "team_a": {"id": team_a_id, "name": team_a_name, "tag": team_a_tag},
            "team_b": {"id": team_b_id, "name": team_b_name, "tag": team_b_tag},
        },
    }


def _get_live_state(match_id: int) -> dict[str, Any]:
    info = _get_match_info(match_id)
    if not info:
        raise HTTPException(status_code=404, detail=f"Match {match_id} not found")

    bo_type = info.get("bo_type") or "bo3"
    maps_to_win = 3 if "5" in bo_type.lower() else 2

    with get_db() as conn:
        rows = conn.execute(
            """SELECT map_number, map_name, winner_team_id, winner_team_side, score_a, score_b, updated_at
               FROM live_map_results
               WHERE match_id = ?
               ORDER BY map_number""",
            (match_id,),
        ).fetchall()

    a_score = sum(1 for r in rows if r["winner_team_side"] == "a")
    b_score = sum(1 for r in rows if r["winner_team_side"] == "b")

    return {
        "match_id": match_id,
        "team_a": {"id": info["team1_id"], "name": info["team1_name"], "tag": info.get("team1_tag")},
        "team_b": {"id": info["team2_id"], "name": info["team2_name"], "tag": info.get("team2_tag")},
        "maps_to_win": maps_to_win,
        "a_score": a_score,
        "b_score": b_score,
        "map_results": [dict(r) for r in rows],
    }


def _calculate_live_series_prob(match_id: int) -> dict[str, Any]:
    info = _get_match_info(match_id)
    if not info:
        raise HTTPException(status_code=404, detail=f"Match {match_id} not found")

    bo_type = info.get("bo_type") or "bo3"
    maps_to_win = 3 if "5" in bo_type.lower() else 2
    max_maps = 2 * maps_to_win - 1

    live_state = _get_live_state(match_id)
    a_score = live_state["a_score"]
    b_score = live_state["b_score"]
    played = len(live_state["map_results"])

    if a_score >= maps_to_win:
        return {
            **live_state,
            "series_prob": {
                "p_a_series": 1.0,
                "p_b_series": 0.0,
                "status": "decided",
            },
        }

    if b_score >= maps_to_win:
        return {
            **live_state,
            "series_prob": {
                "p_a_series": 0.0,
                "p_b_series": 1.0,
                "status": "decided",
            },
        }

    a_needs = maps_to_win - a_score
    remaining = max_maps - played

    veto_maps = _get_veto_maps(match_id, bo_type)
    remaining_probs: list[float] = []

    for idx in range(played, played + remaining):
        map_name = veto_maps[idx]["map_name"] if idx < len(veto_maps) else "Unknown"
        if map_name != "Unknown":
            ma = estimate_map_win(
                info["team1_id"],
                info["team2_id"],
                map_name,
                data_filter=config.data_filter,
                bo_type=bo_type,
            )
            remaining_probs.append(ma.p_team_a_win)
        else:
            remaining_probs.append(0.5)

    sim = simulate_series(remaining_probs, maps_to_win=a_needs)

    return {
        **live_state,
        "remaining_maps": remaining,
        "series_prob": {
            "p_a_series": sim["p_a_series"],
            "p_b_series": sim["p_b_series"],
            "score_probs": sim.get("score_probs", {}),
            "total_maps_dist": sim.get("total_maps_dist", {}),
            "status": "in_progress",
        },
    }


def _export_config() -> dict[str, Any]:
    return {
        "data_filter": {
            "event_ids": list(config.data_filter.event_ids),
            "stage_names": list(config.data_filter.stage_names),
            "date_from": config.data_filter.date_from,
            "date_to": config.data_filter.date_to,
            "description": config.data_filter.description,
            "is_active": config.data_filter.is_active,
        },
        "bankroll": {
            "total": config.bankroll.total,
            "max_stake_pct": config.bankroll.max_stake_pct,
            "daily_limit": config.bankroll.daily_limit,
            "event_limit": config.bankroll.event_limit,
            "kelly_fraction": config.bankroll.kelly_fraction,
        },
        "edge": {
            "min_edge": config.edge.min_edge,
            "strong_edge": config.edge.strong_edge,
            "min_confidence": config.edge.min_confidence,
            "min_sample_map": config.edge.min_sample_map,
            "min_sample_general": config.edge.min_sample_general,
        },
        "markets": {
            "enabled_markets": list(config.markets.enabled_markets),
        },
        "live": {
            "betano_live": config.live.betano_live,
            "bet365_live": config.live.bet365_live,
            "show_live_opportunities": config.live.show_live_opportunities,
            "auto_recalc_on_map_result": config.live.auto_recalc_on_map_result,
        },
    }


def _apply_config_payload(payload: dict[str, Any]) -> None:
    if "data_filter" in payload:
        df = payload["data_filter"] or {}
        config.data_filter.event_ids = list(df.get("event_ids") or [])
        config.data_filter.stage_names = list(df.get("stage_names") or [])
        config.data_filter.date_from = df.get("date_from")
        config.data_filter.date_to = df.get("date_to")

    if "bankroll" in payload:
        b = payload["bankroll"] or {}
        for key in ("total", "max_stake_pct", "daily_limit", "event_limit", "kelly_fraction"):
            if key in b and b[key] is not None:
                setattr(config.bankroll, key, b[key])

    if "edge" in payload:
        e = payload["edge"] or {}
        for key in ("min_edge", "strong_edge", "min_confidence", "min_sample_map", "min_sample_general"):
            if key in e and e[key] is not None:
                setattr(config.edge, key, e[key])

    if "markets" in payload:
        m = payload["markets"] or {}
        if "enabled_markets" in m and m["enabled_markets"] is not None:
            config.markets.enabled_markets = list(m["enabled_markets"])

    if "live" in payload:
        l = payload["live"] or {}
        for key in ("betano_live", "bet365_live", "show_live_opportunities", "auto_recalc_on_map_result"):
            if key in l and l[key] is not None:
                setattr(config.live, key, l[key])


def _persist_config(payload: dict[str, Any]) -> None:
    with get_db() as conn:
        conn.execute(
            """INSERT INTO app_config (key, value, updated_at)
               VALUES (?, ?, datetime('now'))
               ON CONFLICT(key) DO UPDATE SET
                 value=excluded.value,
                 updated_at=datetime('now')""",
            (APP_CONFIG_KEY, json.dumps(payload)),
        )


def _load_persisted_config() -> None:
    with get_db() as conn:
        row = conn.execute(
            "SELECT value FROM app_config WHERE key = ?",
            (APP_CONFIG_KEY,),
        ).fetchone()

    if not row:
        _persist_config(_export_config())
        return

    try:
        payload = json.loads(row["value"])
    except Exception:
        payload = _export_config()

    _apply_config_payload(payload)


def _db_counts() -> dict[str, int]:
    with get_db() as conn:
        events = conn.execute("SELECT COUNT(*) AS c FROM events").fetchone()["c"]
        matches = conn.execute("SELECT COUNT(*) AS c FROM matches").fetchone()["c"]
        maps = conn.execute("SELECT COUNT(*) AS c FROM maps").fetchone()["c"]
    return {"events": events, "matches": matches, "maps": maps}


STAT_KEYWORDS = {
    "ot": "ot",
    "overtime": "ot",
    "pistol": "pistol",
    "pistols": "pistol",
    "winrate": "winrate",
    "win rate": "winrate",
    "taxa de vitoria": "winrate",
    "placar": "scores",
    "placares": "scores",
    "score": "scores",
    "scores": "scores",
    "resultado": "scores",
    "resultados": "scores",
    "close": "close",
    "apertado": "close",
    "apertados": "close",
    "atk": "sides",
    "def": "sides",
    "lado": "sides",
    "sides": "sides",
    "comp": "comp",
    "composicao": "comp",
    "composicoes": "comp",
    "agents": "comp",
    "agentes": "comp",
    "h2h": "h2h",
    "head to head": "h2h",
    "historico": "h2h",
    "stats": "overview",
    "estatisticas": "overview",
    "overview": "overview",
    "geral": "overview",
    "round": "rounds",
    "rounds": "rounds",
}


def _detect_stat_type(query: str) -> str | None:
    q = query.lower().strip()
    for keyword, stat in STAT_KEYWORDS.items():
        if keyword in q:
            return stat
    return None


_STAT_STOPWORDS = {"ot", "overtime", "e", "o", "a", "vs", "h2h", "overview", "scores", "comp", "round", "rounds", "pistol", "pistols", "de", "da", "do", "em", "no", "na"}


def _find_teams(query: str) -> list[dict[str, Any]]:
    q_lower = query.lower().strip()
    words = set(w for w in re.split(r"[^a-z0-9]+", q_lower) if len(w) >= 2 and w not in _STAT_STOPWORDS)
    with get_db() as conn:
        rows = conn.execute("SELECT id, name, tag FROM teams").fetchall()

    found = []
    for row in rows:
        name = (row["name"] or "").lower()
        tag = (row["tag"] or "").lower()
        if not tag and not name:
            continue
        if tag and len(tag) >= 2 and tag in words:
            found.append({"id": row["id"], "name": row["name"], "tag": row["tag"]})
            continue
        if name and any(w in name or name in w for w in words if len(w) >= 2):
            found.append({"id": row["id"], "name": row["name"], "tag": row["tag"]})
            continue
        if name and (name in q_lower or q_lower in name):
            found.append({"id": row["id"], "name": row["name"], "tag": row["tag"]})
        elif tag and len(tag) >= 2 and tag in q_lower:
            found.append({"id": row["id"], "name": row["name"], "tag": row["tag"]})

    unique = []
    seen = set()
    for team in found:
        if team["id"] not in seen:
            unique.append(team)
            seen.add(team["id"])
    return unique


def _find_map(query: str) -> str | None:
    q = query.lower()
    for map_name in VALORANT_MAP_POOL:
        if map_name.lower() in q:
            return map_name
    return None


def _aggregate_team_stats(
    team_id: int,
    map_name: str | None,
    data_filter: DataFilter | None = None,
) -> dict[str, Any]:
    """Aggregate map stats for a team. Use data_filter=DataFilter() for all regions/events."""
    filt = data_filter if data_filter is not None else DataFilter()
    maps = [map_name] if map_name else VALORANT_MAP_POOL
    stats = [get_team_map_stats(team_id, mn, data_filter=filt) for mn in maps]

    total_games = sum(s.games_played for s in stats)
    total_wins = sum(s.wins for s in stats)
    total_losses = sum(s.losses for s in stats)
    total_ot = sum(s.ot_count for s in stats)
    total_pistols_won = sum(s.pistols_won for s in stats)
    total_pistols = sum(s.pistols_played for s in stats)
    total_pistol_atk_won = sum(s.pistol_atk_won for s in stats)
    total_pistol_def_won = sum(s.pistol_def_won for s in stats)
    total_pistol_atk_played = sum(s.pistol_atk_played for s in stats)
    total_pistol_def_played = sum(s.pistol_def_played for s in stats)

    avg_atk = 0.0
    avg_def = 0.0
    if total_games:
        avg_atk = sum(s.atk_round_rate * s.games_played for s in stats) / total_games
        avg_def = sum(s.def_round_rate * s.games_played for s in stats) / total_games

    return {
        "games_played": total_games,
        "wins": total_wins,
        "losses": total_losses,
        "winrate": (total_wins / total_games) if total_games else 0.0,
        "ot_count": total_ot,
        "ot_rate": (total_ot / total_games) if total_games else 0.0,
        "pistols_won": total_pistols_won,
        "pistols_played": total_pistols,
        "pistol_rate": (total_pistols_won / total_pistols) if total_pistols else 0.0,
        "pistol_atk_won": total_pistol_atk_won,
        "pistol_def_won": total_pistol_def_won,
        "pistol_atk_played": total_pistol_atk_played,
        "pistol_def_played": total_pistol_def_played,
        "atk_rate": avg_atk,
        "def_rate": avg_def,
    }


def _run_stats_query(stat_type: str, teams: list[dict[str, Any]], map_name: str | None) -> dict[str, Any]:
    if stat_type == "h2h":
        if len(teams) < 2:
            return {"error": "h2h requires two teams"}
        return get_h2h_stats(
            teams[0]["id"], teams[1]["id"],
            map_name=map_name,
            data_filter=DataFilter(),
        )

    if stat_type == "scores":
        if not teams:
            return {"items": []}

        items: list[dict[str, Any]] = []
        with get_db() as conn:
            for team in teams:
                conds = ["(m.team1_id = ? OR m.team2_id = ?)", "m.team1_score IS NOT NULL"]
                params: list[Any] = [team["id"], team["id"]]
                if map_name:
                    conds.append("m.map_name = ?")
                    params.append(map_name)
                where = " AND ".join(conds)
                rows = conn.execute(
                    f"""SELECT m.map_name, m.team1_score, m.team2_score, m.is_ot,
                               mt.date, t1.name AS t1_name, t2.name AS t2_name
                        FROM maps m
                        JOIN matches mt ON m.match_id = mt.id
                        LEFT JOIN teams t1 ON m.team1_id = t1.id
                        LEFT JOIN teams t2 ON m.team2_id = t2.id
                        WHERE {where}
                        ORDER BY mt.date DESC
                        LIMIT 15""",
                    params,
                ).fetchall()

                for row in rows:
                    items.append(
                        {
                            "team": team["name"],
                            "date": row["date"],
                            "map_name": row["map_name"],
                            "score": f"{row['team1_score']}-{row['team2_score']}",
                            "matchup": f"{row['t1_name']} vs {row['t2_name']}",
                            "is_ot": bool(row["is_ot"]),
                        }
                    )
        return {"items": items}

    if not teams:
        return {
            "error": "No teams recognized in query",
            "hint": "The teams (e.g. DFM, PRX) may not be in the database. Sync events from the regions that include those teams (VLR sync or manual). Stats use all matches from all regions once teams are found.",
        }

    rows = []
    for team in teams:
        agg = _aggregate_team_stats(team["id"], map_name, data_filter=DataFilter())
        rows.append({"team": team, **agg})

    if stat_type == "comp":
        comp_rows = []
        maps = [map_name] if map_name else VALORANT_MAP_POOL
        for team in teams:
            team_items = []
            for mn in maps:
                team_items.extend(
                    get_team_likely_comp(team["id"], mn, data_filter=DataFilter(), limit=2)
                )
            comp_rows.append({"team": team, "compositions": team_items})
        return {"items": comp_rows}

    return {"items": rows}

