# APYX Monitor Strategy

📋 监控策略说明

APYX 稳定币与 DeFi 市场安全监控
stablecoin-safety · ETHEREUM · apxUSD / apyUSD

## 核心目标

监控 apxUSD / apyUSD 的价格、供应、背书、PoR、权限事件和主要市场流动性。重点捕捉三类风险：

• 稳定币脱锚、储备不足或数据失效
• apyUSD share 增发但底层资产未同步增加
• Pendle / Morpho / Curve 等主要市场流动性快速下降、oracle 价格异常或利率异常

## 人工介入标准

出现以下任一情况，应人工确认并按风险等级处理：

• Accountable PoR 偿付率 `<100%`，或 `<100.1%` 且持续恶化
• PoR 数据超过 `30min` 未更新
• apxUSD 价格偏离 `$1.00` 超过 `0.30%`
• apxUSD / apyUSD 供应量 `1m/30m` 变化超过 `10%`，或超过绝对阈值
• apyUSD 新增 share 超过 `100K` 且底层资产背书 `<99%`
• Pendle / Morpho / Curve 主要流动性或价格指标触发阈值
• CommitToken cap、资产或解锁延迟异常
• 收益分发 APY、年化收益资产量或未归属收益异常
• 任意被监控合约出现权限、升级、暂停或协议参数事件

## 监控策略

| 模块 | 频率 | 触发条件 |
|------|------|----------|
| Accountable PoR | 5min | 偿付率 `<100.1%` 预警；`<100%`、储备 `<` 供应或净储备 `<0` 紧急；数据过旧 `>30min` |
| apxUSD peg | 1min | 当前价格偏离 `$1.00` 超过 `0.30%` |
| Supply | 1min | apxUSD / apyUSD `totalSupply` 在 `1m/30m` 变化超过 `10%`，或 apxUSD `±5M`、apyUSD `±2M shares` |
| apyUSD totalAssets | 1min | `1m/30m` 变化超过 `10%`，或 `±5M apxUSD` |
| apyUSD priceAPXUSD | 1min | `1m/30m` 变化超过 `5%` |
| apyUSD mint backing | 1min | share 增量 `>100K` 且底层资产背书 `<99%` |
| Security Events | 1min | 大额 mint/burn；权限、升级、暂停、AccessManager、供应上限、解锁参数、收益归属或 Curve 管理参数事件 |
| Pendle apxUSD / apyUSD | 1min | liquidity `1m/30m` 下降 `>10%`；implied APY 或 PT price `1m/30m` 变化 `>10%` |
| Morpho PT-apyUSD-18JUN2026-USDC | 1min | Total Market Size 或 Total Liquidity `1m/30m` 下降 `>10%`；borrow rate `1m/30m` 变化 `>10%`；oracle price `1m/30m` 变化 `>2%` |
| Curve apxUSD-USDC | 1min | 单币余额 `1m/30m` 下降 `>10%`；virtual price `1m/30m` 变化 `>1%`；池子不平衡 `>20%`；swap price 偏离 `>0.30%` |
| Curve apyUSD-apxUSD | 1min | 总价值 `1m/30m` 下降 `>10%`；virtual price `1m/30m` 变化 `>1%`；value-adjusted imbalance `>20%`；apyUSD/apxUSD 相对 vault price 偏离 `>1.50%` |
| Commit / Unlock | 1min | cap 使用率 `>90%`；totalAssets `1m/30m` 变化 `>10%` 或超过 token 绝对阈值；unlocking delay 任意变化 |
| Yield Distribution | 1min | annualized yield 或 APY `30m` 变化 `>10%`；unvested yield `30m` 变化 `>20%` |
| STRC / SATA | 5min | 当前价格 `<$95` |

## 关键市场

• Pendle apxUSD：`0x50dce085af29caba28f7308bea57c4043757b491`
• Pendle apyUSD：`0x3c53fae231ad3c0408a8b6d33138bbff1caec330`
• Morpho PT-apyUSD-18JUN2026-USDC：`0xa75bb490ecfee90c86a9d22ebc2dde42fb83478b3f18722b9fc6f5f668cab124`
• Curve apxUSD-USDC：`0xE1B96555BbecA40E583BbB41a11C68Ca4706A414`
• Curve apyUSD-apxUSD：`0xe41be7b340f7c2eda4da1e99b42ee1b228b526b7`

## 状态解释

`/status` 显示当前快照和活跃告警：

• 无活跃告警时显示全部正常
• 持续性指标恢复后，下一轮检查会发送恢复通知并清除活跃状态
• 链上安全事件发生后，协议安全状态会保持红色 `60min`
• Morpho `utilization` 目前只展示，不单独触发告警

## 覆盖范围

当前覆盖 Ethereum 主网上配置的 apxUSD、apyUSD、apyUSD ERC-4626 vault、Pendle、Morpho、Curve、CommitToken / UnlockToken、收益分发合约、Accountable PoR 和 STRC / SATA 外部风险信号。

尚未覆盖：多链部署、跨链桥、CEX 深度、所有 DEX 池子、全部持仓地址集中度和 CEX order book。
