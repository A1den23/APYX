from pathlib import Path


def test_docker_context_includes_strategy_document() -> None:
    patterns = {
        line.strip()
        for line in Path(".dockerignore").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    }

    assert "docs" not in patterns
    assert "docs/" not in patterns
