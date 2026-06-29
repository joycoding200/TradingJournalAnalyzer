"""User model."""
import random
from datetime import datetime, timezone
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Boolean, Column, DateTime, String

from app.database import Base

# Positive Chinese words for random nickname generation
_POSITIVE_ADJ = ["快乐的", "阳光的", "勇敢的", "温暖的", "聪慧的", "坚定的", "乐观的", "自信的", "开朗的", "热情的"]
_POSITIVE_NOUNS = ["菠菜", "熊猫", "向日葵", "星辰", "海豚", "银杏", "彩虹", "小鹿", "清风", "竹子", "雪山", "小溪", "蓝莓", "松树", "月光"]


def generate_nickname() -> str:
    """Generate a random positive Chinese nickname like '爱笑的菠菜'."""
    adj = random.choice(_POSITIVE_ADJ)
    noun = random.choice(_POSITIVE_NOUNS)
    return f"{adj}{noun}"


class User(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    email = Column(String(255), unique=True, nullable=True, index=True)
    phone = Column(String(20), unique=True, nullable=True, index=True)
    nickname = Column(String(50), nullable=True)
    is_admin = Column(Boolean, default=False, nullable=False)
    password_hash = Column(String(255), nullable=False)
    # Admin login audit trail (D3.3). Only updated on admin login.
    last_login_at = Column(DateTime, nullable=True)
    last_login_ip = Column(String(45), nullable=True)
    created_at = Column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc),
        server_default=sa.func.now()
    )
