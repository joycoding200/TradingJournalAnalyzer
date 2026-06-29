"""Auth API routes: register, login, me, update profile."""
import logging
import re

from fastapi import APIRouter, Depends, HTTPException, Response, status, Request
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)
from datetime import datetime, timezone

from app.auth.jwt import create_token, get_current_user, get_token_payload, hash_password, set_auth_cookie, verify_password
from app.database import get_db
from app.ratelimit import limiter
from app.models.token_blacklist import TokenBlacklist
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

# Pre-computed dummy bcrypt hash to mitigate timing-based user enumeration.
# When a login attempt targets a non-existent account, we still run a full
# bcrypt verify against this dummy hash so the response time is indistinguishable
# from a failed password check against a real account (~200ms either way).
_DUMMY_HASH = hash_password("dummy-u3n-mera1i0n-t1m1ng-d3f3ns3")


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
def register(request: Request, body: RegisterRequest, response: Response, db: Session = Depends(get_db)):
    if not body.email and not body.phone:
        raise HTTPException(status_code=400, detail="请填写邮箱或手机号")

    # Password strength check
    err = _check_password_strength(body.password)
    if err:
        raise HTTPException(status_code=400, detail=err)

    # Check duplicate email/phone
    if body.email and db.query(User).filter(User.email == body.email).first():
        raise HTTPException(status_code=409, detail="该邮箱已被注册，请直接登录")
    if body.phone and db.query(User).filter(User.phone == body.phone).first():
        raise HTTPException(status_code=409, detail="该手机号已被注册，请直接登录")

    user = User(
        email=body.email or None,
        phone=body.phone or None,
        nickname=body.nickname or generate_nickname(),
        password_hash=hash_password(body.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    token = create_token(user.id)
    set_auth_cookie(response, token)
    return TokenResponse(access_token=token)


@router.post("/login", response_model=TokenResponse)
@limiter.limit("5/minute")
def login(request: Request, body: LoginRequest, response: Response, db: Session = Depends(get_db)):
    # Try email first, then phone
    user = db.query(User).filter(
        (User.email == body.account) | (User.phone == body.account)
    ).first()
    if user is None:
        # Dummy verify to defeat timing-based user enumeration.
        verify_password(body.password, _DUMMY_HASH)
        logger.warning("login failed: account not found account=%s", body.account[:30])
        raise HTTPException(status_code=401, detail="账号或密码错误")
    if not verify_password(body.password, user.password_hash):
        logger.warning("login failed: wrong password user_id=%s", user.id)
        raise HTTPException(status_code=401, detail="账号或密码错误")
    token = create_token(user.id)
    set_auth_cookie(response, token)
    return TokenResponse(access_token=token)


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


@router.post("/logout")
def logout(
    current_user: User = Depends(get_current_user),
    payload: dict = Depends(get_token_payload),
    db: Session = Depends(get_db),
):
    """Revoke the current JWT token by adding its jti to the blacklist.

    After this call the token is invalid for all subsequent requests.
    Expired entries are cleaned up on each logout.
    """
    jti = payload.get("jti")
    exp = payload.get("exp")
    if jti and exp:
        expire_dt = datetime.fromtimestamp(float(exp), tz=timezone.utc)
        # Skip if already blacklisted (idempotent)
        existing = db.query(TokenBlacklist).filter(TokenBlacklist.jti == jti).first()
        if not existing:
            db.add(TokenBlacklist(jti=jti, expires_at=expire_dt))
            db.commit()
        # Clean up expired entries
        db.query(TokenBlacklist).filter(
            TokenBlacklist.expires_at < datetime.now(timezone.utc)
        ).delete()
        db.commit()
    return {"detail": "已登出"}


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
