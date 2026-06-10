"""Tests for parser helper functions."""

from app.parsers import _get_exchange, _get_multiplier


def test_get_multiplier():
    assert _get_multiplier("IF2406") == 300
    assert _get_multiplier("IC2406") == 200
    assert _get_multiplier("IH2406") == 300
    assert _get_multiplier("IM2406") == 200
    assert _get_multiplier("T2406") == 10000
    assert _get_multiplier("TF2406") == 10000
    assert _get_multiplier("TS2406") == 20000
    assert _get_multiplier("RB2405") == 10
    assert _get_multiplier("CU2405") == 5
    assert _get_multiplier("AU2406") == 1000
    assert _get_multiplier("AG2406") == 15
    assert _get_multiplier("UNKNOWN") == 10


def test_get_exchange():
    assert _get_exchange("600519") == "SH"
    assert _get_exchange("500000") == "SH"
    assert _get_exchange("900901") == "SH"
    assert _get_exchange("000001") == "SZ"
    assert _get_exchange("300001") == "SZ"
    assert _get_exchange("200001") == "SZ"
    assert _get_exchange("IF2406") == "CFFEX"
    assert _get_exchange("RB2405") == "SHFE"
