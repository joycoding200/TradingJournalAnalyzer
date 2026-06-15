"""Pydantic schemas for analysis endpoints."""

from datetime import date
from typing import Optional

from pydantic import BaseModel


class AnalysisRunRequest(BaseModel):
    date_start: date
    date_end: date


class AnalysisRunResponse(BaseModel):
    analysis_id: str


class PositionItem(BaseModel):
    symbol: str
    asset_type: str
    entry_date: date
    exit_date: date
    holding_days: int
    total_quantity: float
    avg_entry_price: float
    avg_exit_price: float
    pnl: float
    pnl_pct: float
    trade_ids: list[str]


class OutcomeItem(BaseModel):
    label: str
    count: int


class StatsResponse(BaseModel):
    total_trades: int
    total_positions: int
    unknown_cost_count: int = 0
    win_count: int
    loss_count: int = 0
    win_rate: float
    total_pnl: float
    avg_holding_days: float
    avg_win_holding_days: float = 0.0
    avg_loss_holding_days: float = 0.0
    max_win: float
    max_loss: float
    max_win_symbol: str = ""
    max_win_date: str = ""
    max_loss_symbol: str = ""
    max_loss_date: str = ""
    consecutive_losses: int
    profit_factor: float = 0.0
    avg_win_amount: float = 0.0
    avg_loss_amount: float = 0.0
    win_loss_ratio: float = 0.0
    max_drawdown: float = 0.0
    # V2.5 percentage versions (industry standard)
    max_drawdown_pct: float = 0.0
    total_return_pct: float = 0.0
    avg_win_pct: float = 0.0
    avg_loss_pct: float = 0.0
    outcome_distribution: list[OutcomeItem] = []
    positions: list[PositionItem]
    # V1.2 MAE/MFE
    avg_mae: float = 0.0
    avg_mfe: float = 0.0
    mae_winners: float = 0.0
    mae_losers: float = 0.0
    profit_capture_ratio: float = 0.0
    # V1.3 Expectancy
    expectancy: float = 0.0


class InsightPatternItem(BaseModel):
    pattern_name: str
    count: int
    win_count: int
    win_rate: float
    total_pnl: float
    avg_pnl_pct: float
    expectancy: float = 0.0
    gross_profit: float = 0.0
    gross_loss: float = 0.0


class InsightResponse(BaseModel):
    patterns: list[InsightPatternItem]  # flat list (backward compat)
    # V1.1: 4-dimension system
    market_env: list[InsightPatternItem] = []
    behavior: list[InsightPatternItem] = []
    outcome: list[InsightPatternItem] = []
    psychology: list[InsightPatternItem] = []
    # Legacy fields maintained for backward compat
    entry_patterns: list[InsightPatternItem] = []
    holding_patterns: list[InsightPatternItem] = []
    risk_patterns: list[InsightPatternItem] = []
    exit_patterns: list[InsightPatternItem] = []
    categories: dict[str, list[InsightPatternItem]] = {}
    best_pattern: Optional[InsightPatternItem] = None
    worst_pattern: Optional[InsightPatternItem] = None
    baseline_expectancy: float = 0.0  # V2.3 overall expectancy for comparison


class AttributionItem(BaseModel):
    removed_pattern: str
    original_return: float
    what_if_return: float
    delta: float
    contribution_pct: float
    absolute_impact: float = 0.0


class RuleSimulationItem(BaseModel):
    rule: str
    original_return: float
    what_if_return: float
    delta: float
    affected_positions: int


class ShapleyItem(BaseModel):
    pattern_name: str
    shapley_value: float
    pct_of_total: float = 0.0


class WhatIfResponse(BaseModel):
    items: list[AttributionItem]  # factor contribution (original)
    stop_loss: Optional[RuleSimulationItem] = None
    shapley: list[ShapleyItem] = []  # V2.0 Shapley attribution
