"""Pydantic schemas for report endpoints."""

from datetime import datetime

from pydantic import BaseModel


class ReportGenerateRequest(BaseModel):
    analysis_id: str


class ReportGenerateResponse(BaseModel):
    report_id: str
    status: str = "generated"


class ReportResponse(BaseModel):
    id: str
    analysis_id: str | None = None
    analysis_input: dict
    ai_provider: str
    report_content: str
    validation_passed: bool
    created_at: datetime


class ReportListItem(BaseModel):
    id: str
    analysis_id: str = ""
    filename: str = ""
    created_at: datetime


class ReportsListResponse(BaseModel):
    reports: list[ReportListItem]
    total: int
