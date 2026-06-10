"""Tests for database models."""
from app.database import Base
from app.models import User, RawFile, Trade, Position, Pattern, Analysis, Report


def test_all_models_import():
    """Verify all models have correct table names."""
    assert User.__tablename__ == "users"
    assert RawFile.__tablename__ == "raw_files"
    assert Trade.__tablename__ == "trades"
    assert Position.__tablename__ == "positions"
    assert Pattern.__tablename__ == "patterns"
    assert Analysis.__tablename__ == "analyses"
    assert Report.__tablename__ == "reports"


def test_tables_created(db):
    """Verify all 7 tables are registered in metadata."""
    tables = Base.metadata.tables
    assert "users" in tables
    assert "raw_files" in tables
    assert "trades" in tables
    assert "positions" in tables
    assert "patterns" in tables
    assert "analyses" in tables
    assert "reports" in tables


def test_user_creation(db_session):
    """Test creating a User instance and persisting it."""
    user = User(email="test@test.com", password_hash="hash123")
    db_session.add(user)
    db_session.commit()
    assert user.id is not None
    assert user.email == "test@test.com"


def test_trade_indexes():
    """Verify Trade table has correct composite indexes."""
    indexes = {idx.name for idx in Trade.__table__.indexes}
    assert "ix_trades_user_datetime" in indexes
    assert "ix_trades_user_symbol_datetime" in indexes
