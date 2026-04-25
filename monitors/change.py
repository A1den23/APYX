from __future__ import annotations

from dataclasses import dataclass
from math import isclose

from history import MetricChange


@dataclass(frozen=True)
class ChangeCheckResult:
    breached: bool
    lines: tuple[str, ...]


def exceeds_threshold(value: float, threshold: float) -> bool:
    magnitude = abs(value)
    return magnitude > threshold and not isclose(
        magnitude, threshold, rel_tol=0.0, abs_tol=1e-12
    )


def evaluate_dual_change(
    *,
    latest_change: MetricChange,
    window_change: MetricChange | None,
    pct_threshold: float,
    absolute_threshold: float | None = None,
    absolute_unit: str = "",
    window_label: str = "30m",
) -> ChangeCheckResult:
    lines = [_format_change("1m", latest_change, absolute_unit=absolute_unit)]
    breached = _change_breached(
        latest_change,
        pct_threshold=pct_threshold,
        absolute_threshold=absolute_threshold,
    )
    if window_change is None:
        lines.append(f"{window_label} change: N/A")
    else:
        lines.append(_format_change(window_label, window_change, absolute_unit=absolute_unit))
        breached = breached or _change_breached(
            window_change,
            pct_threshold=pct_threshold,
            absolute_threshold=absolute_threshold,
        )
    return ChangeCheckResult(breached=breached, lines=tuple(lines))


def _change_breached(
    change: MetricChange,
    *,
    pct_threshold: float,
    absolute_threshold: float | None,
) -> bool:
    absolute_change = change.current - change.baseline
    return exceeds_threshold(change.percent, pct_threshold) or (
        absolute_threshold is not None and abs(absolute_change) > absolute_threshold
    )


def _format_change(
    label: str,
    change: MetricChange,
    *,
    absolute_unit: str,
) -> str:
    absolute_change = change.current - change.baseline
    suffix = f" {absolute_unit}" if absolute_unit else ""
    return (
        f"{label} change: {change.percent:+.2%}\n"
        f"{label} absolute change: {absolute_change:+,.2f}{suffix}"
    )
