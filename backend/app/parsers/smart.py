"""
SmartParser — value-based column classifier.

Instead of matching column NAMES (brittle, broker-specific),
this parser samples the VALUES in each column and uses heuristics
to infer what each column represents (date, symbol, price, quantity, etc.).

Works with virtually any broker's CSV/Excel export without configuration.
"""

import re
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

import pandas as pd

from app.parsers.base import BaseParser, TradeData
from app.parsers import _get_exchange


# ── Futures exchange prefix sets ─────────────────────────────
_FUTURES_PREFIXES = {
    "CFFEX": {"IF", "IC", "IH", "IM"},
    "SHFE": {"CU", "AL", "ZN", "PB", "NI", "SN", "AU", "AG", "RB", "WR", "HC", "BU", "RU", "SP", "FU", "AO", "BR", "SS"},
    "DCE": {"A", "B", "C", "CS", "EB", "EG", "FB", "I", "J", "JD", "JM", "L", "LH", "M", "P", "PG", "PP", "RR", "V", "Y"},
    "CZCE": {"AP", "CF", "CJ", "CY", "FG", "JR", "LR", "MA", "OI", "PF", "PK", "PM", "RI", "RM", "RS", "SA", "SF", "SM", "SR", "TA", "UR", "WH", "ZC"},
    "INE": {"SC", "LU", "BC", "NR"},
}
_FUTURES_MULTIPLIERS = {
    "IF": 300, "IC": 200, "IH": 300, "IM": 200,
    "T": 10000, "TF": 10000, "TS": 20000,
}
_DIRECTION_WORDS = {"买入", "卖出", "买", "卖", "开仓", "平仓", "开", "平", "BUY", "SELL", "LONG", "SHORT", "B", "S"}
_DIRECTION_BUY = {"买入", "买", "买", "开仓", "开", "BUY", "LONG", "B"}
_DIRECTION_SELL = {"卖出", "卖", "平仓", "平", "SELL", "SHORT", "S"}
_COMMISSION_KEYWORDS = {"费", "佣", "税", "commission", "fee"}


def _sample_values(series: pd.Series) -> list:
    """Return up to 20 non-null values from a column."""
    return series.dropna().head(20).tolist()


