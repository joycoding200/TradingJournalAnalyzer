from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from sqlalchemy import text

from app.config import settings
from app.database import engine, Base, SessionLocal
from app.api import api_router
from app.logging_config import setup_logging, get_logger
from app.ratelimit import limiter

# Import all models so Base.metadata knows about them
import app.models  # noqa: F401


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    logger = get_logger(__name__)
    logger.info("TradeDoctor starting up (ENV=%s)", settings.env)

    # Development convenience: create_all is safe for prototyping.
    # Production deployments MUST use Alembic instead:
    #   cd backend && alembic upgrade head
    # This avoids table drift (create_all cannot handle ALTER COLUMN, ADD COLUMN, etc.).
    Base.metadata.create_all(bind=engine)

    # Backfill: migrate existing single-file analyses to analysis_files table
    _backfill_analysis_files()

    yield

    logger.info("TradeDoctor shutting down")


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


app = FastAPI(title="TradeDoctor API", version="1.0.0", lifespan=lifespan)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


async def _validation_exception_handler(request: Request, exc: RequestValidationError):
    """Convert Pydantic validation errors to user-friendly Chinese messages."""
    messages: list[str] = []
    for err in exc.errors():
        loc = err.get("loc", [])
        field = str(loc[-1]) if loc else ""
        msg = err.get("msg", "")

        # Translate common validation errors to plain Chinese
        if "value is not a valid email address" in msg:
            messages.append("邮箱格式不正确")
        elif "手机号格式不正确" in msg:
            messages.append("手机号格式不正确，请输入11位中国大陆手机号")
        elif "field required" in msg:
            messages.append(f"请填写{f'「{field}」' if field else '必填项'}")
        elif "string_too_short" in msg or "string_too_long" in msg:
            messages.append(f"{f'「{field}」' if field else '输入'}长度不符合要求")
        elif "ensure this value has at least" in msg:
            messages.append("密码至少需要 8 个字符")
        elif "Value error" in msg:
            # Our own field validators — extract the actual message
            clean = msg.split(", ", 1)[-1] if ", " in msg else msg
            messages.append(clean)
        else:
            messages.append("输入信息有误，请检查后重试")

    detail = "；".join(messages) if messages else "输入信息有误，请检查后重试"
    return JSONResponse(status_code=422, content={"detail": detail})


app.add_exception_handler(RequestValidationError, _validation_exception_handler)

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
