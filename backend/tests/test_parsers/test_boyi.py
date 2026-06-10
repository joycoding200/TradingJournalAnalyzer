"""Tests for Boyi futures parser."""

from app.parsers.boyi import BoyiParser

SAMPLE_CSV = (
    "成交日期,合约,买卖,成交价,手数,成交金额,手续费\n"
    "2026-01-05,RB2405,买,3800.00,5,190000.00,19.00\n"
    "2026-01-06,RB2405,卖,3850.00,3,115500.00,11.55\n"
).encode("utf-8")


def test_boyi_source_type():
    assert BoyiParser.source_type() == "boyi"


def test_boyi_asset_type():
    assert BoyiParser.asset_type() == "future"


def test_boyi_detect():
    score = BoyiParser.detect(SAMPLE_CSV, "test.csv")
    assert score >= 0.8


def test_boyi_parse():
    trades = BoyiParser.parse(SAMPLE_CSV, "test.csv")
    assert len(trades) == 2
    assert trades[0].side == "BUY"
    assert trades[0].symbol == "RB2405"
    assert trades[0].quantity == 5
    assert trades[0].price == 3800.0
    assert trades[0].multiplier == 10
    assert trades[1].side == "SELL"
    assert trades[1].symbol == "RB2405"
    assert trades[1].quantity == 3


def test_boyi_detect_wrong_format():
    score = BoyiParser.detect(b"col1,col2\n1,2", "test.csv")
    assert score < 0.5


def test_boyi_parse_empty():
    csv_data = "成交日期,合约,买卖,成交价,手数\n".encode("utf-8")
    trades = BoyiParser.parse(csv_data, "test.csv")
    assert len(trades) == 0
