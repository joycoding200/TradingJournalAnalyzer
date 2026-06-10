"""Tests for CTP futures parser."""

from app.parsers.ctp import CTPParser

SAMPLE_CSV = (
    "交易日,合约代码,买卖,成交量,成交价,成交金额,手续费\n"
    "2026-01-05,AU2406,买,2,480.00,960000.00,48.00\n"
    "2026-01-06,AU2406,卖,1,485.00,485000.00,24.25\n"
).encode("utf-8")


def test_ctp_source_type():
    assert CTPParser.source_type() == "ctp"


def test_ctp_asset_type():
    assert CTPParser.asset_type() == "future"


def test_ctp_detect():
    score = CTPParser.detect(SAMPLE_CSV, "test.csv")
    assert score >= 0.8


def test_ctp_parse():
    trades = CTPParser.parse(SAMPLE_CSV, "test.csv")
    assert len(trades) == 2
    assert trades[0].side == "BUY"
    assert trades[0].symbol == "AU2406"
    assert trades[0].quantity == 2
    assert trades[0].price == 480.0
    assert trades[0].multiplier == 1000
    assert trades[1].side == "SELL"
    assert trades[1].symbol == "AU2406"
    assert trades[1].quantity == 1


def test_ctp_detect_wrong_format():
    score = CTPParser.detect(b"col1,col2\n1,2", "test.csv")
    assert score < 0.5


def test_ctp_parse_empty():
    csv_data = "交易日,合约代码,买卖,成交量,成交价\n".encode("utf-8")
    trades = CTPParser.parse(csv_data, "test.csv")
    assert len(trades) == 0
