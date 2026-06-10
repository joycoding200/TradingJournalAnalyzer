"""Tests for THS (同花顺) stock parser."""

from app.parsers.ths import ThsParser

SAMPLE_CSV = (
    "发生日期,证券代码,买卖标志,成交价格,成交数量,成交金额,手续费\n"
    "2026-01-05,600519,买,1500.00,100,150000.00,37.50\n"
    "2026-01-06,600519,卖,1520.00,100,152000.00,38.00\n"
).encode("utf-8")


def test_ths_source_type():
    assert ThsParser.source_type() == "ths"


def test_ths_asset_type():
    assert ThsParser.asset_type() == "stock"


def test_ths_detect():
    score = ThsParser.detect(SAMPLE_CSV, "test.csv")
    assert score >= 0.8


def test_ths_parse():
    trades = ThsParser.parse(SAMPLE_CSV, "test.csv")
    assert len(trades) == 2
    assert trades[0].side == "BUY"
    assert trades[0].symbol == "600519"
    assert trades[0].exchange == "SH"
    assert trades[1].side == "SELL"
    assert trades[1].symbol == "600519"


def test_ths_detect_wrong_format():
    score = ThsParser.detect(b"col1,col2\n1,2", "test.csv")
    assert score < 0.5


def test_ths_parse_empty():
    csv_data = "发生日期,证券代码,买卖标志,成交价格,成交数量\n".encode("utf-8")
    trades = ThsParser.parse(csv_data, "test.csv")
    assert len(trades) == 0
