"""Admin API: user search, data retrieval, file download."""
import io
import json
import re
import urllib.parse
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, status, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth.jwt import create_token, get_current_user, get_token_payload, hash_password, verify_password
from app.database import get_db
from app.ratelimit import limiter
from app.models.analysis import Analysis
from app.models.raw_file import RawFile
from app.models.report import Report
from app.models.trade import Trade
from app.models.user import User


UPLOAD_ROOT = Path(__file__).resolve().parent.parent.parent / "uploads"


def _read_raw_file_bytes(rf) -> bytes:
    """Read a RawFile's content from disk."""
    if not rf.file_path:
        return b""
    full_path = UPLOAD_ROOT / rf.file_path
    return full_path.read_bytes() if full_path.exists() else b""


router = APIRouter(prefix="/api/admin", tags=["admin"])

# Timing-attack defence identical to the main login endpoint.
# When admin_login targets a non-existent or non-admin account, we still
# run a full bcrypt verify so the response time is indistinguishable.
_ADMIN_DUMMY_HASH = hash_password("admin-dummy-u3n-mera1i0n-def3ns3")


def _safe_filename(name: str) -> str:
    """Strip CRLF and control characters to prevent header injection, use RFC 5987 encoding."""
    # First clean the filename
    cleaned = re.sub(r'[^A-Za-z0-9._-]', '_', name)
    return cleaned


def _require_admin(
    current_user: User = Depends(get_current_user),
    payload: dict = Depends(get_token_payload),
):
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="需要管理员权限")
    # Verify token has admin scope (for additional security)
    if payload.get("scope") != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return current_user


# --- Schemas ---

class AdminLoginRequest(BaseModel):
    username: str
    password: str


class UserSummary(BaseModel):
    id: str
    email: str = ""
    phone: str = ""
    nickname: str = ""
    created_at: str = ""
    file_count: int = 0
    analysis_count: int = 0
    report_count: int = 0


class FileItem(BaseModel):
    id: str
    filename: str
    source_type: str = ""
    uploaded_at: str = ""


class AnalysisItem(BaseModel):
    id: str
    filename: str = ""
    date_start: str = ""
    date_end: str = ""
    created_at: str = ""
    has_snapshot: bool = False
    has_report: bool = False


# --- Endpoints ---

@router.post("/login")
@limiter.limit("5/minute")
def admin_login(request: Request, body: AdminLoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(
        User.email == body.username, User.is_admin == True
    ).first()
    if user is None:
        # Dummy verify to defeat timing-based admin enumeration
        verify_password(body.password, _ADMIN_DUMMY_HASH)
        raise HTTPException(status_code=401, detail="管理员账号或密码错误")
    if not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="管理员账号或密码错误")
    return {"access_token": create_token(user.id, scope="admin"), "token_type": "bearer"}


@router.get("/users")
def search_users(
    q: str = Query(default=""),
    admin: User = Depends(_require_admin),
    db: Session = Depends(get_db),
) -> list[UserSummary]:
    query = db.query(User)
    if q:
        query = query.filter(
            (User.email.ilike(f"%{q}%")) | (User.nickname.ilike(f"%{q}%"))
        )
    users = query.order_by(User.created_at.desc()).limit(50).all()

    # Pre-aggregate counts in 3 queries instead of 3*N (N+1 → O(1))
    user_ids = [u.id for u in users]
    file_counts = {}
    analysis_counts = {}
    report_counts = {}
    if user_ids:
        file_counts = dict(
            db.query(RawFile.user_id, func.count(RawFile.id))
            .filter(RawFile.user_id.in_(user_ids))
            .group_by(RawFile.user_id).all()
        )
        analysis_counts = dict(
            db.query(Analysis.user_id, func.count(Analysis.id))
            .filter(Analysis.user_id.in_(user_ids))
            .group_by(Analysis.user_id).all()
        )
        report_counts = dict(
            db.query(Report.user_id, func.count(Report.id))
            .filter(Report.user_id.in_(user_ids))
            .group_by(Report.user_id).all()
        )

    result = []
    for u in users:
        result.append(UserSummary(
            id=u.id,
            email=u.email or "",
            phone=u.phone or "",
            nickname=u.nickname or "",
            created_at=str(u.created_at) if u.created_at else "",
            file_count=file_counts.get(u.id, 0),
            analysis_count=analysis_counts.get(u.id, 0),
            report_count=report_counts.get(u.id, 0),
        ))
    return result


