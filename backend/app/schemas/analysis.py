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


class StatsResponse(BaseModel):
    total_trades: int
    total_positions: int
    unknown_cost_count: int = 0
    win_count: int
    win_rate: float
    total_pnl: float
    avg_holding_days: float
    max_win: float
    max_loss: float
    consecutive_losses: int
    positions: list[PositionItem]


class InsightPatternItem(BaseModel):
    pattern_name: str
    count: int
    win_count: int
    win_rate: float
    total_pnl: float
    avg_pnl_pct: float


class InsightResponse(BaseModel):
    patterns: list[InsightPatternItem]
    best_pattern: Optional[InsightPatternItem] = None
    worst_pattern: Optional[InsightPatternItem] = None


class ImpactItem(BaseModel):
    removed_pattern: str
    original_return: float
    what_if_return: float
    delta: float
    impact_score: float


class WhatIfResponse(BaseModel):
    items: list[ImpactItem]
