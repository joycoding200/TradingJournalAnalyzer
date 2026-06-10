"""Tests for DFCF (东方财富) stock parser."""

from app.parsers.dfcf import DfcfParser

SAMPLE_CSV = (
    "成交日期,证券代码,操作,成交均价,成交数量,成交金额,手续费\n"
    "2026-01-05,600519,买入,1500.00,100,150000.00,37.50\n"
    "2026-01-06,600519,卖出,1520.00,100,152000.00,38.00\n"
).encode("utf-8")


def test_dfcf_source_type():
    assert DfcfParser.source_type() == "dfcf"


def test_dfcf_asset_type():
    assert DfcfParser.asset_type() == "stock"


def test_dfcf_detect():
    score = DfcfParser.detect(SAMPLE_CSV, "test.csv")
    assert score >= 0.8


def test_dfcf_parse():
    trades = DfcfParser.parse(SAMPLE_CSV, "test.csv")
    assert len(trades) == 2
    assert trades[0].side == "BUY"
    assert trades[0].symbol == "600519"
    assert trades[0].exchange == "SH"
    assert trades[1].side == "SELL"
    assert trades[1].symbol == "600519"


def test_dfcf_detect_wrong_format():
    score = DfcfParser.detect(b"col1,col2\n1,2", "test.csv")
    assert score < 0.5


def test_dfcf_parse_empty():
    csv_data = "成交日期,证券代码,操作,成交均价,成交数量\n".encode("utf-8")
    trades = DfcfParser.parse(csv_data, "test.csv")
    assert len(trades) == 0
