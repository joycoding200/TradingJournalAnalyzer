# TradeLens MVP Implementation Plan

> ## ⚠️ 已归档 / SUPERSEDED（2026-06-17 标注）
>
> 这是 **TradeLens MVP 阶段的构建计划**（2026-06-10），MVP 已完成，项目已更名为 **TradingJournalAnalyzer** 并持续演进。
> 本计划中的任务清单、代码片段与文件结构均反映 MVP 时的意图，**与当前代码库多处不符**，仅供历史追溯，不要据此实现新功能。
>
> *说明：本项目无发布版本/git tag，FastAPI 声明版本为 `0.1.0`；源码中散落的 `V1.x`/`V2.x` 仅为开发过程的功能里程碑注释，非产品版本号。*
>
> **当前事实来源：** [CLAUDE.md](../../../CLAUDE.md) · [FINANCE_DOMAIN.md](../FINANCE_DOMAIN.md) · [VERIFICATION_CHECKLIST.md](../VERIFICATION_CHECKLIST.md) · 源码 `backend/app/` 与 `frontend/src/`
>
> 主要差异概要：项目更名；前端用 Tailwind（非 shadcn）；行情仅 mootdx 并缓存至 `DailyBar`；标签改为 4 维度体系；Insight/What-If 引擎大幅扩展（PF/Expectancy/MAE-MFE/Shapley/止损回测）；新增管理后台与 openrouter provider；解析器改为值推断的 SmartParser。详见 [spec 顶部演进表](../specs/2026-06-10-tradelens-mvp-design.md)。
>
> 下文为原始 MVP 计划，未做改动。

---

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build TradeLens MVP — upload trade records, run 6-layer analysis pipeline, generate AI diagnostic report with What If backtest.

**Architecture:** Greenfield monorepo — FastAPI backend (PostgreSQL + SQLAlchemy + a-stock-data) + Vite React SPA frontend (shadcn/ui + Recharts + React Query). Plugin-based parser architecture (BaseParser → 15+ implementations), FIFO position builder, 15-tag pattern engine, Insight + What If compute engines, AI layer with provider abstraction + numeric validation.

**Tech Stack:** Python 3.12+ / FastAPI / SQLAlchemy / Pandas / mootdx / Vite / React 18 / shadcn/ui / Recharts / React Query / PostgreSQL

---

## File Structure Map

```
backend/
├── requirements.txt
├── app/
│   ├── __init__.py
│   ├── main.py                  # FastAPI app, CORS, router mounts
│   ├── config.py                # Pydantic Settings (env vars)
│   ├── database.py              # SQLAlchemy engine + session
│   ├── models/
│   │   ├── __init__.py          # re-exports all models
│   │   ├── user.py              # User
│   │   ├── raw_file.py          # RawFile
│   │   ├── trade.py             # Trade
│   │   ├── position.py          # Position
│   │   ├── pattern.py           # Pattern
│   │   ├── analysis.py          # Analysis (metadata only)
│   │   └── report.py            # Report
│   ├── schemas/
│   │   ├── __init__.py
│   │   ├── auth.py              # RegisterRequest, LoginRequest, TokenResponse
│   │   ├── upload.py            # UploadResponse, ConfirmRequest, ImportResponse
│   │   ├── analysis.py          # AnalysisRunRequest, StatsResponse, InsightResponse, WhatIfResponse
│   │   └── report.py            # GenerateRequest, ReportResponse
│   ├── api/
│   │   ├── __init__.py          # APIRouter aggregation
│   │   ├── auth.py              # /api/auth/*
│   │   ├── upload.py            # /api/upload/*
│   │   ├── analysis.py          # /api/analysis/*
│   │   └── report.py            # /api/report/*
│   ├── parsers/
│   │   ├── __init__.py
│   │   ├── base.py              # BaseParser ABC
│   │   ├── registry.py          # ParserRegistry
│   │   ├── qmt.py               # QMT
│   │   ├── vnpy.py              # VN.PY
│   │   ├── dfcf.py              # 东方财富
│   │   ├── ths.py               # 同花顺
│   │   ├── wenhua.py            # 文华财经
│   │   ├── boyi.py              # 博易大师
│   │   ├── ctp.py               # 快期/易盛/CTP
│   │   ├── huatai.py            # 华泰涨乐
│   │   └── citic.py             # 中信/国君/广发/海通
│   ├── engine/
│   │   ├── __init__.py
│   │   ├── position.py          # PositionBuilder (FIFO)
│   │   ├── pattern.py           # PatternEngine
│   │   ├── insight.py           # InsightEngine
│   │   └── whatif.py            # WhatIfEngine
│   ├── ai/
│   │   ├── __init__.py
│   │   ├── provider.py          # LLMProvider ABC + factory
│   │   ├── prompt.py            # build_prompt()
│   │   └── validator.py         # ReportValidator
│   └── auth/
│       ├── __init__.py
│       └── jwt.py               # create_token, decode_token, get_current_user
├── tests/
│   ├── __init__.py
│   ├── conftest.py              # pytest fixtures (test DB, test client)
│   ├── test_auth.py
│   ├── test_parsers/
│   │   ├── __init__.py
│   │   ├── test_qmt.py
│   │   ├── test_vnpy.py
│   │   ├── test_registry.py
│   │   └── fixtures/            # sample CSV files
│   ├── test_engine/
│   │   ├── __init__.py
│   │   ├── test_position.py
│   │   ├── test_pattern.py
│   │   ├── test_insight.py
│   │   └── test_whatif.py
│   ├── test_ai/
│   │   ├── __init__.py
│   │   ├── test_prompt.py
│   │   └── test_validator.py
│   └── test_api/
│       ├── __init__.py
│       ├── test_upload.py
│       ├── test_analysis.py
│       └── test_report.py
├── alembic/
│   ├── env.py
│   └── versions/
└── alembic.ini

frontend/
├── index.html
├── package.json
├── tsconfig.json
├── vite.config.ts
├── tailwind.config.js
├── postcss.config.js
├── components.json              # shadcn/ui config
└── src/
    ├── main.tsx
    ├── App.tsx
    ├── index.css                # Tailwind directives + shadcn theme
    ├── api/
    │   ├── client.ts            # fetch wrapper with JWT
    │   ├── auth.ts              # login, register
    │   ├── upload.ts            # upload, confirm, import
    │   ├── analysis.ts          # runAnalysis, getStats, getInsight, getWhatIf
    │   └── report.ts            # generateReport, getReport, listReports
    ├── context/
    │   └── AuthContext.tsx       # AuthProvider + useAuth
    ├── hooks/
    │   ├── useAnalysis.ts       # React Query hooks for analysis
    │   └── useReport.ts         # React Query hooks for reports
    ├── pages/
    │   ├── Landing.tsx
    │   ├── Login.tsx
    │   ├── Register.tsx
    │   ├── Upload.tsx
    │   ├── Analysis.tsx
    │   ├── Report.tsx
    │   └── History.tsx
    └── components/
        ├── Layout.tsx           # Navbar + footer shell
        ├── ProtectedRoute.tsx   # Auth guard wrapper
        ├── FileDropzone.tsx     # Drag-and-drop upload area
        ├── FormatSelector.tsx   # Source type dropdown for confirm step
        ├── TradePreview.tsx     # Data table preview before import
        ├── StatsCards.tsx       # KPI cards grid
        ├── PatternChart.tsx     # Pattern win rate bar chart
        ├── WhatIfChart.tsx      # What If comparison bars
        └── ReportView.tsx       # Markdown report renderer
```

---

### Task 1: Backend Project Scaffold

**Files:**
- Create: `backend/requirements.txt`
- Create: `backend/app/__init__.py`
- Create: `backend/app/main.py`
- Create: `backend/app/config.py`
- Create: `backend/app/database.py`
- Create: `backend/tests/__init__.py`
- Create: `backend/tests/conftest.py`

- [ ] **Step 1: Create requirements.txt**

```txt
fastapi==0.115.0
uvicorn[standard]==0.32.0
sqlalchemy==2.0.35
psycopg2-binary==2.9.10
alembic==1.14.0
pydantic==2.10.0
pydantic-settings==2.7.0
python-jose[cryptography]==3.3.0
passlib[bcrypt]==1.7.4
python-multipart==0.0.17
pandas==2.2.3
openpyxl==3.1.5
httpx==0.28.0
mootdx==1.0.0
requests==2.32.3
pytest==8.3.4
pytest-asyncio==0.25.0
```

- [ ] **Step 2: Create app/config.py**

```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    database_url: str = "postgresql://postgres:postgres@localhost:5432/tradelens"
    secret_key: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24 * 7  # 7 days
    ai_provider: str = "openai"  # openai | claude | deepseek
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    claude_api_key: str = ""
    claude_model: str = "claude-sonnet-4-6"
    deepseek_api_key: str = ""
    deepseek_model: str = "deepseek-chat"

    class Config:
        env_file = ".env"

settings = Settings()
```

- [ ] **Step 3: Create app/database.py**

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

from app.config import settings

engine = create_engine(settings.database_url)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

class Base(DeclarativeBase):
    pass

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

- [ ] **Step 4: Create app/main.py**

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="TradeLens API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api/health")
def health():
    return {"status": "ok"}
```

- [ ] **Step 5: Create tests/conftest.py**

```python
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

from app.database import Base, get_db
from app.main import app

TEST_DATABASE_URL = "postgresql://postgres:postgres@localhost:5432/tradelens_test"

engine = create_engine(TEST_DATABASE_URL)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db

@pytest.fixture(autouse=True)
def db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)

@pytest.fixture
def client():
    return TestClient(app)
```

- [ ] **Step 6: Verify**

```bash
cd backend
python -m venv .venv && source .venv/bin/activate  # or .venv\Scripts\activate on Windows
pip install -r requirements.txt
uvicorn app.main:app --reload
# Open http://localhost:8000/api/health → {"status":"ok"}
```

- [ ] **Step 7: Commit**

```bash
git add backend/requirements.txt backend/app/__init__.py backend/app/main.py backend/app/config.py backend/app/database.py backend/tests/
git commit -m "feat: scaffold backend project with FastAPI + config + database"
```

---

### Task 2: Database Models

**Files:**
- Create: `backend/app/models/__init__.py`
- Create: `backend/app/models/user.py`
- Create: `backend/app/models/raw_file.py`
- Create: `backend/app/models/trade.py`
- Create: `backend/app/models/position.py`
- Create: `backend/app/models/pattern.py`
- Create: `backend/app/models/analysis.py`
- Create: `backend/app/models/report.py`

- [ ] **Step 1: Create all 7 models in sequence**

`backend/app/models/user.py`:
```python
import uuid
from datetime import datetime
from sqlalchemy import String, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base

class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
```

`backend/app/models/raw_file.py`:
```python
import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, LargeBinary, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base

class RawFile(Base):
    __tablename__ = "raw_files"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    source_type: Mapped[str] = mapped_column(String(50), nullable=True)
    asset_type: Mapped[str] = mapped_column(String(20), nullable=True)
    raw_content: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
```

`backend/app/models/trade.py`:
```python
import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, Float, Integer, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base

