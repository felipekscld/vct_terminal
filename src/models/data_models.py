"""Internal data models used across the application."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class TeamStats:
    """Aggregated stats for a team on a specific map within an event/stage."""
    team_id: int
    team_name: str
    map_name: str
    games_played: int = 0
    wins: int = 0
    losses: int = 0
    ot_count: int = 0
    avg_rounds_won: float = 0.0
    avg_rounds_lost: float = 0.0
    avg_round_diff: float = 0.0
    atk_rounds_won: int = 0
    atk_rounds_played: int = 0
    def_rounds_won: int = 0
    def_rounds_played: int = 0
    pistols_won: int = 0
    pistols_played: int = 0
    pistol_conversions: int = 0
    pistol_atk_won: int = 0
    pistol_def_won: int = 0
    pistol_atk_played: int = 0
    pistol_def_played: int = 0
    close_maps: int = 0
    stomps_won: int = 0
    stomps_lost: int = 0

    @property
    def winrate(self) -> float:
        return self.wins / self.games_played if self.games_played else 0.0

    @property
    def ot_rate(self) -> float:
        return self.ot_count / self.games_played if self.games_played else 0.0

    @property
    def atk_round_rate(self) -> float:
        return self.atk_rounds_won / self.atk_rounds_played if self.atk_rounds_played else 0.0

    @property
    def def_round_rate(self) -> float:
        return self.def_rounds_won / self.def_rounds_played if self.def_rounds_played else 0.0

    @property
    def pistol_rate(self) -> float:
        return self.pistols_won / self.pistols_played if self.pistols_played else 0.0

    @property
    def pistol_conversion_rate(self) -> float:
        return self.pistol_conversions / self.pistols_won if self.pistols_won else 0.0

    @property
    def close_rate(self) -> float:
        return self.close_maps / self.games_played if self.games_played else 0.0


@dataclass
class MapAnalysis:
    """Analysis results for a single map in a matchup."""
    map_name: str
    map_order: int
    pick_team: Optional[str] = None
    team_a_stats: Optional[TeamStats] = None
    team_b_stats: Optional[TeamStats] = None
    p_team_a_win: float = 0.5
    p_ot: float = 0.0
    p_close: float = 0.0
    confidence: str = "low"
    sample_size: int = 0
    factors: dict = field(default_factory=dict)


@dataclass
class MarketOdds:
    """Odds for a single market from a bookmaker."""
    bookmaker: str
    market_type: str
    selection: str
    odds_value: float
    map_number: Optional[int] = None

    @property
    def p_impl(self) -> float:
        return 1.0 / self.odds_value if self.odds_value > 0 else 0.0


@dataclass
class EdgeResult:
    """Result of an edge calculation."""
    market: str
    selection: str
    bookmaker: str
    odds: float
    p_impl: float
    p_model: float
    edge: float
    confidence: str
    sample_size: int
    map_number: Optional[int] = None
    recommendation: str = ""
    suggested_stake: float = 0.0
    factors: dict = field(default_factory=dict)


@dataclass
class MultiBetOpportunity:
    """A multi-bet opportunity (spread, parlay, hedge, correct score)."""
    strategy: str
    description: str
    legs: list[EdgeResult] = field(default_factory=list)
    total_stake: float = 0.0
    min_payout: float = 0.0
    combined_odds: float = 0.0
    p_model: float = 0.0
    p_impl: float = 0.0
    edge: float = 0.0
    ev: float = 0.0
    details: dict = field(default_factory=dict)


@dataclass
class MatchAnalysis:
    """Full analysis for a match."""
    match_id: int
    event_name: str
    stage_name: str
    bo_type: str
    team_a_name: str
    team_b_name: str
    team_a_id: int
    team_b_id: int
    h2h_event: tuple[int, int] = (0, 0)
    maps: list[MapAnalysis] = field(default_factory=list)
    series_p_a_win: float = 0.5
    score_probs: dict[str, float] = field(default_factory=dict)
    single_edges: list[EdgeResult] = field(default_factory=list)
    multi_bets: list[MultiBetOpportunity] = field(default_factory=list)
