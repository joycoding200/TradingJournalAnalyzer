"""API router aggregator."""

from fastapi import APIRouter

from app.api.admin import router as admin_router
from app.api.auth import router as auth_router
from app.api.upload import router as upload_router
from app.api.analysis import router as analysis_router
from app.api.report import router as report_router
from app.api.case_library import router as case_library_router

api_router = APIRouter()
api_router.include_router(admin_router)
api_router.include_router(auth_router)
api_router.include_router(upload_router)
api_router.include_router(analysis_router)
api_router.include_router(report_router)
api_router.include_router(case_library_router)
