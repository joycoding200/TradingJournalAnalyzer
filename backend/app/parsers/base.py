import csv
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from io import BytesIO, StringIO

import pandas as pd


# Excel text-protection wrapper that brokers (e.g. 中信证券) emit so leading
# zeros / numeric-looking codes are preserved as text: ="002471", ="20260331".
# Matches the full literal form (including the surrounding double quotes).
_FORMULA_STRING_RE = re.compile(r'^="(.*)"$', re.DOTALL)


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
    id: str | None = None  # populated from DB record when available
    asset_type: str = "stock"  # "stock" or "future"


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
    def _decode_text(content: bytes) -> str:
        """Decode bytes to text, trying common Chinese encodings after UTF-8."""
        for enc in ("utf-8-sig", "utf-8", "gb18030", "gbk", "latin-1"):
            try:
                return content.decode(enc)
            except UnicodeDecodeError:
                continue
        return content.decode("utf-8", errors="replace")

    @staticmethod
    def _detect_delimiter(text: str) -> str:
        """Pick the delimiter (tab/comma/semicolon) with the highest count in
        the first non-empty line."""
        first_line = ""
        for line in text.splitlines():
            if line.strip():
                first_line = line
                break
        counts = {d: first_line.count(d) for d in ("\t", ",", ";", "|")}
        delim, n = max(counts.items(), key=lambda kv: kv[1])
        return delim if n > 0 else ","

    @staticmethod
    def _strip_formula_strings(df: pd.DataFrame) -> pd.DataFrame:
        """Remove the Excel ='...' text-protection wrapper from object columns.

        Brokers like 中信证券 export every cell as ="..." so codes keep leading
        zeros. Left in place, this breaks value-based column classification
        (symbol/date/price heuristics all see the leading =")."""
        def _clean(v):
            if isinstance(v, str):
                m = _FORMULA_STRING_RE.match(v)
                if m:
                    return m.group(1)
            return v

        # Apply to every column — _clean is a no-op for non-string cells, so we
        # don't have to reason about object-vs-StringDtype differences.
        for col in df.columns:
            df[col] = df[col].map(_clean)
        return df

    @staticmethod
    def _read_delimited(content: bytes) -> pd.DataFrame:
        """Read a delimited text file (TSV/CSV/...), auto-detecting encoding
        and delimiter. Used both for .csv and for .xls files that are really
        text in disguise (a common broker export quirk)."""
        text = BaseParser._decode_text(content)
        delim = BaseParser._detect_delimiter(text)
        # QUOTE_NONE keeps ="..." literals intact instead of letting pandas
        # treat the embedded quotes as CSV quoting; we strip the wrapper after.
        for header_row in range(4):
            df = pd.read_csv(
                StringIO(text),
                sep=delim,
                engine="python",
                quoting=csv.QUOTE_NONE,
                header=header_row,
                dtype=str,
            )
            unnamed_count = sum(1 for c in df.columns if str(c).startswith("Unnamed"))
            if unnamed_count < len(df.columns) * 0.6:
                return df
        return df

    @staticmethod
    def _read_df(content: bytes, filename: str) -> pd.DataFrame:
        if filename.lower().endswith(".csv"):
            return BaseParser._strip_formula_strings(BaseParser._read_delimited(content))
        elif filename.lower().endswith((".xls", ".xlsx")):
            # Try as a real Excel workbook first.
            try:
                for header_row in range(4):
                    df = pd.read_excel(BytesIO(content), header=header_row)
                    unnamed_count = sum(1 for c in df.columns if str(c).startswith("Unnamed"))
                    if unnamed_count < len(df.columns) * 0.6:
                        return BaseParser._strip_formula_strings(df)
                return BaseParser._strip_formula_strings(df)
            except Exception:
                # Not a real Excel file — many brokers export a tab/comma
                # text file with a .xls extension. Fall back to delimited text.
                return BaseParser._strip_formula_strings(BaseParser._read_delimited(content))
        raise ValueError(f"Unsupported file format: {filename}")

    @staticmethod
    def _column_match_score(df_columns: list[str], expected: list[str]) -> float:
        actual_lower = {c.strip().lower(): c for c in df_columns}
        matched = 0
        for exp in expected:
            if exp.lower() in actual_lower:
                matched += 1
        return matched / len(expected) if expected else 0.0