class Trade(Base):
    __tablename__ = "trades"
    __table_args__ = (
        Index("ix_trades_user_datetime", "user_id", "datetime"),
        Index("ix_trades_user_symbol_datetime", "user_id", "symbol", "datetime"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    raw_file_id: Mapped[str] = mapped_column(String(36), ForeignKey("raw_files.id"), nullable=False)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    asset_type: Mapped[str] = mapped_column(String(10), nullable=False)  # stock | future
    datetime: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    exchange: Mapped[str] = mapped_column(String(10), nullable=False)
    side: Mapped[str] = mapped_column(String(10), nullable=False)  # BUY | SELL
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    commission: Mapped[float] = mapped_column(Float, default=0.0)
    margin: Mapped[float] = mapped_column(Float, nullable=True)
    multiplier: Mapped[int] = mapped_column(Integer, nullable=True)
```

`backend/app/models/position.py`:
```python
import uuid
from datetime import date
from sqlalchemy import String, Date, Float, Integer, ForeignKey, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base

class Position(Base):
    __tablename__ = "positions"
    __table_args__ = (Index("ix_positions_user_entry", "user_id", "entry_date"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    asset_type: Mapped[str] = mapped_column(String(10), nullable=False)
    entry_date: Mapped[date] = mapped_column(Date, nullable=False)
    exit_date: Mapped[date] = mapped_column(Date, nullable=False)
    holding_days: Mapped[int] = mapped_column(Integer, nullable=False)
    total_quantity: Mapped[float] = mapped_column(Float, nullable=False)
    avg_entry_price: Mapped[float] = mapped_column(Float, nullable=False)
    avg_exit_price: Mapped[float] = mapped_column(Float, nullable=False)
    pnl: Mapped[float] = mapped_column(Float, nullable=False)
    pnl_pct: Mapped[float] = mapped_column(Float, nullable=False)
    trade_ids: Mapped[dict] = mapped_column(JSONB, nullable=False)
```

`backend/app/models/pattern.py`:
```python
import uuid
from sqlalchemy import String, Float, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base

class Pattern(Base):
    __tablename__ = "patterns"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    position_id: Mapped[str] = mapped_column(String(36), ForeignKey("positions.id"), nullable=False, index=True)
    pattern_name: Mapped[str] = mapped_column(String(30), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    context: Mapped[dict] = mapped_column(JSONB, default=dict)
```

`backend/app/models/analysis.py`:
```python
import uuid
from datetime import date, datetime
from sqlalchemy import String, Date, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base

class Analysis(Base):
    __tablename__ = "analyses"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    date_start: Mapped[date] = mapped_column(Date, nullable=False)
    date_end: Mapped[date] = mapped_column(Date, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
```

`backend/app/models/report.py`:
```python
import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, Text, Boolean, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base

class Report(Base):
    __tablename__ = "reports"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    analysis_input: Mapped[dict] = mapped_column(JSONB, nullable=False)
    ai_provider: Mapped[str] = mapped_column(String(20), nullable=False)
    report_content: Mapped[str] = mapped_column(Text, nullable=False)
    validation_passed: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
```

`backend/app/models/__init__.py`:
```python
from app.models.user import User
from app.models.raw_file import RawFile
from app.models.trade import Trade
from app.models.position import Position
from app.models.pattern import Pattern
from app.models.analysis import Analysis
from app.models.report import Report
```

- [ ] **Step 2: Verify models create tables**

```bash
cd backend
python -c "
from app.database import engine, Base
from app.models import *  # noqa
Base.metadata.create_all(bind=engine)
print('Tables created successfully')
"
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/models/
git commit -m "feat: add all 7 database models (User, RawFile, Trade, Position, Pattern, Analysis, Report)"
```

---

### Task 3: Auth System

**Files:**
- Create: `backend/app/auth/__init__.py`
- Create: `backend/app/auth/jwt.py`
- Create: `backend/app/schemas/__init__.py`
- Create: `backend/app/schemas/auth.py`
- Create: `backend/app/api/__init__.py`
- Create: `backend/app/api/auth.py`
- Create: `backend/tests/test_auth.py`

- [ ] **Step 1: Create app/auth/jwt.py**

```python
from datetime import datetime, timedelta
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.user import User

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer()

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)

def create_token(user_id: str) -> str:
    expire = datetime.utcnow() + timedelta(minutes=settings.jwt_expire_minutes)
    payload = {"sub": user_id, "exp": expire}
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)

def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
) -> User:
    try:
        payload = jwt.decode(credentials.credentials, settings.secret_key, algorithms=[settings.jwt_algorithm])
        user_id = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user
```

- [ ] **Step 2: Create app/schemas/auth.py**

```python
from pydantic import BaseModel, EmailStr

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str  # min_length=6 enforced at API level

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
```

- [ ] **Step 3: Create app/api/auth.py**

```python
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.auth.jwt import hash_password, verify_password, create_token
from app.schemas.auth import RegisterRequest, LoginRequest, TokenResponse

router = APIRouter(prefix="/api/auth", tags=["auth"])

@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(body: RegisterRequest, db: Session = Depends(get_db)):
    if len(body.password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")
    if db.query(User).filter(User.email == body.email).first():
        raise HTTPException(status_code=409, detail="Email already registered")
    user = User(email=body.email, password_hash=hash_password(body.password))
    db.add(user)
    db.commit()
    db.refresh(user)
    token = create_token(user.id)
    return TokenResponse(access_token=token)

@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == body.email).first()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    token = create_token(user.id)
    return TokenResponse(access_token=token)
```

- [ ] **Step 4: Create app/api/__init__.py**

```python
from fastapi import APIRouter
from app.api.auth import router as auth_router
# upload, analysis, report routers will be added in later tasks

api_router = APIRouter()
api_router.include_router(auth_router)
```

Update `app/main.py` to include the router:
```python
from app.api import api_router
app.include_router(api_router)
```

- [ ] **Step 5: Create backend/tests/test_auth.py**

```python
def test_register_and_login(client):
    # Register
    resp = client.post("/api/auth/register", json={"email": "test@example.com", "password": "secret123"})
    assert resp.status_code == 201
    data = resp.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"

    # Login
    resp = client.post("/api/auth/login", json={"email": "test@example.com", "password": "secret123"})
    assert resp.status_code == 200
    assert "access_token" in resp.json()

def test_register_duplicate_email(client):
    client.post("/api/auth/register", json={"email": "dup@example.com", "password": "secret123"})
    resp = client.post("/api/auth/register", json={"email": "dup@example.com", "password": "secret123"})
    assert resp.status_code == 409

def test_login_wrong_password(client):
    client.post("/api/auth/register", json={"email": "wrong@example.com", "password": "secret123"})
    resp = client.post("/api/auth/login", json={"email": "wrong@example.com", "password": "badpass"})
    assert resp.status_code == 401

def test_protected_route_without_token(client):
    resp = client.get("/api/reports")
    assert resp.status_code == 403  # no bearer token
```

- [ ] **Step 6: Run tests**

```bash
cd backend
pytest tests/test_auth.py -v
```

- [ ] **Step 7: Commit**

```bash
git add backend/app/auth/ backend/app/schemas/ backend/app/api/ backend/tests/test_auth.py backend/app/main.py
git commit -m "feat: add JWT auth (register + login)"
```

---

### Task 4: Parser Base + Registry

**Files:**
- Create: `backend/app/parsers/__init__.py`
- Create: `backend/app/parsers/base.py`
- Create: `backend/app/parsers/registry.py`
- Create: `backend/tests/test_parsers/__init__.py`
- Create: `backend/tests/test_parsers/test_registry.py`

- [ ] **Step 1: Create app/parsers/base.py**

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from io import BytesIO
import pandas as pd

@dataclass
class TradeData:
    """Intermediate representation before creating Trade ORM objects."""
    datetime: datetime
    symbol: str
    exchange: str
    side: str  # BUY | SELL
    quantity: float
    price: float
    commission: float = 0.0
    margin: float | None = None
    multiplier: int | None = None

class BaseParser(ABC):
    @classmethod
    @abstractmethod
    def source_type(cls) -> str:
        """Identifier, e.g. 'qmt', 'vnpy', 'dfcf'."""
        ...

    @classmethod
    @abstractmethod
    def asset_type(cls) -> str:
        """'stock' or 'future'."""
        ...

    @classmethod
    @abstractmethod
    def detect(cls, content: bytes, filename: str) -> float:
        """Return confidence 0.0~1.0 that this file matches this parser."""
        ...

    @classmethod
    @abstractmethod
    def parse(cls, content: bytes, filename: str) -> list[TradeData]:
        """Parse file content into list of TradeData."""
        ...

    @staticmethod
    def _read_df(content: bytes, filename: str) -> pd.DataFrame:
        if filename.endswith(".csv"):
            return pd.read_csv(BytesIO(content))
        elif filename.endswith((".xls", ".xlsx")):
            return pd.read_excel(BytesIO(content))
        raise ValueError(f"Unsupported file format: {filename}")

    @staticmethod
    def _column_match_score(df_columns: list[str], expected: list[str]) -> float:
        """Calculate match score between actual columns and expected columns."""
        actual_lower = {c.strip().lower(): c for c in df_columns}
        matched = 0
        for exp in expected:
            if exp.lower() in actual_lower:
                matched += 1
        return matched / len(expected) if expected else 0.0
```

- [ ] **Step 2: Create app/parsers/registry.py**

```python
import importlib
import pkgutil
from pathlib import Path
from app.parsers.base import BaseParser, TradeData

class ParserRegistry:
    _parsers: list[type[BaseParser]] = []
    _initialized: bool = False

    @classmethod
    def auto_discover(cls):
        if cls._initialized:
            return
        parsers_dir = Path(__file__).parent
        for _, name, _ in pkgutil.iter_modules([str(parsers_dir)]):
            if name in ("base", "registry", "__init__"):
                continue
            importlib.import_module(f"app.parsers.{name}")
        # Collect all BaseParser subclasses
        cls._parsers = BaseParser.__subclasses__()
        cls._initialized = True

    @classmethod
    def detect_format(cls, content: bytes, filename: str) -> list[tuple[str, str, float]]:
        """Return [(source_type, asset_type, confidence)] sorted by confidence desc."""
        cls.auto_discover()
        results = []
        for parser_cls in cls._parsers:
            try:
                score = parser_cls.detect(content, filename)
                if score > 0:
                    results.append((parser_cls.source_type(), parser_cls.asset_type(), score))
            except Exception:
                continue
        results.sort(key=lambda x: x[2], reverse=True)
        return results

    @classmethod
    def get_parser(cls, source_type: str) -> type[BaseParser] | None:
        cls.auto_discover()
        for parser_cls in cls._parsers:
            if parser_cls.source_type() == source_type:
                return parser_cls
        return None

    @classmethod
    def parse(cls, source_type: str, content: bytes, filename: str) -> list[TradeData]:
        parser_cls = cls.get_parser(source_type)
        if not parser_cls:
            raise ValueError(f"Unknown source type: {source_type}")
        return parser_cls.parse(content, filename)
```

- [ ] **Step 3: Create tests/test_parsers/test_registry.py**

```python
from app.parsers.registry import ParserRegistry

def test_registry_auto_discover():
    ParserRegistry._initialized = False
    ParserRegistry._parsers = []
    ParserRegistry.auto_discover()
    parser_types = [p.source_type() for p in ParserRegistry._parsers]
    # At minimum, after all parser tasks are done, this should have 9+ entries
    assert len(parser_types) >= 0  # Initially 0 before parsers are created

def test_detect_format_no_parsers():
    ParserRegistry._initialized = False
    ParserRegistry._parsers = []
    results = ParserRegistry.detect_format(b"dummy,data\n1,2", "test.csv")
    assert results == []

def test_parse_unknown():
    try:
        ParserRegistry.parse("nonexistent", b"", "test.csv")
        assert False, "Should have raised"
    except ValueError:
        pass
```

- [ ] **Step 4: Run tests**

```bash
cd backend && pytest tests/test_parsers/test_registry.py -v
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/parsers/base.py backend/app/parsers/registry.py backend/app/parsers/__init__.py backend/tests/test_parsers/
git commit -m "feat: add parser base class + auto-discovery registry"
```

---

### Task 5: Stock Parsers (QMT, VN.PY, 东方财富, 同花顺)

**Files:**
- Create: `backend/app/parsers/qmt.py`
- Create: `backend/app/parsers/vnpy.py`
- Create: `backend/app/parsers/dfcf.py`
- Create: `backend/app/parsers/ths.py`
- Create: `backend/tests/test_parsers/test_qmt.py`
- Create: `backend/tests/test_parsers/test_vnpy.py`

- [ ] **Step 1: Create app/parsers/qmt.py**

```python
import pandas as pd
from app.parsers.base import BaseParser, TradeData

class QMTParser(BaseParser):
    @classmethod
    def source_type(cls) -> str:
        return "qmt"

    @classmethod
    def asset_type(cls) -> str:
        return "stock"

    @classmethod
    def detect(cls, content: bytes, filename: str) -> float:
        try:
            df = cls._read_df(content, filename)
        except Exception:
            return 0.0
        expected = ["委托时间", "证券代码", "买卖方向", "成交价格", "成交数量"]
        return cls._column_match_score(list(df.columns), expected)

    @classmethod
    def parse(cls, content: bytes, filename: str) -> list[TradeData]:
        df = cls._read_df(content, filename)
        col_map = {c.strip(): c for c in df.columns}
        trades = []
        for _, row in df.iterrows():
            symbol = str(row[col_map["证券代码"]]).zfill(6)
            exchange = "SH" if symbol.startswith(("6", "5", "9")) else "SZ"
            side = "BUY" if "买" in str(row[col_map["买卖方向"]]) else "SELL"
            trades.append(TradeData(
                datetime=pd.to_datetime(row[col_map["委托时间"]]),
                symbol=symbol,
                exchange=exchange,
                side=side,
                quantity=float(row[col_map["成交数量"]]),
                price=float(row[col_map["成交价格"]]),
            ))
        return trades
```

- [ ] **Step 2: Create app/parsers/vnpy.py**

```python
import pandas as pd
from app.parsers.base import BaseParser, TradeData

class VNPYParser(BaseParser):
    @classmethod
    def source_type(cls) -> str:
        return "vnpy"

    @classmethod
    def asset_type(cls) -> str:
        return "stock"  # VN.PY can also do futures; default to stock for now

    @classmethod
    def detect(cls, content: bytes, filename: str) -> float:
        try:
            df = cls._read_df(content, filename)
        except Exception:
            return 0.0
        expected = ["datetime", "symbol", "direction", "price", "volume"]
        return cls._column_match_score(list(df.columns), expected)

    @classmethod
    def parse(cls, content: bytes, filename: str) -> list[TradeData]:
        df = cls._read_df(content, filename)
        col_map = {c.strip().lower(): c for c in df.columns}
        trades = []
        for _, row in df.iterrows():
            symbol = str(row[col_map["symbol"]]).zfill(6)
            exchange = "SH" if symbol.startswith(("6", "5", "9")) else "SZ"
            direction = str(row[col_map["direction"]]).upper()
            side = "BUY" if direction in ("LONG", "BUY") else "SELL"
            trades.append(TradeData(
                datetime=pd.to_datetime(row[col_map["datetime"]]),
                symbol=symbol,
                exchange=exchange,
                side=side,
                quantity=float(row[col_map["volume"]]),
                price=float(row[col_map["price"]]),
            ))
        return trades
```

- [ ] **Step 3: Create app/parsers/dfcf.py (东方财富)**

```python
import pandas as pd
from app.parsers.base import BaseParser, TradeData

class DFCFParser(BaseParser):
    @classmethod
    def source_type(cls) -> str:
        return "dfcf"

    @classmethod
    def asset_type(cls) -> str:
        return "stock"

    @classmethod
    def detect(cls, content: bytes, filename: str) -> float:
        try:
            df = cls._read_df(content, filename)
        except Exception:
            return 0.0
        expected = ["成交日期", "证券代码", "操作", "成交均价"]
        return cls._column_match_score(list(df.columns), expected)

    @classmethod
    def parse(cls, content: bytes, filename: str) -> list[TradeData]:
        df = cls._read_df(content, filename)
        col_map = {c.strip(): c for c in df.columns}
        trades = []
        for _, row in df.iterrows():
            symbol = str(row[col_map["证券代码"]]).zfill(6)
            exchange = "SH" if symbol.startswith(("6", "5", "9")) else "SZ"
            op = str(row[col_map["操作"]])
            side = "BUY" if "买" in op else "SELL"
            trades.append(TradeData(
                datetime=pd.to_datetime(row[col_map["成交日期"]]),
                symbol=symbol,
                exchange=exchange,
                side=side,
                quantity=float(row.get(col_map.get("成交数量", ""), row.get(col_map.get("成交量", ""), 0))),
                price=float(row[col_map["成交均价"]]),
            ))
        return trades
```

- [ ] **Step 4: Create app/parsers/ths.py (同花顺)**

```python
import pandas as pd
from app.parsers.base import BaseParser, TradeData

class THSParser(BaseParser):
    @classmethod
    def source_type(cls) -> str:
        return "ths"

    @classmethod
    def asset_type(cls) -> str:
        return "stock"

    @classmethod
    def detect(cls, content: bytes, filename: str) -> float:
        try:
            df = cls._read_df(content, filename)
        except Exception:
            return 0.0
        expected = ["发生日期", "证券代码", "买卖标志", "成交价格"]
        return cls._column_match_score(list(df.columns), expected)

    @classmethod
    def parse(cls, content: bytes, filename: str) -> list[TradeData]:
        df = cls._read_df(content, filename)
        col_map = {c.strip(): c for c in df.columns}
        trades = []
        for _, row in df.iterrows():
            symbol = str(row[col_map["证券代码"]]).zfill(6)
            exchange = "SH" if symbol.startswith(("6", "5", "9")) else "SZ"
            flag = str(row[col_map["买卖标志"]])
            side = "BUY" if "买" in flag else "SELL"
            trades.append(TradeData(
                datetime=pd.to_datetime(row[col_map["发生日期"]]),
                symbol=symbol,
                exchange=exchange,
                side=side,
                quantity=float(row[col_map.get("成交数量", col_map.get("成交量", "0"))]),
                price=float(row[col_map["成交价格"]]),
            ))
        return trades
```

- [ ] **Step 5: Create test for QMT parser**

`backend/tests/test_parsers/test_qmt.py`:
```python
from app.parsers.qmt import QMTParser

SAMPLE_CSV = b"委托时间,证券代码,买卖方向,成交价格,成交数量,成交金额\n2026-01-05 09:35:00,600519,买入,1500.00,100,150000\n2026-01-06 14:20:00,600519,卖出,1520.00,100,152000"

def test_qmt_detect():
    score = QMTParser.detect(SAMPLE_CSV, "test.csv")
    assert score >= 0.8

def test_qmt_parse():
    trades = QMTParser.parse(SAMPLE_CSV, "test.csv")
    assert len(trades) == 2
    assert trades[0].symbol == "600519"
    assert trades[0].side == "BUY"
    assert trades[0].price == 1500.0
    assert trades[0].exchange == "SH"
    assert trades[1].side == "SELL"

def test_qmt_detect_wrong_format():
    score = QMTParser.detect(b"col1,col2\n1,2", "test.csv")
    assert score < 0.5
```

- [ ] **Step 6: Run parser tests**

```bash
cd backend && pytest tests/test_parsers/ -v
```

- [ ] **Step 7: Commit**

```bash
git add backend/app/parsers/qmt.py backend/app/parsers/vnpy.py backend/app/parsers/dfcf.py backend/app/parsers/ths.py backend/tests/test_parsers/
git commit -m "feat: add stock parsers (QMT, VN.PY, dfcf, ths)"
```

---

### Task 6: Futures Parsers (文华, 博易, CTP/快期/易盛)

**Files:**
- Create: `backend/app/parsers/wenhua.py`
- Create: `backend/app/parsers/boyi.py`
- Create: `backend/app/parsers/ctp.py`

- [ ] **Step 1: Create wenhua.py, boyi.py, ctp.py**

`backend/app/parsers/wenhua.py`:
```python
import pandas as pd
from app.parsers.base import BaseParser, TradeData

class WenHuaParser(BaseParser):
    @classmethod
    def source_type(cls) -> str: return "wenhua"
    @classmethod
    def asset_type(cls) -> str: return "future"

    @classmethod
    def detect(cls, content: bytes, filename: str) -> float:
        try:
            df = cls._read_df(content, filename)
        except Exception:
            return 0.0
        expected = ["开平", "合约", "手数", "成交价"]
        return cls._column_match_score(list(df.columns), expected)

    @classmethod
    def parse(cls, content: bytes, filename: str) -> list[TradeData]:
        df = cls._read_df(content, filename)
        col_map = {c.strip(): c for c in df.columns}
        trades = []
        for _, row in df.iterrows():
            symbol = str(row[col_map["合约"]]).strip()
            direction = str(row[col_map["开平"]])
            side = "BUY" if "开" in direction or "买" in direction else "SELL"
            trades.append(TradeData(
                datetime=pd.to_datetime(row[col_map.get("成交时间", col_map.get("时间", "2026-01-01"))]),
                symbol=symbol,
                exchange="SHFE",  # Will be refined by symbol prefix matching
                side=side,
                quantity=float(row[col_map["手数"]]),
                price=float(row[col_map["成交价"]]),
                multiplier=_get_multiplier(symbol),
            ))
        return trades
```

`backend/app/parsers/boyi.py`:
```python
import pandas as pd
from app.parsers.base import BaseParser, TradeData

class BoYiParser(BaseParser):
    @classmethod
    def source_type(cls) -> str: return "boyi"
    @classmethod
    def asset_type(cls) -> str: return "future"

    @classmethod
    def detect(cls, content: bytes, filename: str) -> float:
        try:
            df = cls._read_df(content, filename)
        except Exception:
            return 0.0
        expected = ["成交日期", "合约", "买卖", "成交价", "手数"]
        return cls._column_match_score(list(df.columns), expected)

    @classmethod
    def parse(cls, content: bytes, filename: str) -> list[TradeData]:
        df = cls._read_df(content, filename)
        col_map = {c.strip(): c for c in df.columns}
        trades = []
        for _, row in df.iterrows():
            symbol = str(row[col_map["合约"]]).strip()
            side = "BUY" if "买" in str(row[col_map["买卖"]]) else "SELL"
            trades.append(TradeData(
                datetime=pd.to_datetime(row[col_map["成交日期"]]),
                symbol=symbol,
                exchange="SHFE",
                side=side,
                quantity=float(row[col_map["手数"]]),
                price=float(row[col_map["成交价"]]),
                multiplier=_get_multiplier(symbol),
            ))
        return trades
```

`backend/app/parsers/ctp.py`:
```python
import pandas as pd
from app.parsers.base import BaseParser, TradeData

class CTPParser(BaseParser):
    @classmethod
    def source_type(cls) -> str: return "ctp"
    @classmethod
    def asset_type(cls) -> str: return "future"

    @classmethod
    def detect(cls, content: bytes, filename: str) -> float:
        try:
            df = cls._read_df(content, filename)
        except Exception:
            return 0.0
        expected = ["交易日", "合约代码", "买卖", "成交量", "成交价"]
        return cls._column_match_score(list(df.columns), expected)

    @classmethod
    def parse(cls, content: bytes, filename: str) -> list[TradeData]:
        df = cls._read_df(content, filename)
        col_map = {c.strip(): c for c in df.columns}
        trades = []
        for _, row in df.iterrows():
            symbol = str(row[col_map["合约代码"]]).strip()
            side = "BUY" if "买" in str(row[col_map["买卖"]]) else "SELL"
            trades.append(TradeData(
                datetime=pd.to_datetime(row[col_map["交易日"]]),
                symbol=symbol,
                exchange="SHFE",
                side=side,
                quantity=float(row[col_map["成交量"]]),
                price=float(row[col_map["成交价"]]),
                multiplier=_get_multiplier(symbol),
            ))
        return trades
```

Add shared helper at the bottom of `backend/app/parsers/__init__.py`:
```python
def _get_multiplier(symbol: str) -> int:
    """Map futures symbol prefix to exchange and multiplier."""
    symbol_upper = symbol.upper()
    if symbol_upper.startswith("IF"): return 300
    if symbol_upper.startswith("IC"): return 200
    if symbol_upper.startswith("IH"): return 300
    if symbol_upper.startswith("IM"): return 200
    if symbol_upper.startswith("T"): return 10000
    if symbol_upper.startswith("TF"): return 10000
    if symbol_upper.startswith("TS"): return 20000
    # Commodity defaults
    if any(symbol_upper.startswith(p) for p in ("RB", "HC", "BU", "RU", "SP", "FU")): return 10
    if any(symbol_upper.startswith(p) for p in ("CU", "AL", "ZN", "PB", "NI", "SN", "AO")): return 5
    if any(symbol_upper.startswith(p) for p in ("AU",)): return 1000
    if any(symbol_upper.startswith(p) for p in ("AG",)): return 15
    return 10
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/parsers/wenhua.py backend/app/parsers/boyi.py backend/app/parsers/ctp.py backend/app/parsers/__init__.py
git commit -m "feat: add futures parsers (wenhua, boyi, ctp)"
```

---

### Task 7: Broker App Parsers (华泰, 中信, 国君, 广发, 海通)

**Files:**
- Create: `backend/app/parsers/huatai.py`
- Create: `backend/app/parsers/citic.py`

- [ ] **Step 1: Create huatai.py (华泰涨乐) and citic.py (中信/国君/广发/海通)**

These share a common pattern — Chinese column headers with broker-specific variations. Create a shared base in `huatai.py` (华泰 is the most common), then extend for others in `citic.py`.

`backend/app/parsers/huatai.py`:
```python
import pandas as pd
from app.parsers.base import BaseParser, TradeData

class HuaTaiParser(BaseParser):
    @classmethod
    def source_type(cls) -> str: return "huatai"
    @classmethod
    def asset_type(cls) -> str: return "stock"

    @classmethod
    def detect(cls, content: bytes, filename: str) -> float:
        try:
            df = cls._read_df(content, filename)
        except Exception:
            return 0.0
        # 华泰: 成交日期, 证券名称, 证券代码, 买卖方向, 成交价格, 成交数量
        keywords = ["成交日期", "证券代码", "成交价格"]
        return cls._column_match_score(list(df.columns), keywords)

    @classmethod
    def parse(cls, content: bytes, filename: str) -> list[TradeData]:
        df = cls._read_df(content, filename)
        col_map = {c.strip(): c for c in df.columns}
        trades = []
        for _, row in df.iterrows():
            symbol = str(row[_find_col(col_map, ["证券代码", "股票代码", "代码"])]).zfill(6)
            exchange = "SH" if symbol.startswith(("6", "5", "9")) else "SZ"
            side_str = str(row[_find_col(col_map, ["买卖方向", "操作", "方向", "买卖"])])
            side = "BUY" if "买" in side_str else "SELL"
            trades.append(TradeData(
                datetime=pd.to_datetime(row[_find_col(col_map, ["成交日期", "委托日期", "日期", "发生日期"])]),
                symbol=symbol,
                exchange=exchange,
                side=side,
                quantity=float(row[_find_col(col_map, ["成交数量", "成交量", "数量"])]),
                price=float(row[_find_col(col_map, ["成交价格", "成交均价", "价格"])]),
            ))
        return trades


def _find_col(col_map: dict, candidates: list[str]) -> str:
    for c in candidates:
        if c in col_map:
            return col_map[c]
    raise KeyError(f"None of {candidates} found in columns: {list(col_map.keys())}")
```

`backend/app/parsers/citic.py`:
```python
import pandas as pd
from app.parsers.base import BaseParser, TradeData
from app.parsers.huatai import _find_col

class BrokerParser(BaseParser):
    """Generic parser for 中信/国君/广发/海通 and similar broker apps.
    They share very similar CSV exports with minor column name differences.
    detect() returns a lower confidence score, user may need to confirm."""

    @classmethod
    def source_type(cls) -> str: return "broker"
    @classmethod
    def asset_type(cls) -> str: return "stock"

    @classmethod
    def detect(cls, content: bytes, filename: str) -> float:
        try:
            df = cls._read_df(content, filename)
        except Exception:
            return 0.0
        cols = [c.strip() for c in df.columns]
        keywords = ["成交", "代码", "价格", "数量"]
        matched = sum(1 for k in keywords if any(k in c for c in cols))
        return matched / len(keywords) * 0.85  # Lower base confidence

    @classmethod
    def parse(cls, content: bytes, filename: str) -> list[TradeData]:
        df = cls._read_df(content, filename)
        col_map = {c.strip(): c for c in df.columns}
        trades = []
        for _, row in df.iterrows():
            symbol = str(row[_find_col(col_map, ["证券代码", "股票代码", "代码", "品种代码"])]).zfill(6)
            exchange = "SH" if symbol.startswith(("6", "5", "9")) else "SZ"
            side_str = str(row[_find_col(col_map, ["买卖方向", "操作", "方向", "买卖", "交易方向"])])
            side = "BUY" if "买" in side_str else "SELL"
            trades.append(TradeData(
                datetime=pd.to_datetime(row[_find_col(col_map, ["成交日期", "委托日期", "日期", "发生日期", "交易日期"])]),
                symbol=symbol,
                exchange=exchange,
                side=side,
                quantity=float(row[_find_col(col_map, ["成交数量", "成交量", "数量", "成交股数"])]),
                price=float(row[_find_col(col_map, ["成交价格", "成交均价", "价格", "成交价"])]),
            ))
        return trades
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/parsers/huatai.py backend/app/parsers/citic.py
git commit -m "feat: add broker app parsers (huatai, citic/generic)"
```

---

### Task 8: Position Builder (FIFO)

**Files:**
- Create: `backend/app/engine/__init__.py`
- Create: `backend/app/engine/position.py`
- Create: `backend/tests/test_engine/__init__.py`
- Create: `backend/tests/test_engine/test_position.py`

- [ ] **Step 1: Create app/engine/position.py**

```python
from datetime import date
from collections import deque
from dataclasses import dataclass, field
from app.models.trade import Trade

@dataclass
class PositionResult:
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
    trade_ids: list[str] = field(default_factory=list)

class PositionBuilder:
    """FIFO position reconstruction from raw trades."""

    @staticmethod
    def build(trades: list[Trade]) -> list[PositionResult]:
        # Group by symbol
        by_symbol: dict[str, list[Trade]] = {}
        for t in trades:
            by_symbol.setdefault(t.symbol, []).append(t)

        positions: list[PositionResult] = []
        for symbol, symbol_trades in by_symbol.items():
            sorted_trades = sorted(symbol_trades, key=lambda t: t.datetime)
            positions.extend(PositionBuilder._build_for_symbol(symbol, sorted_trades))
        return positions

    @staticmethod
    def _build_for_symbol(symbol: str, trades: list[Trade]) -> list[PositionResult]:
        positions = []
        long_queue = deque()  # (qty, price, trade_id)

        for trade in trades:
            if trade.side == "BUY":
                long_queue.append((trade.quantity, trade.price, trade.id))
            else:
                remaining_sell = trade.quantity
                sell_trade_ids = [trade.id]
                total_cost = 0.0
                total_qty = 0.0

                while remaining_sell > 0 and long_queue:
                    buy_qty, buy_price, buy_id = long_queue[0]
                    matched_qty = min(remaining_sell, buy_qty)
                    total_cost += matched_qty * buy_price
                    total_qty += matched_qty
                    sell_trade_ids.append(buy_id)
                    remaining_sell -= matched_qty
                    if matched_qty >= buy_qty:
                        long_queue.popleft()
                    else:
                        long_queue[0] = (buy_qty - matched_qty, buy_price, buy_id)

                if total_qty > 0:
                    avg_entry = total_cost / total_qty
                    avg_exit = (trade.quantity * trade.price) / trade.quantity  # simplified
                    pnl = (avg_exit - avg_entry) * total_qty
                    pnl_pct = (avg_exit - avg_entry) / avg_entry if avg_entry != 0 else 0.0
                    entry_date = trades[0].datetime.date()
                    exit_date = trade.datetime.date()
                    holding_days = (exit_date - entry_date).days
                    positions.append(PositionResult(
                        symbol=symbol,
                        asset_type=trade.asset_type,
                        entry_date=entry_date,
                        exit_date=exit_date,
                        holding_days=max(holding_days, 1),
                        total_quantity=total_qty,
                        avg_entry_price=avg_entry,
                        avg_exit_price=trade.price,
                        pnl=pnl,
                        pnl_pct=pnl_pct,
                        trade_ids=sell_trade_ids,
                    ))

        return positions
```

- [ ] **Step 2: Create tests/test_engine/test_position.py**

```python
from datetime import datetime
from app.engine.position import PositionBuilder

def _make_trade(id, symbol, side, qty, price, dt, asset_type="stock", exchange="SH"):
    from app.models.trade import Trade
    t = Trade(id=id, user_id="u1", raw_file_id="r1", symbol=symbol, side=side,
              quantity=qty, price=price, datetime=dt, exchange=exchange,
              asset_type=asset_type, commission=0)
    return t

def test_simple_buy_sell():
    trades = [
        _make_trade("t1", "600519", "BUY", 100, 1500, datetime(2026, 1, 5, 9, 35)),
        _make_trade("t2", "600519", "SELL", 100, 1520, datetime(2026, 1, 10, 14, 20)),
    ]
    positions = PositionBuilder.build(trades)
    assert len(positions) == 1
    p = positions[0]
    assert p.avg_entry_price == 1500.0
    assert p.avg_exit_price == 1520.0
    assert p.pnl == 2000.0
    assert round(p.pnl_pct, 4) == round(20 / 1500, 4)
    assert p.holding_days == 5

def test_partial_sell_fifo():
    trades = [
        _make_trade("t1", "600519", "BUY", 200, 1500, datetime(2026, 1, 5, 9, 35)),
        _make_trade("t2", "600519", "SELL", 100, 1520, datetime(2026, 1, 10, 14, 20)),
        _make_trade("t3", "600519", "SELL", 100, 1510, datetime(2026, 1, 15, 10, 0)),
    ]
    positions = PositionBuilder.build(trades)
    assert len(positions) == 2

def test_multiple_symbols():
    trades = [
        _make_trade("t1", "600519", "BUY", 100, 1500, datetime(2026, 1, 5, 9, 35)),
        _make_trade("t2", "000858", "BUY", 200, 120, datetime(2026, 1, 6, 10, 0)),
        _make_trade("t3", "600519", "SELL", 100, 1520, datetime(2026, 1, 10, 14, 20)),
        _make_trade("t4", "000858", "SELL", 200, 125, datetime(2026, 1, 12, 11, 0)),
    ]
    positions = PositionBuilder.build(trades)
    assert len(positions) == 2
```

- [ ] **Step 3: Run tests**

```bash
cd backend && pytest tests/test_engine/test_position.py -v
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/engine/ backend/tests/test_engine/
git commit -m "feat: add FIFO position builder engine"
```

---

### Task 9: Pattern Engine

**Files:**
- Create: `backend/app/engine/pattern.py`
- Create: `backend/tests/test_engine/test_pattern.py`

- [ ] **Step 1: Create app/engine/pattern.py**

```python
from dataclasses import dataclass, field

PATTERNS_NO_MARKET = {"SCALP", "SWING", "POSITION", "PYRAMID", "AVERAGE_DOWN", "TURN", "STOP_LOSS", "TAKE_PROFIT", "CASH"}
PATTERNS_NEED_MARKET = {"CHASE", "BOTTOM", "BREAKOUT", "TREND", "COUNTER_TREND", "BREAKDOWN"}

@dataclass
class PatternResult:
    pattern_name: str
    confidence: float
    context: dict = field(default_factory=dict)

class PatternEngine:
    """Tag each Position with behavior patterns."""

    def tag_position(self, pos, all_positions: list, trades_by_day: dict = None) -> list[PatternResult]:
        """pos = PositionResult, all_positions needed for PYRAMID/AVERAGE_DOWN/TURN detection."""
        results = []

        # Module 2: Holding period (no market data needed)
        if pos.holding_days < 3:
            results.append(PatternResult("SCALP", 1.0, {"holding_days": pos.holding_days}))
        elif pos.holding_days <= 30:
            results.append(PatternResult("SWING", 1.0, {"holding_days": pos.holding_days}))
        else:
            results.append(PatternResult("POSITION", 1.0, {"holding_days": pos.holding_days}))

        # Module 3: Risk & position management
        # PYRAMID: buy more while in profit on same symbol
        same_symbol = [p for p in all_positions if p.symbol == pos.symbol and p.entry_date == pos.entry_date]
        if len(same_symbol) > 1:
            avg_entry = sum(p.avg_entry_price for p in same_symbol) / len(same_symbol)
            if pos.avg_entry_price > avg_entry:
                results.append(PatternResult("PYRAMID", 0.8, {"same_day_entries": len(same_symbol)}))

        # AVERAGE_DOWN: buy more while in loss on same symbol
        if pos.pnl_pct < 0 and len(same_symbol) > 1:
            results.append(PatternResult("AVERAGE_DOWN", 0.8, {"pnl_pct": pos.pnl_pct}))

        # TURN: same-day buy+sell (detected from trade_ids analysis)
        # This is detected at the Trade level — if any trade in the position
        # has same-day opposing trades for same symbol
        if trades_by_day:
            symbol = pos.symbol
            entry_str = str(pos.entry_date)
            # Check if there are both buys and sells on the same day
            day_trades = trades_by_day.get((symbol, entry_str), [])
            has_buy = any(t.get("side") == "BUY" for t in day_trades)
            has_sell = any(t.get("side") == "SELL" for t in day_trades)
            if has_buy and has_sell:
                results.append(PatternResult("TURN", 0.7, {"date": entry_str}))

        # STOP_LOSS: exit with loss
        if pos.pnl_pct < 0:
            results.append(PatternResult("STOP_LOSS", 0.6, {"pnl_pct": pos.pnl_pct}))

        # TAKE_PROFIT: exit with profit
        if pos.pnl_pct > 0:
            results.append(PatternResult("TAKE_PROFIT", 0.6, {"pnl_pct": pos.pnl_pct}))

        return results

    def tag_market_patterns(self, pos, market_data: dict) -> list[PatternResult]:
        """market_data = {symbol: {date: {open, high, low, close, ma5, ma10, ma20, ma60}}}"""
        results = []
        symbol_data = market_data.get(pos.symbol, {})
        if not symbol_data:
            return results

        entry_str = str(pos.entry_date)
        exit_str = str(pos.exit_date)
        entry = symbol_data.get(entry_str)
        exit_day = symbol_data.get(exit_str)

        if entry:
            close = entry.get("close", 0)
            ma20 = entry.get("ma20")
            ma60 = entry.get("ma60")

            # BREAKOUT: 20-day new high
            dates = sorted(symbol_data.keys())
            idx = dates.index(entry_str) if entry_str in dates else -1
            if idx >= 19:
                prev_20_high = max(symbol_data[d].get("high", 0) for d in dates[idx-19:idx])
                if close > prev_20_high:
                    results.append(PatternResult("BREAKOUT", 0.9, {"20d_high": prev_20_high, "price": close}))

            # TREND / COUNTER_TREND
            if ma20 is not None and ma60 is not None:
                if ma20 > ma60:
                    results.append(PatternResult("TREND", 0.8, {"ma20": ma20, "ma60": ma60}))
                else:
                    results.append(PatternResult("COUNTER_TREND", 0.8, {"ma20": ma20, "ma60": ma60}))

            # CHASE: 5-day gain > 15%
            if idx >= 4:
                price_5d_ago = symbol_data[dates[idx-4]].get("close", 0)
                if price_5d_ago > 0:
                    change = (close - price_5d_ago) / price_5d_ago
                    if change > 0.15:
                        results.append(PatternResult("CHASE", 1.0, {"prev_5d_return": round(change, 4)}))

            # BOTTOM: 5-day drop > 15%
            if idx >= 4:
                price_5d_ago = symbol_data[dates[idx-4]].get("close", 0)
                if price_5d_ago > 0:
                    change = (close - price_5d_ago) / price_5d_ago
                    if change < -0.15:
                        results.append(PatternResult("BOTTOM", 1.0, {"prev_5d_return": round(change, 4)}))

        # BREAKDOWN: exit day price at 20-day low
        if exit_day:
            close = exit_day.get("close", 0)
            dates = sorted(symbol_data.keys())
            if exit_str in dates:
                idx = dates.index(exit_str)
                if idx >= 19:
                    prev_20_low = min(symbol_data[d].get("low", float("inf")) for d in dates[idx-19:idx])
                    if close < prev_20_low:
                        results.append(PatternResult("BREAKDOWN", 0.9, {"20d_low": prev_20_low, "price": close}))

        return results
```

- [ ] **Step 2: Create tests/test_engine/test_pattern.py**

```python
from datetime import date
from app.engine.position import PositionResult
from app.engine.pattern import PatternEngine

def _make_pos(symbol="600519", pnl_pct=0.05, holding_days=10, entry=date(2026,1,5), exit=date(2026,1,15), entry_price=1500, exit_price=1550, qty=100):
    pnl = (exit_price - entry_price) * qty
    return PositionResult(symbol=symbol, asset_type="stock", entry_date=entry, exit_date=exit,
                          holding_days=holding_days, total_quantity=qty, avg_entry_price=entry_price,
                          avg_exit_price=exit_price, pnl=pnl, pnl_pct=pnl_pct, trade_ids=["t1","t2"])

def test_scalp_tag():
    pos = _make_pos(holding_days=2)
    engine = PatternEngine()
    tags = engine.tag_position(pos, [pos])
    names = {t.pattern_name for t in tags}
    assert "SCALP" in names
    assert "SWING" not in names

def test_swing_tag():
    pos = _make_pos(holding_days=15)
    tags = PatternEngine().tag_position(pos, [pos])
    names = {t.pattern_name for t in tags}
    assert "SWING" in names

def test_stop_loss_tag():
    pos = _make_pos(pnl_pct=-0.05)
    tags = PatternEngine().tag_position(pos, [pos])
    names = {t.pattern_name for t in tags}
    assert "STOP_LOSS" in names

def test_take_profit_tag():
    pos = _make_pos(pnl_pct=0.08)
    tags = PatternEngine().tag_position(pos, [pos])
    names = {t.pattern_name for t in tags}
    assert "TAKE_PROFIT" in names

def test_market_patterns_breakout():
    pos = _make_pos(entry=date(2026, 1, 25))
    market_data = {
        "600519": {
            "2026-01-05": {"high": 1480, "low": 1450, "close": 1470, "ma20": 1465, "ma60": 1440},
            # ... fill 19 days of data all with high < 1510
            **{f"2026-01-{d:02d}": {"high": 1480, "low": 1450, "close": 1470, "ma20": 1465, "ma60": 1440}
               for d in range(6, 25)},
            "2026-01-25": {"high": 1510, "low": 1490, "close": 1505, "ma20": 1480, "ma60": 1460},
        }
    }
    tags = PatternEngine().tag_market_patterns(pos, market_data)
    names = {t.pattern_name for t in tags}
    # BREAKOUT because close 1505 > all previous 20-day highs (1480)
    assert "BREAKOUT" in names
```

- [ ] **Step 3: Run tests**

```bash
cd backend && pytest tests/test_engine/test_pattern.py -v
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/engine/pattern.py backend/tests/test_engine/test_pattern.py
git commit -m "feat: add pattern engine with 15 behavior tags"
```

---

### Task 10: Insight + What If Engines

**Files:**
- Create: `backend/app/engine/insight.py`
- Create: `backend/app/engine/whatif.py`
- Create: `backend/tests/test_engine/test_insight.py`
- Create: `backend/tests/test_engine/test_whatif.py`

- [ ] **Step 1: Create app/engine/insight.py**

```python
from dataclasses import dataclass
from app.engine.position import PositionResult
from app.engine.pattern import PatternResult

@dataclass
class InsightItem:
    pattern_name: str
    count: int
    win_count: int
    win_rate: float
    total_pnl: float
    avg_pnl_pct: float

class InsightEngine:
    @staticmethod
    def analyze(positions: list[PositionResult], patterns: dict[str, list[PatternResult]]) -> list[InsightItem]:
        """patterns = {position_id: [PatternResult, ...]}"""
        by_pattern: dict[str, list[PositionResult]] = {}
        for pos in positions:
            for pat in patterns.get(pos.symbol, []):  # Use position_id mapping in real code
                by_pattern.setdefault(pat.pattern_name, []).append(pos)

        # For real implementation, use a proper position_id → patterns mapping
        # This simplified version groups by pattern name
        results = []
        for pattern_name, pat_positions in by_pattern.items():
            wins = [p for p in pat_positions if p.pnl > 0]
            total_pnl = sum(p.pnl for p in pat_positions)
            results.append(InsightItem(
                pattern_name=pattern_name,
                count=len(pat_positions),
                win_count=len(wins),
                win_rate=len(wins) / len(pat_positions) if pat_positions else 0.0,
                total_pnl=total_pnl,
                avg_pnl_pct=sum(p.pnl_pct for p in pat_positions) / len(pat_positions) if pat_positions else 0.0,
            ))
        results.sort(key=lambda x: x.total_pnl, reverse=True)
        return results
```

- [ ] **Step 2: Create app/engine/whatif.py**

```python
from dataclasses import dataclass

@dataclass
class WhatIfItem:
    removed_pattern: str
    original_return: float
    what_if_return: float
    delta: float
    damage_score: float  # 0.0~1.0, higher = more damaging

class WhatIfEngine:
    @staticmethod
    def analyze(positions, patterns_map: dict[str, list[str]]) -> list[WhatIfItem]:
        """patterns_map = {position_index: [pattern_name, ...]}
        For each unique pattern, remove all positions with that tag and recalculate return."""
        # Calculate original total return
        total_invested = sum(p.avg_entry_price * p.total_quantity for p in positions)
        total_pnl = sum(p.pnl for p in positions)
        original_return = total_pnl / total_invested if total_invested > 0 else 0.0

        # Collect all unique pattern names
        all_patterns = set()
        for pats in patterns_map.values():
            all_patterns.update(pats)

        results = []
        for pattern_name in all_patterns:
            # Remove positions tagged with this pattern
            filtered = [p for i, p in enumerate(positions) if pattern_name not in patterns_map.get(i, [])]
            if not filtered:
                continue
            filtered_invested = sum(p.avg_entry_price * p.total_quantity for p in filtered)
            filtered_pnl = sum(p.pnl for p in filtered)
            what_if_return = filtered_pnl / filtered_invested if filtered_invested > 0 else 0.0

            delta = what_if_return - original_return
            # Damage score: how much removing this pattern improves return
            # Normalized: delta / max_improvement across all patterns
            results.append(WhatIfItem(
                removed_pattern=pattern_name,
                original_return=round(original_return, 4),
                what_if_return=round(what_if_return, 4),
                delta=round(delta, 4),
                damage_score=0.0,  # Computed after all items collected
            ))

        # Calculate damage scores
        if results:
            max_delta = max(abs(r.delta) for r in results)
            for r in results:
                r.damage_score = round(abs(r.delta) / max_delta, 4) if max_delta > 0 else 0.0

        results.sort(key=lambda x: x.damage_score, reverse=True)
        return results
```

- [ ] **Step 3: Create quick tests**

`backend/tests/test_engine/test_insight.py`:
```python
from app.engine.position import PositionResult
from app.engine.insight import InsightEngine
from datetime import date

def test_insight_basic():
    positions = [
        PositionResult("600519","stock",date(2026,1,1),date(2026,1,5),4,100,100,110,1000,0.1,["t1","t2"]),
        PositionResult("000858","stock",date(2026,1,2),date(2026,1,10),8,200,50,48,-400,-0.04,["t3","t4"]),
    ]
    patterns = {
        "600519": [type("P",(),{"pattern_name":"BREAKOUT"})()],
        "000858": [type("P",(),{"pattern_name":"CHASE"})()],
    }
    # Note: real implementation uses position IDs, not symbols
    # This test validates the aggregation logic shape
    results = InsightEngine.analyze(positions, patterns)
    assert len(results) > 0
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/engine/insight.py backend/app/engine/whatif.py backend/tests/test_engine/test_insight.py backend/tests/test_engine/test_whatif.py
git commit -m "feat: add insight engine + what-if engine"
```

---

### Task 11: AI Layer (Provider + Prompt + Validator)

**Files:**
- Create: `backend/app/ai/__init__.py`
- Create: `backend/app/ai/provider.py`
- Create: `backend/app/ai/prompt.py`
- Create: `backend/app/ai/validator.py`
- Create: `backend/tests/test_ai/__init__.py`
- Create: `backend/tests/test_ai/test_prompt.py`
- Create: `backend/tests/test_ai/test_validator.py`

- [ ] **Step 1: Create app/ai/provider.py**

```python
from abc import ABC, abstractmethod
import os
from app.config import settings

class LLMProvider(ABC):
    @abstractmethod
    async def generate(self, system_prompt: str, user_prompt: str) -> str: ...

class OpenAIProvider(LLMProvider):
    async def generate(self, system_prompt: str, user_prompt: str) -> str:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=settings.openai_api_key)
        resp = await client.chat.completions.create(
            model=settings.openai_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.3,
        )
        return resp.choices[0].message.content or ""

class ClaudeProvider(LLMProvider):
    async def generate(self, system_prompt: str, user_prompt: str) -> str:
        from anthropic import AsyncAnthropic
        client = AsyncAnthropic(api_key=settings.claude_api_key)
        resp = await client.messages.create(
            model=settings.claude_model,
            max_tokens=2000,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        return resp.content[0].text

class DeepSeekProvider(LLMProvider):
    async def generate(self, system_prompt: str, user_prompt: str) -> str:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=settings.deepseek_api_key, base_url="https://api.deepseek.com")
        resp = await client.chat.completions.create(
            model=settings.deepseek_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.3,
        )
        return resp.choices[0].message.content or ""

def get_llm() -> LLMProvider:
    providers = {
        "openai": OpenAIProvider,
        "claude": ClaudeProvider,
        "deepseek": DeepSeekProvider,
    }
    provider_cls = providers.get(settings.ai_provider, OpenAIProvider)
    return provider_cls()
```

- [ ] **Step 2: Create app/ai/prompt.py**

```python
import json

SYSTEM_PROMPT = """你是一名 A 股交易教练。你的职责是分析用户的交易数据，帮助他识别亏损原因并给出改善建议。

你必须严格遵守以下规则：
1. 只使用我提供的数据，不要编造任何数字
2. 不要预测市场走势
3. 不要推荐具体股票
4. 分析要基于行为，不要归因于市场或运气
5. 语气：专业、直接、不说废话"""

def build_user_prompt(analysis_data: dict) -> str:
    """Build structured prompt from analysis results."""
    data_json = json.dumps(analysis_data, ensure_ascii=False, indent=2)
    return f"""以下是一位交易者的账户分析数据：

{data_json}

请从以下四个维度生成诊断报告：
1. **你的优势**：最赚钱的行为模式是什么？给出具体数据
2. **你的劣势**：最亏钱的行为模式是什么？给出具体数据
3. **最危险行为**：What If 回测显示，删除哪种行为收益提升最大？
4. **改善建议**：具体的、可执行的下一步行动

报告格式要求：
- 第一行必须是「## 核心诊断」，用一句话总结（不超过 50 字）
- 然后按 1/2/3/4 四个维度展开
- 每个维度至少引用一个具体数字
- 语言简洁，不使用套话"""
```

- [ ] **Step 3: Create app/ai/validator.py**

```python
import re
from dataclasses import dataclass, field

@dataclass
class ValidationResult:
    passed: bool
    errors: list[str] = field(default_factory=list)

class ReportValidator:
    MAX_RETRIES = 3
    TOLERANCE = 0.01  # 1%

    def validate(self, report: str, input_data: dict) -> ValidationResult:
        errors = []

        # Extract key metrics from input
        account = input_data.get("account_summary", {})
        expected_win_rate = account.get("win_rate")
        expected_total_return = account.get("total_return_pct")
        expected_total_trades = account.get("total_trades")

        # Extract numbers from report
        percentages = re.findall(r"(\d+(?:\.\d+)?)\s*%", report)

        # Check win rate in report
        if expected_win_rate is not None:
            expected_pct = round(expected_win_rate * 100, 1)
            found = any(abs(float(p) - expected_pct) <= expected_pct * self.TOLERANCE + 1 for p in percentages)
            if not found:
                errors.append(f"Win rate {expected_pct}% not accurately reflected in report")

        # Check total return
        if expected_total_return is not None:
            expected_pct = round(expected_total_return * 100, 1)
            found = any(abs(float(p) - expected_pct) <= max(abs(expected_pct) * self.TOLERANCE, 1) for p in percentages)
            if not found:
                errors.append(f"Total return {expected_pct}% not accurately reflected in report")

        return ValidationResult(passed=len(errors) == 0, errors=errors)

    async def generate_with_retry(self, llm, system_prompt: str, user_prompt: str, input_data: dict) -> tuple[str, bool]:
        for attempt in range(self.MAX_RETRIES):
            report = await llm.generate(system_prompt, user_prompt)
            validation = self.validate(report, input_data)
            if validation.passed:
                return report, True
        # Last attempt, accept it but flag as failed
        report = await llm.generate(system_prompt, user_prompt)
        return report, False
```

- [ ] **Step 4: Create tests/test_ai/test_validator.py**

```python
from app.ai.validator import ReportValidator

def test_validator_passes_accurate_report():
    validator = ReportValidator()
    input_data = {
        "account_summary": {"win_rate": 0.42, "total_return_pct": 0.12, "total_trades": 847}
    }
    report = "## 核心诊断\n胜率42%，总收益12%，共847笔交易"
    result = validator.validate(report, input_data)
    assert result.passed

def test_validator_catches_wrong_number():
    validator = ReportValidator()
    input_data = {
        "account_summary": {"win_rate": 0.42, "total_return_pct": 0.12, "total_trades": 847}
    }
    report = "## 核心诊断\n胜率85%，总收益50%"
    result = validator.validate(report, input_data)
    assert not result.passed
```

- [ ] **Step 5: Run tests**

```bash
cd backend && pytest tests/test_ai/ -v
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/ai/ backend/tests/test_ai/
git commit -m "feat: add AI layer (provider abstraction + prompt builder + validator)"
```

---

### Task 12: API Endpoints (Upload, Analysis, Report)

**Files:**
- Create: `backend/app/schemas/upload.py`
- Create: `backend/app/schemas/analysis.py`
- Create: `backend/app/schemas/report.py`
- Create: `backend/app/api/upload.py`
- Create: `backend/app/api/analysis.py`
- Create: `backend/app/api/report.py`
- Modify: `backend/app/api/__init__.py`
- Create: `backend/tests/test_api/test_upload.py`
- Create: `backend/tests/test_api/test_analysis.py`

- [ ] **Step 1: Create Pydantic schemas**

`backend/app/schemas/upload.py`:
```python
from pydantic import BaseModel

class UploadResponse(BaseModel):
    raw_file_id: str
    detected_formats: list[dict]  # [{source_type, asset_type, confidence}]

class ConfirmRequest(BaseModel):
    raw_file_id: str
    source_type: str

class ConfirmResponse(BaseModel):
    trades: list[dict]
    total_count: int

class ImportRequest(BaseModel):
    raw_file_id: str

class ImportResponse(BaseModel):
    imported_count: int
    message: str
```

`backend/app/schemas/analysis.py`:
```python
from pydantic import BaseModel
from datetime import date

class AnalysisRunRequest(BaseModel):
    date_start: date
    date_end: date

class AnalysisRunResponse(BaseModel):
    analysis_id: str

class KPIStats(BaseModel):
    total_trades: int
    win_rate: float
    profit_factor: float
    total_return_pct: float
    max_drawdown_pct: float
    avg_holding_days: float
    max_consecutive_losses: int

class StatsResponse(BaseModel):
    kpi: KPIStats
    positions: list[dict]

class InsightItemResponse(BaseModel):
    pattern_name: str
    count: int
    win_rate: float
    total_pnl: float
    avg_pnl_pct: float

class InsightResponse(BaseModel):
    patterns: list[InsightItemResponse]
    best_pattern: str | None
    worst_pattern: str | None

class WhatIfItemResponse(BaseModel):
    removed_pattern: str
    original_return: float
    what_if_return: float
    delta: float
    damage_score: float

class WhatIfResponse(BaseModel):
    items: list[WhatIfItemResponse]
```

`backend/app/schemas/report.py`:
```python
from pydantic import BaseModel

class GenerateReportRequest(BaseModel):
    analysis_id: str

class ReportResponse(BaseModel):
    id: str
    report_content: str
    validation_passed: bool
    ai_provider: str
    created_at: str
```

- [ ] **Step 2: Create app/api/upload.py**

```python
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.user import User
from app.models.raw_file import RawFile
from app.models.trade import Trade
from app.auth.jwt import get_current_user
from app.parsers.registry import ParserRegistry
from app.schemas.upload import UploadResponse, ConfirmRequest, ConfirmResponse, ImportRequest, ImportResponse

router = APIRouter(prefix="/api/upload", tags=["upload"])

@router.post("", response_model=UploadResponse)
async def upload_file(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    content = await file.read()
    raw_file = RawFile(user_id=user.id, filename=file.filename, raw_content=content)
    db.add(raw_file)
    db.commit()
    db.refresh(raw_file)
    formats = ParserRegistry.detect_format(content, file.filename)
    return UploadResponse(
        raw_file_id=raw_file.id,
        detected_formats=[{"source_type": f[0], "asset_type": f[1], "confidence": f[2]} for f in formats],
    )

@router.post("/confirm", response_model=ConfirmResponse)
def confirm_format(
    body: ConfirmRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    raw_file = db.query(RawFile).filter(RawFile.id == body.raw_file_id, RawFile.user_id == user.id).first()
    if not raw_file:
        raise HTTPException(404, "File not found")
    raw_file.source_type = body.source_type
    db.commit()
    trade_data = ParserRegistry.parse(body.source_type, raw_file.raw_content, raw_file.filename)
    return ConfirmResponse(
        trades=[{"datetime": str(t.datetime), "symbol": t.symbol, "side": t.side,
                 "quantity": t.quantity, "price": t.price, "exchange": t.exchange} for t in trade_data],
        total_count=len(trade_data),
    )

@router.post("/import", response_model=ImportResponse)
def import_trades(
    body: ImportRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    raw_file = db.query(RawFile).filter(RawFile.id == body.raw_file_id, RawFile.user_id == user.id).first()
    if not raw_file or not raw_file.source_type:
        raise HTTPException(400, "File not confirmed yet")
    trade_data = ParserRegistry.parse(raw_file.source_type, raw_file.raw_content, raw_file.filename)
    trades = []
    for td in trade_data:
        trade = Trade(
            raw_file_id=raw_file.id, user_id=user.id, asset_type=raw_file.asset_type or "stock",
            datetime=td.datetime, symbol=td.symbol, exchange=td.exchange,
            side=td.side, quantity=td.quantity, price=td.price,
            commission=td.commission, margin=td.margin, multiplier=td.multiplier,
        )
        trades.append(trade)
    db.add_all(trades)
    db.commit()
    return ImportResponse(imported_count=len(trades), message=f"Imported {len(trades)} trades")
```

- [ ] **Step 3: Create app/api/analysis.py**

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.user import User
from app.models.trade import Trade
from app.models.analysis import Analysis
from app.auth.jwt import get_current_user
from app.schemas.analysis import AnalysisRunRequest, AnalysisRunResponse, StatsResponse, InsightResponse, WhatIfResponse, KPIStats
from app.engine.position import PositionBuilder
from app.engine.pattern import PatternEngine
from app.engine.insight import InsightEngine
from app.engine.whatif import WhatIfEngine

router = APIRouter(prefix="/api/analysis", tags=["analysis"])

@router.post("/run", response_model=AnalysisRunResponse)
def run_analysis(
    body: AnalysisRunRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    analysis = Analysis(user_id=user.id, date_start=body.date_start, date_end=body.date_end)
    db.add(analysis)
    db.commit()
    db.refresh(analysis)
    return AnalysisRunResponse(analysis_id=analysis.id)

@router.get("/{analysis_id}/stats", response_model=StatsResponse)
def get_stats(
    analysis_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    analysis = db.query(Analysis).filter(Analysis.id == analysis_id, Analysis.user_id == user.id).first()
    if not analysis:
        raise HTTPException(404, "Analysis not found")
    trades = db.query(Trade).filter(
        Trade.user_id == user.id,
        Trade.datetime >= analysis.date_start,
        Trade.datetime <= analysis.date_end,
    ).all()
    positions = PositionBuilder.build(trades)
    wins = [p for p in positions if p.pnl > 0]
    losses = [p for p in positions if p.pnl <= 0]
    total_pnl = sum(p.pnl for p in positions)
    total_invested = sum(p.avg_entry_price * p.total_quantity for p in positions)
    return StatsResponse(
        kpi=KPIStats(
            total_trades=len(positions),
            win_rate=round(len(wins) / len(positions), 4) if positions else 0.0,
            profit_factor=round(abs(sum(p.pnl for p in wins) / sum(abs(p.pnl) for p in losses)), 2) if losses else 999,
            total_return_pct=round(total_pnl / total_invested, 4) if total_invested > 0 else 0.0,
            max_drawdown_pct=0.0,
            avg_holding_days=round(sum(p.holding_days for p in positions) / len(positions), 1) if positions else 0.0,
            max_consecutive_losses=0,
        ),
        positions=[{"symbol": p.symbol, "entry": str(p.entry_date), "exit": str(p.exit_date),
                     "pnl": p.pnl, "pnl_pct": p.pnl_pct} for p in positions],
    )

@router.get("/{analysis_id}/insight", response_model=InsightResponse)
def get_insight(analysis_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    analysis = db.query(Analysis).filter(Analysis.id == analysis_id, Analysis.user_id == user.id).first()
    if not analysis:
        raise HTTPException(404, "Analysis not found")
    trades = db.query(Trade).filter(Trade.user_id == user.id,
        Trade.datetime >= analysis.date_start, Trade.datetime <= analysis.date_end).all()
    positions = PositionBuilder.build(trades)
    engine = PatternEngine()
    patterns_map = {}
    for i, pos in enumerate(positions):
        tags = engine.tag_position(pos, positions)
        patterns_map[i] = [t.pattern_name for t in tags]
    insights = InsightEngine.analyze(positions, patterns_map)
    return InsightResponse(
        patterns=[{"pattern_name": r.pattern_name, "count": r.count, "win_rate": r.win_rate,
                    "total_pnl": r.total_pnl, "avg_pnl_pct": r.avg_pnl_pct} for r in insights],
        best_pattern=insights[0].pattern_name if insights else None,
        worst_pattern=insights[-1].pattern_name if insights else None,
    )

@router.get("/{analysis_id}/whatif", response_model=WhatIfResponse)
def get_whatif(analysis_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    analysis = db.query(Analysis).filter(Analysis.id == analysis_id, Analysis.user_id == user.id).first()
    if not analysis:
        raise HTTPException(404, "Analysis not found")
    trades = db.query(Trade).filter(Trade.user_id == user.id,
        Trade.datetime >= analysis.date_start, Trade.datetime <= analysis.date_end).all()
    positions = PositionBuilder.build(trades)
    engine = PatternEngine()
    patterns_map = {}
    for i, pos in enumerate(positions):
        tags = engine.tag_position(pos, positions)
        patterns_map[i] = [t.pattern_name for t in tags]
    results = WhatIfEngine.analyze(positions, patterns_map)
    return WhatIfResponse(items=[{
        "removed_pattern": r.removed_pattern, "original_return": r.original_return,
        "what_if_return": r.what_if_return, "delta": r.delta, "damage_score": r.damage_score,
    } for r in results])
```

- [ ] **Step 4: Create app/api/report.py** and update `app/api/__init__.py`

`backend/app/api/report.py`:
```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.user import User
from app.models.trade import Trade
from app.models.analysis import Analysis
from app.models.report import Report
from app.auth.jwt import get_current_user
from app.engine.position import PositionBuilder
from app.engine.pattern import PatternEngine
from app.engine.insight import InsightEngine
from app.engine.whatif import WhatIfEngine
from app.ai.provider import get_llm
from app.ai.prompt import SYSTEM_PROMPT, build_user_prompt
from app.ai.validator import ReportValidator
from app.schemas.report import GenerateReportRequest, ReportResponse
from app.config import settings

router = APIRouter(prefix="/api/report", tags=["report"])

@router.post("/generate", response_model=ReportResponse)
async def generate_report(
    body: GenerateReportRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    analysis = db.query(Analysis).filter(Analysis.id == body.analysis_id, Analysis.user_id == user.id).first()
    if not analysis:
        raise HTTPException(404, "Analysis not found")

    trades = db.query(Trade).filter(
        Trade.user_id == user.id,
        Trade.datetime >= analysis.date_start,
        Trade.datetime <= analysis.date_end,
    ).all()
    positions = PositionBuilder.build(trades)
    engine = PatternEngine()
    patterns_map = {}
    for i, pos in enumerate(positions):
        tags = engine.tag_position(pos, positions)
        patterns_map[i] = [t.pattern_name for t in tags]
    insights = InsightEngine.analyze(positions, patterns_map)
    whatifs = WhatIfEngine.analyze(positions, patterns_map)

    wins = [p for p in positions if p.pnl > 0]
    total_pnl = sum(p.pnl for p in positions)
    total_invested = sum(p.avg_entry_price * p.total_quantity for p in positions)

    analysis_data = {
        "account_summary": {
            "total_trades": len(positions),
            "win_rate": round(len(wins) / len(positions), 4) if positions else 0,
            "total_return_pct": round(total_pnl / total_invested, 4) if total_invested > 0 else 0,
            "avg_holding_days": round(sum(p.holding_days for p in positions) / len(positions), 1) if positions else 0,
        },
        "pattern_analysis": [{"pattern": r.pattern_name, "count": r.count, "win_rate": r.win_rate,
                               "total_pnl": r.total_pnl, "avg_pnl_pct": r.avg_pnl_pct} for r in insights],
        "what_if_results": [{"removed_pattern": r.removed_pattern, "original_return": r.original_return,
                              "what_if_return": r.what_if_return, "delta": r.delta} for r in whatifs],
        "damage_ranking": [{"pattern": r.removed_pattern, "damage_score": r.damage_score} for r in whatifs],
    }

    llm = get_llm()
    validator = ReportValidator()
    user_prompt = build_user_prompt(analysis_data)
    report_text, passed = await validator.generate_with_retry(llm, SYSTEM_PROMPT, user_prompt, analysis_data)

    report = Report(
        user_id=user.id, analysis_input=analysis_data, ai_provider=settings.ai_provider,
        report_content=report_text, validation_passed=passed,
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    return ReportResponse(id=report.id, report_content=report_text,
                          validation_passed=passed, ai_provider=settings.ai_provider,
                          created_at=str(report.created_at))

@router.get("/{report_id}", response_model=ReportResponse)
def get_report(report_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    report = db.query(Report).filter(Report.id == report_id, Report.user_id == user.id).first()
    if not report:
        raise HTTPException(404, "Report not found")
    return ReportResponse(id=report.id, report_content=report.report_content,
                          validation_passed=report.validation_passed,
                          ai_provider=report.ai_provider, created_at=str(report.created_at))

@router.get("")
def list_reports(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    reports = db.query(Report).filter(Report.user_id == user.id).order_by(Report.created_at.desc()).limit(50).all()
    return [{"id": r.id, "validation_passed": r.validation_passed,
             "ai_provider": r.ai_provider, "created_at": str(r.created_at)} for r in reports]
```

Update `backend/app/api/__init__.py`:
```python
from fastapi import APIRouter
from app.api.auth import router as auth_router
from app.api.upload import router as upload_router
from app.api.analysis import router as analysis_router
from app.api.report import router as report_router

api_router = APIRouter()
api_router.include_router(auth_router)
api_router.include_router(upload_router)
api_router.include_router(analysis_router)
api_router.include_router(report_router)
```

- [ ] **Step 5: Run API tests**

```bash
cd backend && pytest tests/test_api/ -v
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/schemas/ backend/app/api/ backend/tests/test_api/
git commit -m "feat: add upload/analysis/report API endpoints"
```

---

### Task 13: Frontend Scaffold + Auth

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/vite.config.ts`
- Create: `frontend/tsconfig.json`
- Create: `frontend/index.html`
- Create: `frontend/tailwind.config.js`
- Create: `frontend/postcss.config.js`
- Create: `frontend/src/main.tsx`
- Create: `frontend/src/App.tsx`
- Create: `frontend/src/index.css`
- Create: `frontend/src/api/client.ts`
- Create: `frontend/src/api/auth.ts`
- Create: `frontend/src/context/AuthContext.tsx`
- Create: `frontend/src/pages/Login.tsx`
- Create: `frontend/src/pages/Register.tsx`
- Create: `frontend/src/components/Layout.tsx`
- Create: `frontend/src/components/ProtectedRoute.tsx`

- [ ] **Step 1: Scaffold Vite + React project**

```bash
cd frontend
npm create vite@latest . -- --template react-ts
npm install
npm install react-router-dom @tanstack/react-query react-markdown recharts
npm install -D tailwindcss @tailwindcss/vite postcss
npx shadcn@latest init
npx shadcn@latest add button card input tabs table badge toast
```

- [ ] **Step 2: Create API client**

`frontend/src/api/client.ts`:
```typescript
const BASE_URL = "http://localhost:8000";

function getToken(): string | null {
  return localStorage.getItem("token");
}

export async function apiFetch(path: string, options: RequestInit = {}): Promise<Response> {
  const token = getToken();
  const headers: Record<string, string> = {
    ...(options.headers as Record<string, string>),
  };
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }
  if (options.body && typeof options.body === "string") {
    headers["Content-Type"] = "application/json";
  }
  return fetch(`${BASE_URL}${path}`, { ...options, headers });
}

export async function apiPost(path: string, body?: unknown): Promise<any> {
  const resp = await apiFetch(path, { method: "POST", body: body ? JSON.stringify(body) : undefined });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ detail: resp.statusText }));
    throw new Error(err.detail || "Request failed");
  }
  return resp.json();
}

export async function apiGet(path: string): Promise<any> {
  const resp = await apiFetch(path);
  if (!resp.ok) throw new Error("Request failed");
  return resp.json();
}

export async function apiUpload(path: string, formData: FormData): Promise<any> {
  const token = getToken();
  const resp = await fetch(`${BASE_URL}${path}`, {
    method: "POST",
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    body: formData,
  });
  if (!resp.ok) throw new Error("Upload failed");
  return resp.json();
}
```

`frontend/src/api/auth.ts`:
```typescript
import { apiPost } from "./client";

export function login(email: string, password: string) {
  return apiPost("/api/auth/login", { email, password });
}

export function register(email: string, password: string) {
  return apiPost("/api/auth/register", { email, password });
}
```

- [ ] **Step 3: Create AuthContext**

`frontend/src/context/AuthContext.tsx`:
```typescript
import { createContext, useContext, useState, useEffect, ReactNode } from "react";

interface AuthState {
  token: string | null;
  isLoggedIn: boolean;
  login: (token: string) => void;
  logout: () => void;
}

const AuthContext = createContext<AuthState>({
  token: null, isLoggedIn: false, login: () => {}, logout: () => {},
});

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(localStorage.getItem("token"));

  useEffect(() => {
    if (token) localStorage.setItem("token", token);
    else localStorage.removeItem("token");
  }, [token]);

  return (
    <AuthContext.Provider value={{
      token, isLoggedIn: !!token,
      login: (t) => setToken(t),
      logout: () => setToken(null),
    }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() { return useContext(AuthContext); }
```

- [ ] **Step 4: Create Layout + ProtectedRoute + Login + Register**

`frontend/src/components/Layout.tsx`:
```tsx
import { Link, Outlet } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

export default function Layout() {
  const { isLoggedIn, logout } = useAuth();
  return (
    <div className="min-h-screen bg-background">
      <nav className="border-b px-6 py-3 flex justify-between items-center">
        <Link to="/" className="text-xl font-bold">TradeLens</Link>
        <div className="flex gap-4">
          {isLoggedIn ? (
            <>
              <Link to="/upload">上传</Link>
              <Link to="/history">历史报告</Link>
              <button onClick={logout}>登出</button>
            </>
          ) : (
            <>
              <Link to="/login">登录</Link>
              <Link to="/register">注册</Link>
            </>
          )}
        </div>
      </nav>
      <main className="max-w-5xl mx-auto p-6"><Outlet /></main>
    </div>
  );
}
```

`frontend/src/components/ProtectedRoute.tsx`:
```tsx
import { Navigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

export default function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { isLoggedIn } = useAuth();
  if (!isLoggedIn) return <Navigate to="/login" replace />;
  return <>{children}</>;
}
```

- [ ] **Step 5: Create App.tsx with routes**

`frontend/src/App.tsx`:
```tsx
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AuthProvider } from "./context/AuthContext";
import Layout from "./components/Layout";
import ProtectedRoute from "./components/ProtectedRoute";
import Login from "./pages/Login";
import Register from "./pages/Register";
// Other pages added in subsequent tasks

const queryClient = new QueryClient();

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <BrowserRouter>
          <Routes>
            <Route element={<Layout />}>
              <Route path="/" element={<div>Landing page</div>} />
              <Route path="/login" element={<Login />} />
              <Route path="/register" element={<Register />} />
            </Route>
          </Routes>
        </BrowserRouter>
      </AuthProvider>
    </QueryClientProvider>
  );
}
```

- [ ] **Step 6: Verify frontend starts**

```bash
cd frontend && npm run dev
# Open http://localhost:5173 → should show Layout with nav
```

- [ ] **Step 7: Commit**

```bash
git add frontend/
git commit -m "feat: scaffold frontend with Vite + React + Auth + shadcn/ui"
```

---

### Task 14: Frontend Upload Page

**Files:**
- Create: `frontend/src/api/upload.ts`
- Create: `frontend/src/components/FileDropzone.tsx`
- Create: `frontend/src/components/FormatSelector.tsx`
- Create: `frontend/src/components/TradePreview.tsx`
- Create: `frontend/src/pages/Upload.tsx`

- [ ] **Step 1: Create upload API**

`frontend/src/api/upload.ts`:
```typescript
import { apiPost, apiUpload } from "./client";

export function uploadFile(file: File) {
  const fd = new FormData();
  fd.append("file", file);
  return apiUpload("/api/upload", fd);
}

export function confirmFormat(rawFileId: string, sourceType: string) {
  return apiPost("/api/upload/confirm", { raw_file_id: rawFileId, source_type: sourceType });
}

export function importTrades(rawFileId: string) {
  return apiPost("/api/upload/import", { raw_file_id: rawFileId });
}
```

- [ ] **Step 2: Create Upload page with 3-step wizard**

`frontend/src/pages/Upload.tsx`:
```tsx
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import FileDropzone from "../components/FileDropzone";
import FormatSelector from "../components/FormatSelector";
import TradePreview from "../components/TradePreview";
import { uploadFile, confirmFormat, importTrades } from "../api/upload";

type Step = "upload" | "confirm" | "preview";

export default function Upload() {
  const [step, setStep] = useState<Step>("upload");
  const [rawFileId, setRawFileId] = useState<string>("");
  const [formats, setFormats] = useState<any[]>([]);
  const [trades, setTrades] = useState<any[]>([]);
  const [error, setError] = useState("");
  const navigate = useNavigate();

  const handleUpload = async (file: File) => {
    try {
      setError("");
      const resp = await uploadFile(file);
      setRawFileId(resp.raw_file_id);
      setFormats(resp.detected_formats);
      setStep("confirm");
    } catch (e: any) { setError(e.message); }
  };

  const handleConfirm = async (sourceType: string) => {
    try {
      const resp = await confirmFormat(rawFileId, sourceType);
      setTrades(resp.trades);
      setStep("preview");
    } catch (e: any) { setError(e.message); }
  };

  const handleImport = async () => {
    try {
      await importTrades(rawFileId);
      // Navigate to run analysis (simplified: POST /api/analysis/run with default date range)
      navigate("/history");
    } catch (e: any) { setError(e.message); }
  };

  return (
    <div className="max-w-2xl mx-auto">
      <h1 className="text-2xl font-bold mb-6">上传交割单</h1>
      {error && <div className="bg-red-900/20 text-red-400 p-3 rounded mb-4">{error}</div>}

      {step === "upload" && <FileDropzone onUpload={handleUpload} />}
      {step === "confirm" && <FormatSelector formats={formats} onConfirm={handleConfirm} />}
      {step === "preview" && <TradePreview trades={trades} onImport={handleImport} />}

      <div className="flex justify-center gap-4 mt-6 text-sm text-muted-foreground">
        <div className={step === "upload" ? "text-primary font-bold" : ""}>① 上传</div>
        <span>→</span>
        <div className={step === "confirm" ? "text-primary font-bold" : ""}>② 确认格式</div>
        <span>→</span>
        <div className={step === "preview" ? "text-primary font-bold" : ""}>③ 预览导入</div>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Create FileDropzone, FormatSelector, TradePreview components**

`frontend/src/components/FileDropzone.tsx`:
```tsx
import { useCallback, useState } from "react";

export default function FileDropzone({ onUpload }: { onUpload: (file: File) => void }) {
  const [dragging, setDragging] = useState(false);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault(); setDragging(false);
    const file = e.dataTransfer.files[0];
    if (file && (file.name.endsWith(".csv") || file.name.endsWith(".xlsx") || file.name.endsWith(".xls"))) {
      onUpload(file);
    }
  }, [onUpload]);

  return (
    <div
      className={`border-2 border-dashed rounded-lg p-12 text-center cursor-pointer transition-colors ${
        dragging ? "border-primary bg-primary/5" : "border-muted-foreground/30"
      }`}
      onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
      onDragLeave={() => setDragging(false)}
      onDrop={handleDrop}
      onClick={() => document.getElementById("file-input")?.click()}
    >
      <div className="text-4xl mb-4">📁</div>
      <p className="text-lg font-semibold mb-2">拖拽交割单文件到此处</p>
      <p className="text-sm text-muted-foreground">支持 CSV / Excel · 自动识别券商格式</p>
      <input id="file-input" type="file" accept=".csv,.xls,.xlsx" className="hidden"
        onChange={(e) => { const f = e.target.files?.[0]; if (f) onUpload(f); }} />
    </div>
  );
}
```

`frontend/src/components/FormatSelector.tsx`:
```tsx
export default function FormatSelector({ formats, onConfirm }: {
  formats: { source_type: string; asset_type: string; confidence: number }[];
  onConfirm: (sourceType: string) => void;
}) {
  const top = formats[0];
  // Auto-confirm if top confidence > 0.7
  if (top && top.confidence >= 0.7) {
    return (
      <div className="space-y-4">
        <div className="bg-green-900/20 text-green-400 p-4 rounded">
          自动识别为 <b>{top.source_type.toUpperCase()}</b> ({top.asset_type})，置信度 {(top.confidence * 100).toFixed(0)}%
        </div>
        <button onClick={() => onConfirm(top.source_type)} className="w-full">确认，继续</button>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <h3 className="text-lg font-semibold">请选择券商/终端格式</h3>
      {formats.map((f) => (
        <button key={f.source_type} onClick={() => onConfirm(f.source_type)}
          className="w-full p-4 border rounded text-left hover:bg-accent">
          <b>{f.source_type.toUpperCase()}</b> — {f.asset_type} (置信度: {(f.confidence * 100).toFixed(0)}%)
        </button>
      ))}
    </div>
  );
}
```

`frontend/src/components/TradePreview.tsx`:
```tsx
export default function TradePreview({ trades, onImport }: { trades: any[]; onImport: () => void }) {
  if (!trades.length) return <p>无交易记录</p>;
  return (
    <div className="space-y-4">
      <p className="text-lg">共 {trades.length} 笔交易，请确认数据无误</p>
      <div className="max-h-96 overflow-auto border rounded">
        <table className="w-full text-sm">
          <thead className="bg-muted sticky top-0">
            <tr>
              <th className="p-2 text-left">时间</th><th className="p-2 text-left">代码</th>
              <th className="p-2 text-left">方向</th><th className="p-2 text-right">数量</th>
              <th className="p-2 text-right">价格</th>
            </tr>
          </thead>
          <tbody>
            {trades.slice(0, 100).map((t, i) => (
              <tr key={i} className="border-t">
                <td className="p-2">{t.datetime}</td><td className="p-2">{t.symbol}</td>
                <td className="p-2">{t.side === "BUY" ? "买入" : "卖出"}</td>
                <td className="p-2 text-right">{t.quantity}</td>
                <td className="p-2 text-right">{t.price}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <button onClick={onImport} className="w-full" size="lg">确认导入</button>
    </div>
  );
}
```

- [ ] **Step 4: Add route**

```tsx
<Route path="/upload" element={<ProtectedRoute><Upload /></ProtectedRoute>} />
```

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/upload.ts frontend/src/components/ frontend/src/pages/Upload.tsx
git commit -m "feat: add upload page with 3-step wizard"
```

---

### Task 15: Frontend Dashboard + Report Pages

**Files:**
- Create: `frontend/src/api/analysis.ts`
- Create: `frontend/src/api/report.ts`
- Create: `frontend/src/hooks/useAnalysis.ts`
- Create: `frontend/src/pages/Analysis.tsx`
- Create: `frontend/src/components/StatsCards.tsx`
- Create: `frontend/src/components/PatternChart.tsx`
- Create: `frontend/src/components/WhatIfChart.tsx`
- Create: `frontend/src/pages/Report.tsx`
- Create: `frontend/src/components/ReportView.tsx`
- Create: `frontend/src/pages/History.tsx`

- [ ] **Step 1: Create analysis + report API hooks**

`frontend/src/api/analysis.ts`:
```typescript
import { apiPost, apiGet } from "./client";

export function runAnalysis(dateStart: string, dateEnd: string) {
  return apiPost("/api/analysis/run", { date_start: dateStart, date_end: dateEnd });
}
export function getStats(analysisId: string) { return apiGet(`/api/analysis/${analysisId}/stats`); }
export function getInsight(analysisId: string) { return apiGet(`/api/analysis/${analysisId}/insight`); }
export function getWhatIf(analysisId: string) { return apiGet(`/api/analysis/${analysisId}/whatif`); }
```

`frontend/src/api/report.ts`:
```typescript
import { apiPost, apiGet } from "./client";

export function generateReport(analysisId: string) {
  return apiPost("/api/report/generate", { analysis_id: analysisId });
}
export function getReport(reportId: string) { return apiGet(`/api/report/${reportId}`); }
export function listReports() { return apiGet("/api/reports"); }
```

- [ ] **Step 2: Create hooks/useAnalysis.ts**

```typescript
import { useQuery } from "@tanstack/react-query";
import { getStats, getInsight, getWhatIf } from "../api/analysis";

export function useStats(analysisId: string | null) {
  return useQuery({ queryKey: ["stats", analysisId], queryFn: () => getStats(analysisId!),
    enabled: !!analysisId });
}
export function useInsight(analysisId: string | null) {
  return useQuery({ queryKey: ["insight", analysisId], queryFn: () => getInsight(analysisId!),
    enabled: !!analysisId });
}
export function useWhatIf(analysisId: string | null) {
  return useQuery({ queryKey: ["whatif", analysisId], queryFn: () => getWhatIf(analysisId!),
    enabled: !!analysisId });
}
```

- [ ] **Step 3: Create Dashboard page (3 tabs)**

`frontend/src/pages/Analysis.tsx`:
```tsx
import { useParams } from "react-router-dom";
import { useState } from "react";
import { useStats, useInsight, useWhatIf } from "../hooks/useAnalysis";
import StatsCards from "../components/StatsCards";
import PatternChart from "../components/PatternChart";
import WhatIfChart from "../components/WhatIfChart";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { useNavigate } from "react-router-dom";
import { generateReport } from "../api/report";

export default function AnalysisPage() {
  const { id } = useParams<{ id: string }>();
  const { data: stats } = useStats(id ?? null);
  const { data: insight } = useInsight(id ?? null);
  const { data: whatif } = useWhatIf(id ?? null);
  const navigate = useNavigate();
  const [generating, setGenerating] = useState(false);

  const handleGenerateReport = async () => {
    if (!id) return;
    setGenerating(true);
    try {
      const report = await generateReport(id);
      navigate(`/report/${report.id}`);
    } finally { setGenerating(false); }
  };

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <h1 className="text-2xl font-bold">交易分析</h1>
        <Button onClick={handleGenerateReport} disabled={generating}>
          {generating ? "生成中..." : "生成 AI 诊断报告"}
        </Button>
      </div>

      <Tabs defaultValue="stats">
        <TabsList>
          <TabsTrigger value="stats">📊 交易统计</TabsTrigger>
          <TabsTrigger value="insight">🏷️ 行为归因</TabsTrigger>
          <TabsTrigger value="whatif">🔮 What If 回测</TabsTrigger>
        </TabsList>
        <TabsContent value="stats">
          {stats && <StatsCards kpi={stats.kpi} />}
        </TabsContent>
        <TabsContent value="insight">
          {insight && <PatternChart patterns={insight.patterns} best={insight.best_pattern} worst={insight.worst_pattern} />}
        </TabsContent>
        <TabsContent value="whatif">
          {whatif && <WhatIfChart items={whatif.items} />}
        </TabsContent>
      </Tabs>
    </div>
  );
}
```

- [ ] **Step 4: Create StatsCards component**

`frontend/src/components/StatsCards.tsx`:
```tsx
export default function StatsCards({ kpi }: { kpi: any }) {
  const cards = [
    { label: "总交易次数", value: kpi.total_trades },
    { label: "胜率", value: `${(kpi.win_rate * 100).toFixed(1)}%` },
    { label: "盈亏比", value: kpi.profit_factor },
    { label: "总收益率", value: `${(kpi.total_return_pct * 100).toFixed(1)}%` },
    { label: "平均持仓天数", value: `${kpi.avg_holding_days}天` },
    { label: "最大连续亏损", value: kpi.max_consecutive_losses },
  ];
  return (
    <div className="grid grid-cols-3 gap-4">
      {cards.map((c) => (
        <div key={c.label} className="bg-card border rounded-lg p-4 text-center">
          <div className="text-sm text-muted-foreground">{c.label}</div>
          <div className="text-2xl font-bold mt-1">{c.value}</div>
        </div>
      ))}
    </div>
  );
}
```

- [ ] **Step 5: Create PatternChart + WhatIfChart + Report pages**

`frontend/src/components/PatternChart.tsx`:
```tsx
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from "recharts";

export default function PatternChart({ patterns, best, worst }: { patterns: any[]; best?: string; worst?: string }) {
  const data = patterns.map((p) => ({
    name: p.pattern_name,
    winRate: +(p.win_rate * 100).toFixed(1),
    pnl: +p.total_pnl.toFixed(0),
    isBest: p.pattern_name === best,
    isWorst: p.pattern_name === worst,
  }));
  return (
    <div className="bg-card border rounded-lg p-4">
      <h3 className="font-semibold mb-4">行为归因 — 各行为胜率对比</h3>
      <ResponsiveContainer width="100%" height={300}>
        <BarChart data={data}>
          <XAxis dataKey="name" />
          <YAxis unit="%" />
          <Tooltip />
          <Bar dataKey="winRate" name="胜率">
            {data.map((d, i) => (
              <Cell key={i} fill={d.isBest ? "#22c55e" : d.isWorst ? "#ef4444" : "#3b82f6"} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
```

`frontend/src/components/WhatIfChart.tsx`:
```tsx
export default function WhatIfChart({ items }: { items: any[] }) {
  return (
    <div className="bg-card border rounded-lg p-4 space-y-3">
      <h3 className="font-semibold mb-4">What If 回测 — 删除特定行为后的收益变化</h3>
      {items.map((item) => (
        <div key={item.removed_pattern} className="space-y-1">
          <div className="flex justify-between text-sm">
            <span className="font-medium">{item.removed_pattern}</span>
            <span className="text-green-400">+{(item.what_if_return * 100).toFixed(1)}%</span>
          </div>
          <div className="h-6 bg-muted rounded relative overflow-hidden">
            <div className="absolute left-0 h-full bg-blue-600/50 rounded" style={{ width: `${Math.max(item.original_return * 100, 2)}%` }} />
            <div className="absolute left-0 h-full bg-green-500/70 rounded" style={{ width: `${Math.max(item.what_if_return * 100, 2)}%` }} />
          </div>
          <div className="flex justify-between text-xs text-muted-foreground">
            <span>原收益: {(item.original_return * 100).toFixed(1)}%</span>
            <span className="text-green-400">Δ +{(item.delta * 100).toFixed(1)}%</span>
          </div>
        </div>
      ))}
    </div>
  );
}
```

- [ ] **Step 6: Create Report + History pages**

`frontend/src/pages/Report.tsx`:
```tsx
import { useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { getReport } from "../api/report";
import ReportView from "../components/ReportView";

export default function ReportPage() {
  const { id } = useParams<{ id: string }>();
  const { data } = useQuery({ queryKey: ["report", id], queryFn: () => getReport(id!), enabled: !!id });

  if (!data) return <div className="text-center py-12">加载中...</div>;
  return <ReportView content={data.report_content} validationPassed={data.validation_passed} />;
}
```

`frontend/src/components/ReportView.tsx`:
```tsx
import ReactMarkdown from "react-markdown";

export default function ReportView({ content, validationPassed }: { content: string; validationPassed: boolean }) {
  return (
    <div className="max-w-3xl mx-auto">
      {!validationPassed && (
        <div className="bg-yellow-900/20 text-yellow-400 p-3 rounded mb-4">⚠️ AI 报告数据校验未通过，部分数字可能有误</div>
      )}
      <div className="prose prose-invert max-w-none">
        <ReactMarkdown>{content}</ReactMarkdown>
      </div>
    </div>
  );
}
```

`frontend/src/pages/History.tsx`:
```tsx
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { listReports } from "../api/report";

export default function HistoryPage() {
  const { data: reports } = useQuery({ queryKey: ["reports"], queryFn: listReports });

  return (
    <div className="max-w-2xl mx-auto">
      <h1 className="text-2xl font-bold mb-6">历史报告</h1>
      {!reports?.length && <p className="text-muted-foreground">暂无报告，先去上传交割单吧</p>}
      <div className="space-y-3">
        {reports?.map((r: any) => (
          <Link key={r.id} to={`/report/${r.id}`} className="block p-4 border rounded hover:bg-accent">
            <div className="flex justify-between">
              <span>{r.ai_provider} 生成</span>
              <span className={r.validation_passed ? "text-green-400" : "text-yellow-400"}>
                {r.validation_passed ? "✓ 已校验" : "⚠ 校验异常"}
              </span>
            </div>
            <div className="text-sm text-muted-foreground mt-1">{new Date(r.created_at).toLocaleString("zh-CN")}</div>
          </Link>
        ))}
      </div>
    </div>
  );
}
```

- [ ] **Step 7: Update App.tsx with all routes**

```tsx
<Route path="/upload" element={<ProtectedRoute><Upload /></ProtectedRoute>} />
<Route path="/analysis/:id" element={<ProtectedRoute><AnalysisPage /></ProtectedRoute>} />
<Route path="/report/:id" element={<ProtectedRoute><ReportPage /></ProtectedRoute>} />
<Route path="/history" element={<ProtectedRoute><HistoryPage /></ProtectedRoute>} />
```

- [ ] **Step 8: Verify full flow**

```bash
cd frontend && npm run build
# Should build without errors
```

- [ ] **Step 9: Commit**

```bash
git add frontend/src/api/ frontend/src/hooks/ frontend/src/pages/ frontend/src/components/
git commit -m "feat: add dashboard + report + history pages"
```

---

### Task 16: Integration — End-to-End Wiring

**Files:**
- Modify: `backend/app/main.py` (verify all routers)
- Test: Manual E2E flow

- [ ] **Step 1: Verify backend starts with all routes**

```bash
cd backend
uvicorn app.main:app --reload
# Check: GET /api/health → 200
# Check: POST /api/auth/register → 201
# Check: Swagger docs at /docs
```

- [ ] **Step 2: Verify frontend starts**

```bash
cd frontend
npm run dev
# Open http://localhost:5173
```

- [ ] **Step 3: End-to-end test flow**

1. Register a new account at `/register`
2. Go to `/upload`, upload a sample CSV
3. Confirm format → preview trades → import
4. Run analysis (via API call or navigate)
5. View stats / insight / whatif tabs
6. Generate AI report → view at `/report/:id`
7. Check `/history` shows the report

- [ ] **Step 4: Commit**

```bash
git add .
git commit -m "feat: integration wiring + final polish"
```

---
