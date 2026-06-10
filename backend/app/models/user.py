"""User model."""
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import Column, DateTime, String

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    created_at = Column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )
