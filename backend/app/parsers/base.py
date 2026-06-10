from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from io import BytesIO

import pandas as pd


@dataclass
class TradeData:
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
    def source_type(cls) -> str: ...

    @classmethod
    @abstractmethod
    def asset_type(cls) -> str: ...

    @classmethod
    @abstractmethod
    def detect(cls, content: bytes, filename: str) -> float: ...

    @classmethod
    @abstractmethod
    def parse(cls, content: bytes, filename: str) -> list[TradeData]: ...

    @staticmethod
    def _read_df(content: bytes, filename: str) -> pd.DataFrame:
        if filename.endswith(".csv"):
            return pd.read_csv(BytesIO(content))
        elif filename.endswith((".xls", ".xlsx")):
            return pd.read_excel(BytesIO(content))
        raise ValueError(f"Unsupported file format: {filename}")

    @staticmethod
    def _column_match_score(df_columns: list[str], expected: list[str]) -> float:
        actual_lower = {c.strip().lower(): c for c in df_columns}
        matched = 0
        for exp in expected:
            if exp.lower() in actual_lower:
                matched += 1
        return matched / len(expected) if expected else 0.0
