"""JWT auth helpers: hash, verify, create_token, get_current_user.

Supports both Bearer token (Authorization header) and httpOnly cookie
authentication. The cookie path is the recommended secure approach
(immune to XSS-based token theft); the Bearer header is retained for
backward compatibility with existing API clients.
"""

from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.user import User

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class _OAuth2WithCookie(HTTPBearer):
    """Bearer scheme that also reads the token from an httpOnly cookie.

    Checks the ``access_token`` cookie first (preferred — XSS-safe),
    then falls back to the ``Authorization: Bearer <token>`` header.
    """

    async def __call__(self, request: Request):
        token = request.cookies.get("access_token")
        if token:
            return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
        return await super().__call__(request)


security = _OAuth2WithCookie()


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_token(user_id: str, scope: str | None = None) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)
    payload = {
        "sub": user_id,
        "exp": expire,
        "iat": datetime.now(timezone.utc).timestamp(),
        "jti": str(__import__("uuid").uuid4()),  # unique token ID for revocation
        "aud": settings.jwt_audience,            # audience binding: this token is only valid for TJA API
    }
    if scope:
        payload["scope"] = scope
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def set_auth_cookie(response, token: str) -> None:
    """Set the JWT as an httpOnly cookie on the response.

    Call this from login/register endpoints after creating a token.
    The cookie is httpOnly (inaccessible to JS) to prevent XSS token theft.
    secure flag is derived from ENV: True in production, False in development.
    """
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        samesite="lax",
        max_age=settings.jwt_expire_minutes * 60,
        secure=settings.cookie_secure,
        path="/",
    )


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
) -> User:
    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.secret_key,
            algorithms=[settings.jwt_algorithm],
            audience=settings.jwt_audience,
        )
        user_id = payload.get("sub")
        if user_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token"
            )
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token"
        )
    # Check if token has been revoked (logout)
    jti = payload.get("jti")
    if jti:
        from app.models.token_blacklist import TokenBlacklist
        blacklisted = db.query(TokenBlacklist).filter(TokenBlacklist.jti == jti).first()
        if blacklisted:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Token has been revoked"
            )
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found"
        )
    return user


def get_token_payload(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.secret_key,
            algorithms=[settings.jwt_algorithm],
            audience=settings.jwt_audience,
        )
        return payload
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token"
        )
