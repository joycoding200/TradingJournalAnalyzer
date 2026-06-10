"""Wenhua (文华) futures parser."""

import pandas as pd

from app.parsers.base import BaseParser, TradeData
from app.parsers import _get_multiplier, _get_exchange


class WenhuaParser(BaseParser):
    MARGIN_RATE = 0.1  # Default margin rate for futures

    @classmethod
    def source_type(cls) -> str:
        return "wenhua"

    @classmethod
    def asset_type(cls) -> str:
        return "future"

    @classmethod
    def detect(cls, content: bytes, filename: str) -> float:
        try:
            df = cls._read_df(content, filename)
        except Exception:
            return 0.0
        return cls._column_match_score(
            df.columns.tolist(),
            ["开平", "合约", "手数", "成交价"],
        )

    @classmethod
    def parse(cls, content: bytes, filename: str) -> list[TradeData]:
        df = cls._read_df(content, filename)
        df.columns = df.columns.str.strip()
        trades: list[TradeData] = []
        for _, row in df.iterrows():
            symbol = str(row["合约"]).strip()
            raw_side = str(row["开平"]).strip()
            side = "BUY" if raw_side in ("开", "买") else "SELL"
            multiplier = _get_multiplier(symbol)
            price = float(row["成交价"])
            quantity = float(row["手数"])
            margin = price * multiplier * quantity * cls.MARGIN_RATE
            trades.append(
                TradeData(
                    datetime=pd.to_datetime(row.get("成交日期", row.get("日期", pd.Timestamp.now().date()))),
                    symbol=symbol,
                    exchange=_get_exchange(symbol),
                    side=side,
                    quantity=quantity,
                    price=price,
                    multiplier=multiplier,
                    margin=margin,
                    commission=float(row.get("手续费", 0) or 0),
                )
            )
        return trades
