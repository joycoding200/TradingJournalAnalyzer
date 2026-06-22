"""Auth API routes: register, login, me, update profile."""
import re

from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from app.auth.jwt import create_token, get_current_user, hash_password, verify_password
from app.database import get_db
from app.ratelimit import limiter
from app.models.user import User, generate_nickname
from app.schemas.auth import (
    LoginRequest,
    PasswordCheckRequest,
    RegisterRequest,
    TokenResponse,
    UpdateProfileRequest,
    UserResponse,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _check_password_strength(pw: str) -> str | None:
    """Validate password strength. Returns error message or None."""
    if len(pw) < 8:
        return "密码至少需要 8 个字符"
    if not re.search(r"[A-Za-z]", pw):
        return "密码需要包含至少一个英文字母"
    if not re.search(r"\d", pw):
        return "密码需要包含至少一个数字"
    # Check for common weak passwords
    common = {"12345678", "password", "11111111", "88888888", "qwertyui"}
    if pw.lower() in common:
        return "密码过于简单，请换一个更安全的密码"
    return None


def _password_strength_score(pw: str) -> int:
    """Return 0-4 strength score."""
    score = 0
    if len(pw) >= 12: score += 1
    if re.search(r"[A-Z]", pw) and re.search(r"[a-z]", pw): score += 1
    if re.search(r"\d", pw): score += 1
    if re.search(r"[^A-Za-z0-9]", pw): score += 1
    return score


@router.post(
    "/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED
)
@limiter.limit("5/minute")
def register(request: Request, body: RegisterRequest, db: Session = Depends(get_db)):
    if not body.email and not body.phone:
        raise HTTPException(status_code=400, detail="请填写邮箱或手机号")

    # Password strength check
    err = _check_password_strength(body.password)
    if err:
        raise HTTPException(status_code=400, detail=err)

    # Check duplicate email/phone (generic message to prevent account enumeration)
    if body.email and db.query(User).filter(User.email == body.email).first():
        raise HTTPException(status_code=409, detail="注册失败，请检查输入")
    if body.phone and db.query(User).filter(User.phone == body.phone).first():
        raise HTTPException(status_code=409, detail="注册失败，请检查输入")

    user = User(
        email=body.email or None,
        phone=body.phone or None,
        nickname=generate_nickname(),
        password_hash=hash_password(body.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return TokenResponse(access_token=create_token(user.id))


@router.post("/login", response_model=TokenResponse)
@limiter.limit("5/minute")
def login(request: Request, body: LoginRequest, db: Session = Depends(get_db)):
    # Try email first, then phone
    user = db.query(User).filter(
        (User.email == body.account) | (User.phone == body.account)
    ).first()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="账号或密码错误")
    return TokenResponse(access_token=create_token(user.id))


@router.get("/me", response_model=UserResponse)
def me(current_user: User = Depends(get_current_user)):
    return UserResponse(
        id=current_user.id,
        email=current_user.email or "",
        phone=current_user.phone or "",
        nickname=current_user.nickname or "",
    )


@router.put("/me", response_model=UserResponse)
def update_profile(
    body: UpdateProfileRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if body.nickname:
        if len(body.nickname) < 2 or len(body.nickname) > 20:
            raise HTTPException(status_code=400, detail="昵称需要 2-20 个字符")
        current_user.nickname = body.nickname
        db.commit()
        db.refresh(current_user)
    return UserResponse(
        id=current_user.id,
        email=current_user.email or "",
        phone=current_user.phone or "",
        nickname=current_user.nickname or "",
    )


@router.post("/password-strength")
def check_strength(body: "PasswordCheckRequest"):
    """Return password strength score (0-4). POST to keep password out of URL logs."""
    err = _check_password_strength(body.password)
    score = _password_strength_score(body.password)
    labels = {0: "弱", 1: "一般", 2: "中等", 3: "强", 4: "很强"}
    return {
        "score": score if not err else 0,
        "label": labels.get(score, "弱") if not err else "弱",
        "hint": err or "",
    }