def _classify_column(name: str, values: list) -> dict[str, float]:
    """Score a column against each semantic type. Returns {type: score}."""
    name_lower = str(name).lower()
    scores = {}

    # ── DATE ────────────────────────────────────────────
    str_values = [str(v) for v in values]
    date_score = 0.0
    date_pattern = re.compile(r'^\d{4}[-/]\d{1,2}[-/]\d{1,2}')  # YYYY-MM-DD or YYYY/MM/DD
    parsed_count = 0
    for v in values:
        sv = str(v).strip()
        # Only consider values that LOOK like dates — avoid false positives on pure numbers
        is_likely_date = bool(date_pattern.match(sv)) or (sv.isdigit() and len(sv) == 8 and sv.startswith(("19", "20")))
        if not is_likely_date:
            continue
        try:
            pd.to_datetime(v)
            parsed_count += 1
        except Exception:
            pass
    date_score = parsed_count / len(values) if values else 0.0
    scores["DATE"] = min(date_score, 1.0)

    # ── SYMBOL (stock) ─────────────────────────────────
    stock_score = 0.0
    for v in str_values:
        v = v.strip().replace("'", "").replace('"', '')
        if re.match(r'^(000|002|003|300|301|600|601|603|605|688|689)\d{3}$', v):
            stock_score += 1.0
        elif re.match(r'^\d{6}$', v):
            stock_score += 0.6
    scores["STOCK_SYMBOL"] = stock_score / len(str_values) if str_values else 0.0

    # ── SYMBOL (futures) ───────────────────────────────
    future_score = 0.0
    for v in str_values:
        v = v.strip().upper().replace("'", "").replace('"', '')
        # Match patterns like IF2401, rb2505, MA310, SC2402, LU202301
        m = re.match(r'^([A-Z]+)(\d{3,6})$', v)
        if m:
            prefix = m.group(1)
            for exchange_prefixes in _FUTURES_PREFIXES.values():
                if prefix in exchange_prefixes:
                    future_score += 1.0
                    break
            else:
                # Unrecognized prefix but still letter+number → probably futures
                future_score += 0.5
    scores["FUTURES_SYMBOL"] = future_score / len(str_values) if str_values else 0.0

    # ── DIRECTION ──────────────────────────────────────
    dir_score = 0.0
    for v in str_values:
        v_upper = v.strip().upper()
        if v.strip() in _DIRECTION_WORDS or v_upper in _DIRECTION_WORDS:
            dir_score += 1.0
        elif any(w in str(v) for w in ["买", "卖", "BUY", "SELL", "开", "平"]):
            dir_score += 0.5
    scores["DIRECTION"] = dir_score / len(str_values) if str_values else 0.0

    # ── NUMERIC columns ────────────────────────────────
    numeric_values = []
    for v in values:
        try:
            numeric_values.append(float(v))
        except (ValueError, TypeError):
            pass

    if not numeric_values:
        return scores

    pos_values = [v for v in numeric_values if v > 0]
    if not pos_values:
        return scores

    avg_val = sum(pos_values) / len(pos_values)
    min_val = min(pos_values)
    max_val = max(pos_values)

    # ── PRICE ──────────────────────────────────────────
    price_score = 0.0
    if 0.01 <= avg_val <= 50000 and min_val > 0:
        distinct = len(set(numeric_values))
        # Prices tend to have many distinct values, commissions repeat
        if distinct >= len(numeric_values) * 0.7:
            price_score += 0.4
        if all(v == int(v) for v in numeric_values):
            price_score -= 0.3  # pure integers → more likely quantity
        # Commission-like: few distinct values, all small → NOT price
        value_range = max_val - min_val
        if max_val < 1000 and distinct < len(numeric_values) * 0.3:
            price_score -= 0.5
        if avg_val < 100:
            price_score += 0.3
        elif avg_val < 10000:
            price_score += 0.2
        scores["PRICE"] = min(max(price_score, 0.0), 1.0)

    # ── QUANTITY ───────────────────────────────────────
    qty_score = 0.0
    if all(v == int(v) for v in numeric_values) and min_val > 0:
        qty_score += 0.4
    # Stock shares: typically multiples of 100
    if all(v >= 100 for v in numeric_values) and all(v % 100 == 0 for v in numeric_values[:10]):
        qty_score += 0.3
    # Futures lots: typically small integers
    if all(v <= 1000 for v in numeric_values) and len(set(numeric_values)) <= len(numeric_values) * 0.8:
        qty_score += 0.2
    scores["QUANTITY"] = min(qty_score, 1.0)

    # ── COMMISSION ─────────────────────────────────────
    comm_score = 0.0
    if avg_val < 1000 and max_val < 10000:
        comm_score += 0.3
    # Commission keywords in column name boost
    if any(kw in name_lower for kw in _COMMISSION_KEYWORDS):
        comm_score += 0.4
    # Commission values are often small
    if avg_val < 100 and max_val < 500:
        comm_score += 0.2
    scores["COMMISSION"] = min(comm_score, 1.0)

    # ── AMOUNT ─────────────────────────────────────────
    amount_score = 0.0
    if max_val > 1000:
        amount_score += 0.3
    if "金额" in name_lower or "成交额" in name_lower or "amount" in name_lower:
        amount_score += 0.4
    scores["AMOUNT"] = min(amount_score, 1.0)

    # ── MARGIN ─────────────────────────────────────────
    margin_score = 0.0
    if "保证金" in name_lower or "保证" in name_lower or "margin" in name_lower:
        margin_score += 0.5
    if max_val > 10000:
        margin_score += 0.3
    scores["MARGIN"] = min(margin_score, 1.0)

    # Cross-penalization: if this column is MORE likely commission than price, penalize PRICE
    if scores.get("COMMISSION", 0) > scores.get("PRICE", 0):
        if "PRICE" in scores:
            scores["PRICE"] *= 0.3
    # If this column looks like amount/notional, it's NOT a price
    if scores.get("AMOUNT", 0) > 0.6 and scores.get("AMOUNT", 0) > scores.get("PRICE", 0):
        if "PRICE" in scores:
            scores["PRICE"] *= 0.3

    return scores


