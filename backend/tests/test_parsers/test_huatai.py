"""Tests for Huatai broker parser."""

from app.parsers.huatai import HuataiParser

SAMPLE_CSV = (
    "成交日期,证券代码,成交价格,成交数量,成交金额,手续费\n"
    "2026-01-05,600519,1500.00,100,150000.00,37.50\n"
    "2026-01-06,600519,1520.00,100,152000.00,38.00\n"
).encode("utf-8")

SAMPLE_VARIANT_CSV = (
    "成交日期,证券代码,成交均价,成交数量,成交金额,手续费\n"
    "2026-01-05,000001,12.50,1000,12500.00,3.13\n"
).encode("utf-8")

SAMPLE_NO_COMMISSION_CSV = (
    "成交日期,证券代码,成交价格,成交数量,成交金额\n"
    "2026-01-05,600519,1500.00,100,150000.00\n"
).encode("utf-8")


def test_huatai_source_type():
    assert HuataiParser.source_type() == "huatai"


def test_huatai_asset_type():
    assert HuataiParser.asset_type() == "stock"


def test_huatai_detect():
    score = HuataiParser.detect(SAMPLE_CSV, "test.csv")
    assert score >= 0.5


def test_huatai_parse():
    trades = HuataiParser.parse(SAMPLE_CSV, "test.csv")
    assert len(trades) == 2
    assert trades[0].symbol == "600519"
    assert trades[0].price == 1500.0
    assert trades[0].exchange == "SH"
    assert trades[0].commission == 37.50


def test_huatai_parse_variant():
    trades = HuataiParser.parse(SAMPLE_VARIANT_CSV, "test.csv")
    assert len(trades) == 1
    assert trades[0].symbol == "000001"
    assert trades[0].price == 12.50
    assert trades[0].exchange == "SZ"


def test_huatai_parse_no_commission():
    trades = HuataiParser.parse(SAMPLE_NO_COMMISSION_CSV, "test.csv")
    assert len(trades) == 1
    assert trades[0].commission == 0.0


def test_huatai_detect_wrong_format():
    score = HuataiParser.detect(b"col1,col2\n1,2", "test.csv")
    assert score < 0.5
