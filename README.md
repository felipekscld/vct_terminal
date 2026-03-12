# VCT +EV Terminal

CLI and web application for quantitative analysis of competitive Valorant matches: collects historical match data, estimates win probabilities from team statistics, and compares model estimates against market-implied probabilities to identify pricing gaps.

**Relevant skills:** data pipeline (scraping → SQLite), probabilistic modeling (map/series/overtime), margin removal and implied probability, expected value and edge computation, multi-outcome optimization under correlation.

---

## What it does

- **Data pipeline.** Syncs VCT events, stages, matches, maps and round-level results from VLR.gg into a relational SQLite schema. Optional collection of market prices from configurable providers (browser automation or manual input).
- **Probability engine.** Estimates per-map win probability using only filtered data (by event, stage, date range). Aggregates team map statistics, head-to-head history, side performance (attack/defense), pistol rounds and composition, applying configurable weights and an optional Wilson lower bound to correct for small samples. Best-of-3 and best-of-5 series probabilities, as well as overtime probabilities, are derived analytically from the map-level estimates.
- **Edge computation.** Converts market prices into implied probabilities after removing the built-in margin (power and Shin methods), then compares them against model estimates to compute edge and expected value per outcome. Confidence levels are assigned based on sample size.
- **Multi-outcome analysis.** Combination finder, spread analysis across maps, hedge and dutch calculators, and a correct-score coverage optimizer. Includes a correlation factor for dependent outcomes.
- **Cross-provider comparison.** Detects inconsistencies where implied probabilities from different providers sum to less than one.

Three interfaces are available: an interactive terminal with menus, a legacy command-line interface (`--legacy`), and a FastAPI + React web UI.

---

## Main components

| Area | Description |
| --- | --- |
| **Sync** | VLR.gg → events, stages, teams, matches, maps, rounds. Filterable by event, stage or date range. |
| **Probability** | Map win, overtime and series outcome; optional composition and veto context; format-specific history. |
| **Market data** | Manual entry, quick string parsing, file import, and optional automated collection. Stored per market and map with timestamp. |
| **Edge** | Model vs. market; margin stripping (power/Shin); edge and expected value per selection; confidence from sample size. |
| **Multi-outcome** | Combinations, spread across maps, hedge, dutch, correct-score coverage. |
| **Comparison** | Cross-provider inconsistency detection per match and market. |
| **Filtering** | All modeling and analysis respect a global filter (event IDs, stage names, date range). |

---

## Modeling notes

The probability engine is deliberately conservative on small samples. Raw win rates over few observations are unstable, so the engine optionally applies a Wilson score lower bound rather than the point estimate, which penalizes conclusions drawn from thin data.

Series probabilities are not estimated directly. They are derived from per-map estimates under an explicit independence assumption, which is documented rather than hidden — dependence between maps in a series is a known limitation and is partially addressed through the correlation factor in multi-outcome analysis.

Market prices carry an embedded margin that inflates the sum of implied probabilities above one. Two normalization methods are implemented: proportional (power) and Shin, which assumes a share of informed participants. Comparing model output to raw prices without this step produces a systematically biased edge.

---

## Stack

- **Backend:** Python 3.x, SQLite, FastAPI, Typer/Rich (CLI), vlrdevapi, Playwright.
- **Frontend:** React — match selection, veto input, market data entry, analysis output.
- **Data:** Relational schema (events, stages, teams, matches, maps, rounds, odds_snapshots, outcomes), with filter-aware queries throughout.

---

## Running

```bash
# dependencies
pip install -r requirements.txt
playwright install chromium

# interactive terminal (default)
python -m src

# legacy CLI
python -m src --legacy sync
python -m src --legacy analyze <match_id>
python -m src --legacy odds <match_id> [--manual]

# API + web interface
uvicorn src.api:app --reload
cd web && npm install && npm run dev
```

The database and browser profile live under `data/` (gitignored).

---

## Limitations

Estimates are statistical, not predictive certainties. The model is only as good as the filtered sample it is given, and roster changes, patch updates and meta shifts are not explicitly modeled. Results are intended for quantitative analysis and comparison, not as a basis for financial decisions.
