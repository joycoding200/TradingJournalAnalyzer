import importlib
import pkgutil
from pathlib import Path

from app.parsers.base import BaseParser, TradeData


class ParserRegistry:
    _parsers: list[type[BaseParser]] = []
    _initialized: bool = False

    @classmethod
    def auto_discover(cls):
        if cls._initialized:
            return
        parsers_dir = Path(__file__).parent
        for _, name, _ in pkgutil.iter_modules([str(parsers_dir)]):
            if name in ("base", "registry", "__init__"):
                continue
            importlib.import_module(f"app.parsers.{name}")
        cls._parsers = BaseParser.__subclasses__()
        cls._initialized = True

    @classmethod
    def detect_format(cls, content: bytes, filename: str) -> list[tuple[str, str, float]]:
        cls.auto_discover()
        results = []
        for parser_cls in cls._parsers:
            try:
                score = parser_cls.detect(content, filename)
                if score > 0:
                    results.append((parser_cls.source_type(), parser_cls.asset_type(), score))
            except Exception:
                continue
        results.sort(key=lambda x: x[2], reverse=True)
        return results

    @classmethod
    def get_parser(cls, source_type: str) -> type[BaseParser] | None:
        cls.auto_discover()
        for parser_cls in cls._parsers:
            if parser_cls.source_type() == source_type:
                return parser_cls
        return None

    @classmethod
    def parse(cls, source_type: str, content: bytes, filename: str) -> list[TradeData]:
        parser_cls = cls.get_parser(source_type)
        if not parser_cls:
            raise ValueError(f"Unknown source type: {source_type}")
        return parser_cls.parse(content, filename)
