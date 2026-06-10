"""Citic (中信证券) broker parser."""

import pandas as pd

from app.parsers.base import BaseParser, TradeData
from app.parsers import _get_exchange, _find_col


class CiticParser(BaseParser):
    @classmethod
    def source_type(cls) -> str:
        return "broker"

    @classmethod
    def asset_type(cls) -> str:
        return "stock"

    @classmethod
    def detect(cls, content: bytes, filename: str) -> float:
        try:
            df = cls._read_df(content, filename)
        except Exception:
            return 0.0
        cols_lower = [c.strip().lower() for c in df.columns]
        keywords = ["成交", "代码", "价格", "数量"]
        matched = sum(1 for kw in keywords if any(kw in c for c in cols_lower))
        return (matched / len(keywords)) * 0.85

    @classmethod
    def parse(cls, content: bytes, filename: str) -> list[TradeData]:
        df = cls._read_df(content, filename)
        df.columns = df.columns.str.strip()
        col_map = {c.lower(): c for c in df.columns}

        date_col = _find_col(col_map, [
            "成交日期", "交易日期", "发生日期", "委托日期", "日期", "成交时间", "时间",
        ])
        code_col = _find_col(col_map, [
            "证券代码", "代码", "合约代码", "品种代码", "股票代码", "合约",
        ])
        price_col = _find_col(col_map, [
            "成交价格", "成交均价", "价格", "成交价", "均价",
        ])
        qty_col = _find_col(col_map, [
            "成交数量", "数量", "成交量", "手数", "成交股数",
        ])
        side_col = _find_col(col_map, [
            "买卖方向", "操作", "买卖标志", "方向", "买卖", "成交方向",
        ])
        commission_col = _find_col(col_map, [
            "手续费", "佣金", "过户费", "印花税", "交易费用",
        ])

        if not all([date_col, code_col, price_col, qty_col]):
            return []

        trades: list[TradeData] = []
        for _, row in df.iterrows():
            symbol = str(row[code_col]).zfill(6)
            raw_side = str(row[side_col]).strip() if side_col else ""
            side = "BUY"
            if raw_side in ("卖", "卖出", "SELL", "SHORT", "s", "S"):
                side = "SELL"
            elif raw_side in ("买", "买入", "BUY", "LONG", "b", "B"):
                side = "BUY"

            trades.append(
                TradeData(
                    datetime=pd.to_datetime(row[date_col]),
                    symbol=symbol,
                    exchange=_get_exchange(symbol),
                    side=side,
                    quantity=float(row[qty_col]),
                    price=float(row[price_col]),
                    commission=float(row[commission_col]) if commission_col and pd.notna(row.get(commission_col)) else 0.0,
                )
            )
        return trades
