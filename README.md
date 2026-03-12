# VCT +EV Terminal

CLI and web app for Valorant esports: sync match data, estimate win probabilities from historical stats, collect bookmaker odds, and surface +EV spots (single bets, parlays, spreads, arbitrage).

**Relevant skills:** data pipeline (scraping → SQLite), probabilistic modeling (map/series/OT), margin removal and implied odds, expected value and edge calculation, multi-outcome optimization (dutch, hedge, correct score).

---

## What it does

- **Data:** Syncs VCT events, stages, matches, maps and round-level results from VLR.gg into SQLite. Optional odds collection from Betano/Bet365 (browser automation or manual input).
- **Model:** Probability engine that uses only filtered data (by event, stage, date range). For each map in a matchup it aggregates team map stats, H2H, side (ATK/DEF), pistols, and composition; applies configurable weights and (optionally) Wilson lower bound for small samples. Bo3/Bo5 series and OT probabilities are derived from these map estimates.
- **Edge:** Compares model probabilities to bookmaker implied odds (with margin removal). Flags +EV markets (map winner, OT, correct score, over/under rounds). Confidence levels based on sample size.
- **Multibets:** Parlay finder, spread analysis (e.g. "OT on every map"), hedge and dutch calculators, correct-score coverage optimizer. Correlation factor for dependent legs.
- **Arbitrage:** Detects surebets when odds from different books imply probabilities that sum below 1.

You can use the interactive terminal (menus), the legacy CLI (`--legacy`), or the FastAPI + React web UI.

---

## Main features

| Area | Description |
|------|-------------|
| **Sync** | VLR.gg → events, stages, teams, matches, maps, rounds. Filter by event/stage/date. |
| **Probability** | Map win, OT, series outcome; optional composition and veto context; Bo3/Bo5-specific history. |
| **Odds** | Manual entry, quick string, file import; optional scrapers (Betano, Bet365). Stored per market/map with timestamp. |
| **Edge** | Model vs bookmaker; margin stripping (power/Shin); edge and EV per selection; confidence (sample size). |
| **Multibets** | Parlays, spread (same bet on all maps), hedge, dutch, correct-score coverage. |
| **Arbitrage** | Cross-book comparison; list of arb opportunities per match/market. |
| **Data filter** | All model and analysis respect a global filter (event IDs, stage names, date range). |

---

## Stack

- **Backend:** Python 3.x, SQLite, FastAPI, Typer/Rich (CLI), vlrdevapi (VLR), Playwright (odds scrapers).
- **Frontend:** React, minimal UI for match selection, veto input, odds, and analysis results.
- **Data:** Relational schema (events, stages, teams, matches, maps, rounds, odds_snapshots, outcomes). Queries are filter-aware.

---

## Run

```bash
# deps
pip install -r requirements.txt
playwright install chromium

# interactive terminal (default)
python -m src

# legacy CLI (e.g. sync, analyze, odds)
python -m src --legacy sync
python -m src --legacy analyze <match_id>
python -m src --legacy odds <match_id> [--manual]

# API + web
uvicorn src.api:app --reload
cd web && npm install && npm run dev
```

Database and browser profile live under `data/` (gitignored).
