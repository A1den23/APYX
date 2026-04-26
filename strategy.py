from __future__ import annotations

from pathlib import Path


STRATEGY_PATH = Path("docs/monitoring-strategy.md")


def build_strategy_message(path: str | Path = STRATEGY_PATH) -> str:
    return Path(path).read_text(encoding="utf-8")
