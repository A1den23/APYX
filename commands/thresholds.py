from __future__ import annotations

from app.config import AppConfig


def build_thresholds_message(settings: AppConfig) -> str:
    supply_thresholds = {
        token.name: token.absolute_change_threshold for token in settings.supply.tokens
    }
    apxusd_supply_abs = supply_thresholds.get("apxUSD", 0.0)
    apyusd_supply_abs = supply_thresholds.get("apyUSD", 0.0)

    lines = [
        "📏 APYX Monitor Thresholds",
        "",
        "🌐 宏观风险",
    ]
    for symbol in settings.finnhub.symbols:
        lines.append(f"  {symbol.symbol} price < ${symbol.threshold_price:.2f}")

    lines.extend(
        [
            "",
            "📈 Pendle 市场",
            f"  liquidity: 30m ↓{settings.pendle.liquidity_drop_pct:.0%}",
            f"  implied APY: 30m ±{settings.pendle.apy_change_pct:.0%}",
            f"  PT price: 30m ±{settings.pendle.pt_price_change_pct:.0%}",
            "",
            "💧 Curve 池",
            f"  balance: 30m ↓{settings.curve.balance_drop_pct:.0%}",
            f"  total value: 30m ↓{settings.curve.balance_drop_pct:.0%}",
            f"  imbalance > {settings.curve.imbalance_pct:.0%}",
            f"  value-adjusted imbalance > {settings.curve.imbalance_pct:.0%}",
            f"  virtual price: 30m ±{settings.curve.virtual_price_change_pct:.0%}",
            f"  apxUSD/USDC price: 偏离 > {settings.curve.price_deviation_pct:.2%}",
            "  apyUSD/apxUSD price: 相对 vault priceAPXUSD 偏离 > 0.50%",
            "",
            "🔒 Commit / Unlock",
            f"  cap usage > {settings.commit.cap_usage_warning_pct:.0%}",
            (
                f"  totalAssets: 1m/30m ±{settings.commit.assets_change_pct:.0%} "
                "或 token 配置绝对阈值"
            ),
            *[
                f"    {token.name}: ±{token.absolute_change_threshold/1e6:.2f}M"
                for token in settings.commit.tokens
            ],
            "  unlocking delay: 任意变化",
            "",
            "🌾 收益分发",
            (
                "  annualized yield: "
                f"30m ±{settings.yield_distribution.annualized_yield_change_pct:.0%}"
            ),
            f"  APY: 30m ±{settings.yield_distribution.apy_change_pct:.0%}",
            f"  unvested yield: 30m ±{settings.yield_distribution.unvested_change_pct:.0%}",
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
            "  security events: 大额mint/burn、权限、升级、暂停、AccessManager、协议参数变更",
        ]
    )
    return "\n".join(lines)
