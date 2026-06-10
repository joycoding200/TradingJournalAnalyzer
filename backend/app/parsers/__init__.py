"""Parser helpers."""


def _get_multiplier(symbol: str) -> int:
    """Get contract multiplier for futures symbols."""
    symbol_upper = symbol.upper()
    if symbol_upper.startswith("IF"):
        return 300
    if symbol_upper.startswith("IC"):
        return 200
    if symbol_upper.startswith("IH"):
        return 300
    if symbol_upper.startswith("IM"):
        return 200
    if symbol_upper.startswith("TS"):
        return 20000
    if symbol_upper.startswith("T"):
        return 10000
    if symbol_upper.startswith("TF"):
        return 10000
    if any(symbol_upper.startswith(p) for p in ("RB", "HC", "BU", "RU", "SP", "FU")):
        return 10
    if any(symbol_upper.startswith(p) for p in ("CU", "AL", "ZN", "PB", "NI", "SN", "AO")):
        return 5
    if symbol_upper.startswith("AU"):
        return 1000
    if symbol_upper.startswith("AG"):
        return 15
    return 10


def _get_exchange(symbol: str) -> str:
    """Get exchange code from stock/futures symbol."""
    sym = symbol.zfill(6)
    if sym[0] in ("6", "5", "9"):
        return "SH"
    if sym[0] in ("0", "3", "2"):
        return "SZ"
    # Futures exchanges
    upper = symbol.upper()
    if any(upper.startswith(p) for p in ("IF", "IC", "IH", "IM", "T", "TF", "TS")):
        return "CFFEX"
    if any(upper.startswith(p) for p in ("CU", "AL", "ZN", "PB", "NI", "SN", "AO",
                                          "AU", "AG", "RB", "HC", "BU", "RU", "SP", "FU", "WR",
                                          "SS", "BR")):
        return "SHFE"
    return "DCE"  # Default for futures


def _find_col(col_map: dict[str, str], candidates: list[str]) -> str | None:
    """Find first matching column from candidates in the column map.

    Args:
        col_map: Mapping from lowercase column name to actual column name.
        candidates: List of possible column names to find.

    Returns:
        Actual column name if found, None otherwise.
    """
    for c in candidates:
        c_lower = c.strip().lower()
        if c_lower in col_map:
            return col_map[c_lower]
    return None
