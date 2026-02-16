"""Global configuration for VCT +EV Terminal."""

from __future__ import annotations

import os
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

DB_PATH = DATA_DIR / "vct.db"

VALORANT_MAP_POOL: list[str] = [
    "Abyss",
    "Bind",
    "Breeze",
    "Corrode",
    "Haven",
    "Pearl",
    "Split",
]


@dataclass
class DataFilter:
    """Controls which data the model uses for calculations.

    Examples:
        - Only VCT Kickoff 2026:  DataFilter(event_ids=[2682])
        - Kickoff + Masters 2026: DataFilter(event_ids=[2682, 2700])
        - Only 2026 data:         DataFilter(date_from="2026-01-01")
        - Specific stage:         DataFilter(event_ids=[2682], stage_names=["Playoffs"])
        - Last 30 days:           DataFilter(date_from="2026-01-15")
    """
    event_ids: list[int] = field(default_factory=list)
    stage_names: list[str] = field(default_factory=list)
    date_from: Optional[str] = None
    date_to: Optional[str] = None

    def build_sql_conditions(self, match_table_alias: str = "mt") -> tuple[list[str], list]:
        """Generate SQL WHERE clauses and params from this filter.

        Returns (conditions_list, params_list) to be appended to a query.
        """
        conditions: list[str] = []
        params: list = []

        if self.event_ids:
            placeholders = ",".join("?" for _ in self.event_ids)
            conditions.append(f"{match_table_alias}.event_id IN ({placeholders})")
            params.extend(self.event_ids)

        if self.stage_names:
            placeholders = ",".join("?" for _ in self.stage_names)
            conditions.append(f"{match_table_alias}.stage_name IN ({placeholders})")
            params.extend(self.stage_names)

        if self.date_from:
            conditions.append(f"{match_table_alias}.date >= ?")
            params.append(self.date_from)

        if self.date_to:
            conditions.append(f"{match_table_alias}.date <= ?")
            params.append(self.date_to)

        return conditions, params

    @property
    def description(self) -> str:
        """Human-readable description of active filters."""
        parts = []
        if self.event_ids:
            parts.append(f"events={self.event_ids}")
        if self.stage_names:
            parts.append(f"stages={self.stage_names}")
        if self.date_from:
            parts.append(f"from={self.date_from}")
        if self.date_to:
            parts.append(f"to={self.date_to}")
        return " | ".join(parts) if parts else "all data (no filters)"

    @property
    def is_active(self) -> bool:
        return bool(self.event_ids or self.stage_names or self.date_from or self.date_to)


@dataclass
class BankrollConfig:
    total: float = 1300.0
    max_stake_pct: float = 0.03
    daily_limit: float = 300.0
    event_limit: float = 500.0
    kelly_fraction: float = 0.25


@dataclass
class EdgeConfig:
    min_edge: float = 0.03
    strong_edge: float = 0.08
    min_confidence: str = "medium"
    min_sample_map: int = 3
    min_sample_general: int = 5


@dataclass
class ModelWeights:
    """Weights for the map-level probability model."""
    base_map_winrate: float = 0.30
    opponent_adjusted: float = 0.25
    h2h: float = 0.15
    side_advantage: float = 0.10
    comp_factor: float = 0.10
    pistol_factor: float = 0.05
    recency: float = 0.05


@dataclass
class OTModelWeights:
    """Weights for OT probability model."""
    global_ot_rate: float = 0.30
    closeness_index: float = 0.30
    comp_ot_rate: float = 0.25
    pistol_swing: float = 0.15


@dataclass
class MultiBetConfig:
    correlation_factor: float = 0.10
    min_spread_edge: float = 0.02
    min_parlay_edge: float = 0.05
    monte_carlo_sims: int = 10000
    default_spread_stake: float = 10.0


ALL_MARKET_TYPES = [
    "map_winner",
    "map_ot",
    "map_pistol",
    "map_handicap",
    "map_total_rounds",
    "match_winner",
    "correct_score",
    "over_maps",
    "over_maps_2_5",
    "under_maps_2_5",
    "over_maps_4_5",
    "under_maps_4_5",
]

MARKET_LABELS = {
    "map_winner": "Map Winner (ML)",
    "map_ot": "Overtime por Mapa",
    "map_pistol": "Pistol Rounds",
    "map_handicap": "Handicap de Rounds",
    "map_total_rounds": "Total de Rounds (Over/Under)",
    "match_winner": "Match Winner (Serie)",
    "correct_score": "Placar Correto da Serie",
    "over_maps": "+3.5 Mapas (BO5)",
    "over_maps_2_5": "Over 2.5 Mapas (BO3)",
    "under_maps_2_5": "Under 2.5 Mapas (BO3)",
    "over_maps_4_5": "Over 4.5 Mapas (BO5)",
    "under_maps_4_5": "Under 4.5 Mapas (BO5)",
}


@dataclass
class MarketPreferences:
    """Which markets the user wants to see and analyze."""
    enabled_markets: list[str] = field(default_factory=lambda: [
        "map_winner", "map_ot", "map_pistol", "match_winner",
        "correct_score", "over_maps",
    ])

    def is_enabled(self, market: str) -> bool:
        return market in self.enabled_markets


@dataclass
class LiveBettingConfig:
    """Configuration for live/in-play betting analysis."""
    betano_live: bool = True
    bet365_live: bool = False
    show_live_opportunities: bool = True
    auto_recalc_on_map_result: bool = True


@dataclass
class Config:
    db_path: Path = field(default_factory=lambda: DB_PATH)
    data_filter: DataFilter = field(default_factory=DataFilter)
    bankroll: BankrollConfig = field(default_factory=BankrollConfig)
    edge: EdgeConfig = field(default_factory=EdgeConfig)
    model_weights: ModelWeights = field(default_factory=ModelWeights)
    ot_weights: OTModelWeights = field(default_factory=OTModelWeights)
    multibet: MultiBetConfig = field(default_factory=MultiBetConfig)
    markets: MarketPreferences = field(default_factory=MarketPreferences)
    live: LiveBettingConfig = field(default_factory=LiveBettingConfig)
    map_pool: list[str] = field(default_factory=lambda: VALORANT_MAP_POOL.copy())


config = Config()
