"""CITIC Securities futures trade parser."""

import pandas as pd
from app.parsers.base import BaseParser, TradeData


# Column name candidates — use list of possible encodings to handle GBK/UTF-8 mismatches
_COL_CANDIDATES = {
    "date": ["成交日期"],
    "symbol": ["合约代码"],
    "side": ["买卖方向", "买卖"],
    "price": ["成交价格", "成交价"],
    "quantity": ["成交数量", "成交量", "手数"],
    "commission": ["手续费", "佣金"],
    "margin": ["保证金"],
}


def _find_col(col_map: dict, candidates: list[str]) -> str:
    """Find a column by trying multiple candidate names."""
    # Try exact match first
    for c in candidates:
        if c in col_map:
            return col_map[c]
    # Try stripped match
    stripped = {k.strip(): v for k, v in col_map.items()}
    for c in candidates:
        if c in stripped:
            return stripped[c]
    # Try substring match — find key that contains the candidate or vice versa
    for c in candidates:
        for k, v in col_map.items():
            if c in k or k in c:
                return v
    # Return first column that contains "成交" or "合约" as fallback
    for k, v in col_map.items():
        if "价格" in k or "价" in k:
            return v
    raise KeyError(f"None of {candidates} found in {list(col_map.keys())}")


class CiticFuturesParser(BaseParser):
    @classmethod
    def source_type(cls) -> str:
        return "citic_futures"

    @classmethod
    def asset_type(cls) -> str:
        return "future"

    @classmethod
    def detect(cls, content: bytes, filename: str) -> float:
        try:
            df = cls._read_df(content, filename)
        except Exception:
            return 0.0
        # Check for futures-specific columns: 合约代码, 开平仓
        all_cols = [str(c) for c in df.columns]
        keywords = ["合约", "开平", "成交日期", "成交价格", "成交数量", "手续费"]
        matched = sum(1 for kw in keywords if any(kw in c for c in all_cols))
        return matched / len(keywords)

    @classmethod
    def parse(cls, content: bytes, filename: str) -> list[TradeData]:
        df = cls._read_df(content, filename)
        col_map = {str(c): c for c in df.columns}
        # Also build a lower-case+strip map for fuzzy matching
        col_map_fuzzy = {}
        for k, v in col_map.items():
            col_map_fuzzy[k.strip()] = v
            col_map_fuzzy[k.strip().lower()] = v
        col_map = {**col_map, **col_map_fuzzy}

        trades = []
        for _, row in df.iterrows():
            symbol = str(row[_find_col(col_map, _COL_CANDIDATES["symbol"])]).strip()
            direction = str(row[_find_col(col_map, _COL_CANDIDATES["side"])])
            side = "BUY" if "买" in direction or "BUY" in direction.upper() else "SELL"

            price_col = _find_col(col_map, _COL_CANDIDATES["price"])
            qty_col = _find_col(col_map, _COL_CANDIDATES["quantity"])
            date_col = _find_col(col_map, _COL_CANDIDATES["date"])

            commission = 0.0
            try:
                comm_col = _find_col(col_map, _COL_CANDIDATES["commission"])
                commission = float(row[comm_col])
            except (KeyError, ValueError):
                pass

            margin = None
            try:
                margin_col = _find_col(col_map, _COL_CANDIDATES["margin"])
                margin = float(row[margin_col])
            except (KeyError, ValueError):
                pass

            multiplier = _get_futures_multiplier(symbol)

            trades.append(TradeData(
                datetime=pd.to_datetime(row[date_col]),
                symbol=symbol,
                exchange=_get_futures_exchange(symbol),
                side=side,
                quantity=float(row[qty_col]),
                price=float(row[price_col]),
                commission=commission,
                margin=margin,
                multiplier=multiplier,
            ))
        return trades


def _get_futures_exchange(symbol: str) -> str:
    upper = symbol.upper()
    # Strip numeric suffix for exchange detection
    import re
    base = re.sub(r'\d+$', '', upper)
    # CFFEX
    if base in ("IF", "IC", "IH", "IM") or base.startswith(("T", "TF", "TS")):
        return "CFFEX"
    # SHFE
    if base in ("CU", "AL", "ZN", "PB", "NI", "SN", "AU", "AG", "RB", "WR", "HC", "BU", "RU", "SP", "FU", "AO", "BR", "SS"):
        return "SHFE"
    # DCE
    if base in ("A", "B", "C", "CS", "EB", "EG", "FB", "I", "J", "JD", "JM", "L", "LH", "M", "P", "PG", "PP", "RR", "V", "Y"):
        return "DCE"
    # CZCE
    if base in ("AP", "CF", "CJ", "CY", "FG", "JR", "LR", "MA", "OI", "PF", "PK", "PM", "RI", "RM", "RS", "SA", "SF", "SM", "SR", "TA", "UR", "WH", "ZC"):
        return "CZCE"
    # INE
    if base in ("SC", "LU", "BC", "NR"):
        return "INE"
    return "CFFEX"


def _get_futures_multiplier(symbol: str) -> int:
    upper = symbol.upper()
    import re
    base = re.sub(r'\d+$', '', upper)
    if base == "IF": return 300
    if base == "IC": return 200
    if base == "IH": return 300
    if base == "IM": return 200
    if base.startswith("T") and base != "TA": return 10000
    if base == "TF": return 10000
    if base == "TS": return 20000
    return 10
