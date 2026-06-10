"""QMT (迅投) stock parser."""

import pandas as pd

from app.parsers.base import BaseParser, TradeData
from app.parsers import _get_exchange


class QMTParser(BaseParser):
    @classmethod
    def source_type(cls) -> str:
        return "qmt"

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
            ["委托时间", "证券代码", "买卖方向", "成交价格", "成交数量"],
        )

    @classmethod
    def parse(cls, content: bytes, filename: str) -> list[TradeData]:
        df = cls._read_df(content, filename)
        df.columns = df.columns.str.strip()
        trades: list[TradeData] = []
        for _, row in df.iterrows():
            symbol = str(row["证券代码"]).zfill(6)
            raw_side = str(row["买卖方向"]).strip()
            trades.append(
                TradeData(
                    datetime=pd.to_datetime(row["委托时间"]),
                    symbol=symbol,
                    exchange=_get_exchange(symbol),
                    side="BUY" if raw_side == "买入" else "SELL",
                    quantity=float(row["成交数量"]),
                    price=float(row["成交价格"]),
                    commission=float(row.get("手续费", 0) or 0),
                )
            )
        return trades
