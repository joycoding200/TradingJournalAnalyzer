"""Tests for Wenhua futures parser."""

from app.parsers.wenhua import WenhuaParser

SAMPLE_CSV = (
    "开平,合约,手数,成交价,成交额,手续费\n"
    "开,IF2406,2,3500.00,2100000.00,35.00\n"
    "平,IF2406,1,3520.00,1056000.00,17.60\n"
).encode("utf-8")


def test_wenhua_source_type():
    assert WenhuaParser.source_type() == "wenhua"


def test_wenhua_asset_type():
    assert WenhuaParser.asset_type() == "future"


def test_wenhua_detect():
    score = WenhuaParser.detect(SAMPLE_CSV, "test.csv")
    assert score >= 0.8


def test_wenhua_parse():
    trades = WenhuaParser.parse(SAMPLE_CSV, "test.csv")
    assert len(trades) == 2

    assert trades[0].side == "BUY"
    assert trades[0].symbol == "IF2406"
    assert trades[0].quantity == 2
    assert trades[0].price == 3500.0
    assert trades[0].multiplier == 300
    assert trades[0].margin is not None
    assert trades[0].exchange == "CFFEX"

    assert trades[1].side == "SELL"
    assert trades[1].symbol == "IF2406"
    assert trades[1].quantity == 1
    assert trades[1].price == 3520.0
    assert trades[1].multiplier == 300


def test_wenhua_parse_buy_sell_variants():
    csv_data = (
        "开平,合约,手数,成交价\n"
        "买,AG2406,1,6000.00\n"
        "卖,AG2408,2,6100.00\n"
    ).encode("utf-8")
    trades = WenhuaParser.parse(csv_data, "test.csv")
    assert len(trades) == 2
    assert trades[0].side == "BUY"
    assert trades[1].side == "SELL"
    assert trades[0].multiplier == 15


def test_wenhua_detect_wrong_format():
    score = WenhuaParser.detect(b"col1,col2\n1,2", "test.csv")
    assert score < 0.5


def test_wenhua_parse_empty():
    csv_data = "开平,合约,手数,成交价\n".encode("utf-8")
    trades = WenhuaParser.parse(csv_data, "test.csv")
    assert len(trades) == 0
