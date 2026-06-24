"""Load pattern definitions from pattern_definition.yaml (single source of truth).

Data is loaded lazily on first access so a missing/malformed YAML file does not
prevent the application from starting — only endpoints that actually need pattern
definitions will fail with a clear error.
"""

from pathlib import Path
import yaml

_yaml_path = Path(__file__).parent.parent.parent.parent / "pattern_definition.yaml"
_data: dict | None = None


def _load() -> dict:
    global _data
    if _data is None:
        with open(_yaml_path, "r", encoding="utf-8") as f:
            _data = yaml.safe_load(f)
    return _data


def _patterns() -> list[dict]:
    return _load()["patterns"]


# Lookup helpers — callable properties so they always read fresh data
# (though in practice the YAML doesn't change at runtime).

def PATTERNS() -> list[dict]:
    return _patterns()


def PATTERN_NAMES() -> list[str]:
    return [p["name"] for p in _patterns()]


def LABEL_MAP() -> dict[str, str]:
    return {p["name"]: p["label"] for p in _patterns()}


def NAME_MAP() -> dict[str, str]:
    return {p["label"]: p["name"] for p in _patterns()}


def MODULE_MAP() -> dict[str, str]:
    return {p["name"]: p["module"] for p in _patterns()}


def MARKET_DEPENDENT() -> set[str]:
    return {p["name"] for p in _patterns() if p["market_dependent"]}


def NON_MARKET() -> set[str]:
    return {p["name"] for p in _patterns() if not p["market_dependent"]}


def DEFAULT_CONFIDENCE() -> dict[str, float]:
    return {p["name"]: p["confidence"] for p in _patterns()}


def label(name: str) -> str:
    """Get Chinese label for a pattern name."""
    return LABEL_MAP().get(name, name)


def name(label_str: str) -> str:
    """Get pattern name from Chinese label."""
    return NAME_MAP().get(label_str, label_str)