@router.get("/users/{user_id}/files")
def get_user_files(
    user_id: str,
    admin: User = Depends(_require_admin),
    db: Session = Depends(get_db),
) -> list[FileItem]:
    files = (
        db.query(RawFile)
        .filter(RawFile.user_id == user_id)
        .order_by(RawFile.uploaded_at.desc())
        .all()
    )
    return [
        FileItem(
            id=f.id, filename=f.filename,
            source_type=f.source_type or "",
            uploaded_at=str(f.uploaded_at) if f.uploaded_at else "",
        )
        for f in files
    ]


@router.get("/users/{user_id}/analyses")
def get_user_analyses(
    user_id: str,
    admin: User = Depends(_require_admin),
    db: Session = Depends(get_db),
) -> list[AnalysisItem]:
    analyses = (
        db.query(Analysis)
        .filter(Analysis.user_id == user_id)
        .order_by(Analysis.created_at.desc())
        .all()
    )
    raw_ids = [a.raw_file_id for a in analyses if a.raw_file_id]
    fn_map = {}
    if raw_ids:
        rfs = db.query(RawFile).filter(RawFile.id.in_(raw_ids)).all()
        fn_map = {rf.id: rf.filename for rf in rfs}
    report_aids = set(
        r.analysis_id for r in
        db.query(Report.analysis_id).filter(Report.user_id == user_id, Report.analysis_id.in_([a.id for a in analyses])).all()
    )
    return [
        AnalysisItem(
            id=a.id,
            filename=fn_map.get(a.raw_file_id, ""),
            date_start=str(a.date_start) if a.date_start else "",
            date_end=str(a.date_end) if a.date_end else "",
            created_at=str(a.created_at) if a.created_at else "",
            has_snapshot=a.stats_snapshot is not None,
            has_report=a.id in report_aids,
        )
        for a in analyses
    ]


@router.get("/download/raw/{file_id}")
def download_raw_file(
    file_id: str,
    admin: User = Depends(_require_admin),
    db: Session = Depends(get_db),
):
    rf = db.query(RawFile).filter(RawFile.id == file_id).first()
    if not rf:
        raise HTTPException(status_code=404, detail="文件不存在")
    safe_name = _safe_filename(rf.filename)
    encoded_name = urllib.parse.quote(safe_name)
    return StreamingResponse(
        io.BytesIO(_read_raw_file_bytes(rf)),
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f"attachment; filename={safe_name}; filename*=UTF-8''{encoded_name}"
        },
    )


@router.get("/download/analysis/{analysis_id}")
def download_analysis_snapshot(
    analysis_id: str,
    admin: User = Depends(_require_admin),
    db: Session = Depends(get_db),
):
    a = db.query(Analysis).filter(Analysis.id == analysis_id).first()
    if not a:
        raise HTTPException(status_code=404, detail="分析不存在")
    data = {
        "id": a.id,
        "user_id": a.user_id,
        "date_start": str(a.date_start) if a.date_start else "",
        "date_end": str(a.date_end) if a.date_end else "",
        "created_at": str(a.created_at) if a.created_at else "",
        "stats_snapshot": a.stats_snapshot,
    }
    content = json.dumps(data, ensure_ascii=False, indent=2, default=str)
    return StreamingResponse(
        io.BytesIO(content.encode("utf-8")),
        media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename=analysis_{_safe_filename(analysis_id[:8])}.json"},
    )


@router.get("/download/report/{report_id}")
def download_report(
    report_id: str,
    admin: User = Depends(_require_admin),
    db: Session = Depends(get_db),
):
    r = db.query(Report).filter(Report.id == report_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="报告不存在")
    return StreamingResponse(
        io.BytesIO(r.report_content.encode("utf-8")),
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename=report_{_safe_filename(report_id[:8])}.md"},
    )
