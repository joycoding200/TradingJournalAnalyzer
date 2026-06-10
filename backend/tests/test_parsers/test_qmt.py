"""Tests for QMT stock parser."""

from app.parsers.qmt import QMTParser

SAMPLE_CSV = (
    "委托时间,证券代码,买卖方向,成交价格,成交数量,成交金额,手续费\n"
    "2026-01-05 09:35:00,600519,买入,1500.00,100,150000.00,37.50\n"
    "2026-01-06 14:20:00,600519,卖出,1520.00,100,152000.00,38.00\n"
).encode("utf-8")

SAMPLE_CSV_SZ = (
    "委托时间,证券代码,买卖方向,成交价格,成交数量,成交金额,手续费\n"
    "2026-01-05 09:35:00,000001,买入,12.50,1000,12500.00,3.13\n"
).encode("utf-8")


def test_qmt_source_type():
    assert QMTParser.source_type() == "qmt"


def test_qmt_asset_type():
    assert QMTParser.asset_type() == "stock"


def test_qmt_detect():
    score = QMTParser.detect(SAMPLE_CSV, "test.csv")
    assert score >= 0.8


def test_qmt_parse():
    trades = QMTParser.parse(SAMPLE_CSV, "test.csv")
    assert len(trades) == 2

    assert trades[0].symbol == "600519"
    assert trades[0].side == "BUY"
    assert trades[0].price == 1500.0
    assert trades[0].quantity == 100
    assert trades[0].exchange == "SH"
    assert trades[0].commission == 37.50

    assert trades[1].symbol == "600519"
    assert trades[1].side == "SELL"
    assert trades[1].price == 1520.0
    assert trades[1].quantity == 100
    assert trades[1].exchange == "SH"


def test_qmt_parse_sz():
    trades = QMTParser.parse(SAMPLE_CSV_SZ, "test.csv")
    assert len(trades) == 1
    assert trades[0].symbol == "000001"
    assert trades[0].exchange == "SZ"


def test_qmt_detect_wrong_format():
    score = QMTParser.detect(b"col1,col2\n1,2", "test.csv")
    assert score < 0.5


def test_qmt_detect_empty():
    score = QMTParser.detect(b"", "test.csv")
    assert score < 0.5


def test_qmt_parse_empty():
    csv_data = "委托时间,证券代码,买卖方向,成交价格,成交数量,成交金额,手续费\n".encode("utf-8")
    trades = QMTParser.parse(csv_data, "test.csv")
    assert len(trades) == 0
