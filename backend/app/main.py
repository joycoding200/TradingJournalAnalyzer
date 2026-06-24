from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from sqlalchemy import text

from app.config import settings
from app.database import engine, Base, SessionLocal
from app.api import api_router
from app.ratelimit import limiter

# Import all models so Base.metadata knows about them
import app.models  # noqa: F401


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Development convenience: create_all is safe for prototyping.
    # Production deployments MUST use Alembic instead:
    #   cd backend && alembic upgrade head
    # This avoids table drift (create_all cannot handle ALTER COLUMN, ADD COLUMN, etc.).
    Base.metadata.create_all(bind=engine)

    # Backfill: migrate existing single-file analyses to analysis_files table
    _backfill_analysis_files()

    yield


def _backfill_analysis_files():
    """Ensure legacy analyses are represented in the analysis_files join table.

    Checks for orphaned records first — if there's nothing to backfill the
    function returns immediately, avoiding unnecessary INSERT attempts on
    every startup.
    """
    db = SessionLocal()
    try:
        # Check if the analysis_files table exists (created by create_all)
        db.execute(text("SELECT 1 FROM analysis_files LIMIT 0"))
    except Exception:
        db.close()
        return  # table doesn't exist yet (first run before create_all?)

    try:
        # Quick count — skip the INSERT entirely when there are no orphans
        orphan_count = db.execute(
            text(
                "SELECT COUNT(*) FROM analyses "
                "WHERE raw_file_id IS NOT NULL "
                "AND (id, raw_file_id) NOT IN (SELECT analysis_id, raw_file_id FROM analysis_files)"
            )
        ).scalar()
        if not orphan_count:
            db.close()
            return

        result = db.execute(
            text(
                "INSERT INTO analysis_files (analysis_id, raw_file_id) "
                "SELECT id, raw_file_id FROM analyses "
                "WHERE raw_file_id IS NOT NULL "
                "AND (id, raw_file_id) NOT IN (SELECT analysis_id, raw_file_id FROM analysis_files) "
                "ON CONFLICT DO NOTHING"
            )
        )
        db.commit()
        if result.rowcount and result.rowcount > 0:
            import logging
            logging.getLogger(__name__).info(
                f"Backfilled {result.rowcount} analysis-file associations"
            )
    except Exception:
        db.rollback()
    finally:
        db.close()


app = FastAPI(title="TradingJournalAnalyzer API", version="0.1.0", lifespan=lifespan)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_exceptions(request: Request, call_next):
    """Log unhandled HTTP exceptions with stack traces for production debugging."""
    try:
        return await call_next(request)
    except Exception:
        import logging
        logger = logging.getLogger(__name__)
        logger.exception(f"Unhandled exception on {request.method} {request.url.path}")
        raise


app.include_router(api_router)


@app.get("/api/health")
def health():
    return {"status": "ok"}
