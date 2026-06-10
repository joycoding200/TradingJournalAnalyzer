"""VNPY stock parser."""

import pandas as pd

from app.parsers.base import BaseParser, TradeData
from app.parsers import _get_exchange


class VnpyParser(BaseParser):
    @classmethod
    def source_type(cls) -> str:
        return "vnpy"

    @classmethod
    def asset_type(cls) -> str:
        return "stock"

    @classmethod
    def detect(cls, content: bytes, filename: str) -> float:
        try:
            df = cls._read_df(content, filename)
        except Exception:
            return 0.0
        return cls._column_match_score(
            df.columns.tolist(),
            ["datetime", "symbol", "direction", "price", "volume"],
        )

    @classmethod
    def parse(cls, content: bytes, filename: str) -> list[TradeData]:
        df = cls._read_df(content, filename)
        df.columns = df.columns.str.strip()
        trades: list[TradeData] = []
        for _, row in df.iterrows():
            symbol = str(row["symbol"]).zfill(6)
            raw_side = str(row["direction"]).strip().upper()
            side = "BUY" if raw_side in ("LONG", "BUY") else "SELL"
            trades.append(
                TradeData(
                    datetime=pd.to_datetime(row["datetime"]),
                    symbol=symbol,
                    exchange=_get_exchange(symbol),
                    side=side,
                    quantity=float(row["volume"]),
                    price=float(row["price"]),
                    commission=float(row.get("commission", 0) or 0),
                )
            )
        return trades
