"""Tests for Citic broker parser."""

from app.parsers.citic import CiticParser

SAMPLE_CSV = (
    "成交日期,证券代码,成交价格,成交数量,成交金额,手续费\n"
    "2026-01-05,600519,1500.00,100,150000.00,37.50\n"
    "2026-01-06,600519,1520.00,100,152000.00,38.00\n"
).encode("utf-8")

SAMPLE_VARIANT = (
    "成交日期,代码,成交价格,成交数量,成交金额,手续费\n"
    "2026-01-05,000001,12.50,1000,12500.00,3.13\n"
).encode("utf-8")


def test_citic_source_type():
    assert CiticParser.source_type() == "broker"


def test_citic_asset_type():
    assert CiticParser.asset_type() == "stock"


def test_citic_detect():
    score = CiticParser.detect(SAMPLE_CSV, "test.csv")
    assert score >= 0.7


def test_citic_parse():
    trades = CiticParser.parse(SAMPLE_CSV, "test.csv")
    assert len(trades) == 2
    assert trades[0].symbol == "600519"
    assert trades[0].price == 1500.0
    assert trades[0].exchange == "SH"
    assert trades[0].commission == 37.50


def test_citic_parse_variant():
    trades = CiticParser.parse(SAMPLE_VARIANT, "test.csv")
    assert len(trades) == 1
    assert trades[0].symbol == "000001"
    assert trades[0].price == 12.50
    assert trades[0].exchange == "SZ"


def test_citic_detect_wrong_format():
    score = CiticParser.detect(b"col1,col2\n1,2", "test.csv")
    assert score < 0.5