def _get_futures_exchange_smart(symbol: str) -> str:
    """Determine exchange from futures symbol prefix."""
    upper = symbol.upper()
    base = re.sub(r'\d+$', '', upper)
    for exchange, prefixes in _FUTURES_PREFIXES.items():
        if base in prefixes:
            return exchange
    if base.startswith(("T", "TF", "TS")):
        return "CFFEX"
    return "CFFEX"


def _get_futures_multiplier_smart(symbol: str) -> int:
    """Return contract multiplier."""
    upper = symbol.upper()
    base = re.sub(r'\d+$', '', upper)
    return _FUTURES_MULTIPLIERS.get(base, 10)


class SmartParser(BaseParser):
    """Universal parser using value-based column classification.

    Works with any broker's CSV/Excel export without broker-specific configuration.
    Falls back to column name hints only when value heuristics are ambiguous.
    """

    @classmethod
    def source_type(cls) -> str:
        return "smart"

    @classmethod
    def asset_type(cls) -> str:
        return "stock"  # Overridden per-file during detect

    @classmethod
    def detect(cls, content: bytes, filename: str) -> float:
        """Always returns 0.7 — SmartParser is a fallback, not a primary match."""
        try:
            df = cls._read_df(content, filename)
            if len(df.columns) < 3 or len(df) < 1:
                return 0.0
            # We can parse anything with >= 3 columns and >= 1 row
            return 0.75
        except Exception as e:
            logger.warning(f"SmartParser detect failed for {filename}: {e}")
            return 0.0

    @classmethod
    def parse(cls, content: bytes, filename: str) -> list[TradeData]:
        df = cls._read_df(content, filename)
        if df.empty or len(df.columns) < 3:
            return []

        # Classify every column
        column_scores: dict[str, dict[str, float]] = {}
        for col in df.columns:
            values = _sample_values(df[col])
            column_scores[str(col)] = _classify_column(str(col), values)

        # Pick best column for each required field
        def best_col(target_type: str, exclude: set = set()) -> str | None:
            best = None
            best_score = 0.0
            for col, scores in column_scores.items():
                if col in exclude:
                    continue
                s = scores.get(target_type, 0.0)
                if s > best_score:
                    best_score = s
                    best = col
            return best if best_score > 0.3 else None

        date_col = best_col("DATE")

        # Symbol: prefer stock, try futures next — must resolve before price/qty
        stock_col = best_col("STOCK_SYMBOL")
        future_col = best_col("FUTURES_SYMBOL")
        symbol_col = stock_col or future_col

        # Exclude symbol column from price/qty/direction to avoid misclassification
        _non_symbol = {symbol_col} if symbol_col else set()

        direction_col = best_col("DIRECTION", exclude=_non_symbol)
        price_col = best_col("PRICE", exclude=_non_symbol)
        qty_col = best_col("QUANTITY", exclude=_non_symbol)

        # Asset type determined by which symbol column scored higher
        stock_score = column_scores.get(stock_col or "", {}).get("STOCK_SYMBOL", 0)
        future_score = column_scores.get(future_col or "", {}).get("FUTURES_SYMBOL", 0)
        is_future = future_score > stock_score and future_score > 0.3

        # Find ALL commission/fee columns (佣金, 印花税, 过户费, 其他杂费 etc.)
        # Exclude: price columns (PRICE > COMMISSION) and serial/ID columns (high QUANTITY).
        # The QUANTITY guard's job is to drop serial/ID columns; a column whose NAME
        # carries a fee keyword (费/佣/税) is a genuine fee column even when its values
        # are small integers (e.g. 手续费 = 5.00 looks quantity-like), so skip the guard
        # for those — otherwise broker commission is silently dropped from PnL.
        _id_keywords = ["序号", "编号", "成交编号", "委托编号", "合同编号", "股东代码"]
        comm_cols = [
            col for col, scores in column_scores.items()
            if scores.get("COMMISSION", 0) > 0.3
            and scores.get("PRICE", 0) < scores.get("COMMISSION", 0)
            and not any(kw in str(col).lower() for kw in _id_keywords)
            and (
                scores.get("QUANTITY", 0) < 0.45
                or any(kw in str(col).lower() for kw in _COMMISSION_KEYWORDS)
            )
        ]
        margin_col = best_col("MARGIN") if is_future else None

        if not all([date_col, symbol_col, direction_col, price_col, qty_col]):
            # Fall back: try amount column as quantity proxy
            amount_col = best_col("AMOUNT")
            if amount_col and not qty_col:
                qty_col = amount_col
            if not all([date_col, symbol_col, direction_col, price_col, qty_col]):
                return []

        trades: list[TradeData] = []
        skipped = 0
        total = len(df)
        for _, row in df.iterrows():
            try:
                symbol = str(row[symbol_col]).strip().replace("'", "").replace('"', '')
                if is_future:
                    exchange = _get_futures_exchange_smart(symbol)
                else:
                    symbol = symbol.zfill(6)
                    exchange = _get_exchange(symbol)

                raw_dir = str(row[direction_col]).strip()
                raw_dir_upper = raw_dir.upper()
                dir_str = str(row[direction_col])

                # First check exact set matches
                if raw_dir_upper in _DIRECTION_BUY:
                    side = "BUY"
                elif raw_dir_upper in _DIRECTION_SELL:
                    side = "SELL"
                else:
                    # Then check for meaningful substrings (avoid single "开"/"平" that could be part of either)
                    has_buy = "买入" in dir_str or "买" in dir_str
                    has_sell = "卖出" in dir_str or "卖" in dir_str
                    has_open = "开仓" in dir_str
                    has_close = "平仓" in dir_str

                    if has_buy or (has_open and not has_sell and not has_close):
                        side = "BUY"
                    elif has_sell or (has_close and not has_buy and not has_open):
                        side = "SELL"
                    else:
                        # Can't determine direction reliably, skip this row
                        skipped += 1
                        continue

                qty = float(row[qty_col])
                price = float(row[price_col])

                if is_future:
                    exchange = _get_futures_exchange_smart(symbol)
                    multiplier = _get_futures_multiplier_smart(symbol)
                else:
                    exchange = _get_exchange(symbol)
                    multiplier = None

                comm = 0.0
                for c in comm_cols:
                    val = row.get(c)
                    if pd.notna(val):
                        try:
                            comm += float(val)
                        except (ValueError, TypeError):
                            pass

                margin = None
                if margin_col and pd.notna(row.get(margin_col)):
                    margin = float(row[margin_col])

                trades.append(TradeData(
                    datetime=pd.to_datetime(row[date_col]),
                    symbol=symbol,
                    exchange=exchange,
                    side=side,
                    quantity=qty,
                    price=price,
                    commission=comm,
                    margin=margin,
                    multiplier=multiplier,
                    asset_type="future" if is_future else "stock",
                ))
            except (ValueError, KeyError, TypeError):
                skipped += 1
                continue

        # Warn if >5% rows were skipped
        if total > 0 and skipped / total > 0.05:
            logger.warning(f"SmartParser skipped {skipped}/{total} rows ({skipped/total:.1%}) for {filename}")

        return trades
