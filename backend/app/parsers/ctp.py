"""CTP (综合交易平台) futures parser."""

import pandas as pd

from app.parsers.base import BaseParser, TradeData
from app.parsers import _get_multiplier, _get_exchange


class CTPParser(BaseParser):
    MARGIN_RATE = 0.1

    @classmethod
    def source_type(cls) -> str:
        return "ctp"

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
            ["交易日", "合约代码", "买卖", "成交量", "成交价"],
        )

    @classmethod
    def parse(cls, content: bytes, filename: str) -> list[TradeData]:
        df = cls._read_df(content, filename)
        df.columns = df.columns.str.strip()
        trades: list[TradeData] = []
        for _, row in df.iterrows():
            symbol = str(row["合约代码"]).strip()
            raw_side = str(row["买卖"]).strip()
            side = "BUY" if raw_side == "买" else "SELL"
            multiplier = _get_multiplier(symbol)
            price = float(row["成交价"])
            quantity = float(row["成交量"])
            margin = price * multiplier * quantity * cls.MARGIN_RATE
            trades.append(
                TradeData(
                    datetime=pd.to_datetime(row["交易日"]),
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
