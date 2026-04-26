from __future__ import annotations

from config import AppConfig


def build_thresholds_message(settings: AppConfig) -> str:
    supply_thresholds = {
        token.name: token.absolute_change_threshold for token in settings.supply.tokens
    }
    apxusd_supply_abs = supply_thresholds.get("apxUSD", 0.0)
    apyusd_supply_abs = supply_thresholds.get("apyUSD", 0.0)

    return "\n".join(
        [
            "📏 APYX Monitor Thresholds",
            "",
            "🌐 宏观风险",
            f"  STRC price < ${settings.finnhub.threshold_price:.2f}",
            "",
            "📈 Pendle 市场",
            f"  liquidity: 30m ↓{settings.pendle.liquidity_drop_pct:.0%}",
            f"  implied APY: 30m ±{settings.pendle.apy_change_pct:.0%}",
            f"  PT price: 30m ±{settings.pendle.pt_price_change_pct:.0%}",
            "",
            "🔐 协议安全",
            "  Accountable PoR:",
            f"    ratio < {settings.solvency.warning_collateralization:.1%} 预警",
            f"    ratio < {settings.solvency.critical_collateralization:.0%} 紧急",
            f"    updated > {settings.solvency.max_data_age_minutes}min 预警",
            f"  apxUSD price: 偏离 > {settings.peg.threshold_pct:.2%}",
            (
                f"  apxUSD totalSupply: 1m/30m ±{settings.supply.threshold_pct:.0%} "
                f"或 ±{apxusd_supply_abs/1e6:.2f}M"
            ),
            (
                f"  apyUSD totalSupply: 1m/30m ±{settings.supply.threshold_pct:.0%} "
                f"或 ±{apyusd_supply_abs/1e6:.2f}M shares"
            ),
            (
                f"  apyUSD totalAssets: 1m/30m ±{settings.apyusd.total_assets_change_pct:.0%} "
                f"或 ±{settings.apyusd.total_assets_absolute_change_threshold/1e6:.2f}M apxUSD"
            ),
            f"  apyUSD priceAPXUSD: 1m/30m ±{settings.apyusd.price_apxusd_change_pct:.0%}",
            (
                f"  mint backing: share增量 > "
                f"{settings.security.apyusd_min_supply_increase/1e6:.2f}M "
                f"且背书 < {settings.security.apyusd_min_backing_ratio:.0%}"
            ),
            "  security events: 大额mint/burn、权限、升级、暂停",
        ]
    )
