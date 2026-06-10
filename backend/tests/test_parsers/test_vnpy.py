"""Tests for VNPY stock parser."""

from app.parsers.vnpy import VnpyParser

SAMPLE_CSV = (
    "datetime,symbol,direction,price,volume,commission\n"
    "2026-03-15 09:30:00,600519,LONG,1500.00,100,37.50\n"
    "2026-03-15 14:00:00,600519,SHORT,1520.00,100,38.00\n"
).encode("utf-8")

SAMPLE_BUY_VARIANTS = (
    "datetime,symbol,direction,price,volume\n"
    "2026-03-15 09:30:00,000001,BUY,12.50,1000\n"
    "2026-03-15 09:31:00,000002,LONG,15.00,500\n"
).encode("utf-8")


def test_vnpy_source_type():
    assert VnpyParser.source_type() == "vnpy"


def test_vnpy_asset_type():
    assert VnpyParser.asset_type() == "stock"


def test_vnpy_detect():
    score = VnpyParser.detect(SAMPLE_CSV, "test.csv")
    assert score >= 0.8


def test_vnpy_parse():
    trades = VnpyParser.parse(SAMPLE_CSV, "test.csv")
    assert len(trades) == 2

    assert trades[0].symbol == "600519"
    assert trades[0].side == "BUY"
    assert trades[0].price == 1500.0
    assert trades[0].quantity == 100
    assert trades[0].exchange == "SH"

    assert trades[1].symbol == "600519"
    assert trades[1].side == "SELL"
    assert trades[1].price == 1520.0
    assert trades[1].quantity == 100
    assert trades[1].exchange == "SH"


def test_vnpy_parse_buy_variants():
    trades = VnpyParser.parse(SAMPLE_BUY_VARIANTS, "test.csv")
    assert len(trades) == 2
    assert trades[0].side == "BUY"
    assert trades[1].side == "BUY"


def test_vnpy_detect_wrong_format():
    score = VnpyParser.detect(b"col1,col2\n1,2", "test.csv")
    assert score < 0.5


def test_vnpy_parse_empty():
    csv_data = "datetime,symbol,direction,price,volume\n".encode("utf-8")
    trades = VnpyParser.parse(csv_data, "test.csv")
    assert len(trades) == 0
