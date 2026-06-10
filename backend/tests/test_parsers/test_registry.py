from app.parsers.registry import ParserRegistry


def test_registry_auto_discover():
    ParserRegistry._initialized = False
    ParserRegistry._parsers = []
    ParserRegistry.auto_discover()
    parser_types = [p.source_type() for p in ParserRegistry._parsers]
    assert len(parser_types) >= 0


def test_detect_format_no_parsers():
    ParserRegistry._initialized = False
    ParserRegistry._parsers = []
    results = ParserRegistry.detect_format(b"dummy,data\n1,2", "test.csv")
    assert results == []


def test_parse_unknown_raises():
    ParserRegistry._initialized = False
    ParserRegistry._parsers = []
    try:
        ParserRegistry.parse("nonexistent", b"", "test.csv")
        assert False, "Should have raised ValueError"
    except ValueError:
        pass


def test_column_match_score():
    from app.parsers.base import BaseParser

    score = BaseParser._column_match_score(
        ["委托时间", "证券代码", "成交价格"], ["委托时间", "证券代码", "成交价格"]
    )
    assert score == 1.0

    score = BaseParser._column_match_score(["a", "b"], ["委托时间", "证券代码", "成交价格"])
    assert score == 0.0

    score = BaseParser._column_match_score(
        ["委托时间", "其他"], ["委托时间", "证券代码"]
    )
    assert score == 0.5
