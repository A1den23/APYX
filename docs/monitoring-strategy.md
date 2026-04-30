# APYX Monitor Strategy

📋 监控策略说明

APYX 稳定币与 Pendle 市场安全监控  
stablecoin-safety · ETHEREUM · apxUSD / apyUSD

⚠️ 主要风险：

• apxUSD 是 APYX 体系内的美元锚定资产，核心风险是价格脱锚、供应量异常变化、权限/升级事件以及相关 DeFi 池流动性突然下滑。

• APYX 官方 Accountable PoR 页面提供 apxUSD 实时偿付证明，当前监控直接读取其公开 dashboard API，覆盖 `collateralization`、总储备、总供应、净超额储备和数据更新时间。PoR 降低报表篡改风险，但不能单独排除源头资产、托管账户或外部数据源造假，因此必须和价格、链上供应、权限事件一起看。

• apyUSD 是 ERC-4626 vault share，`totalSupply()` 代表 share supply，不等于底层资产规模；真正资产规模需要看 `totalAssets()`，share 价格需要看 `previewRedeem(1e18)` 得到的 `priceAPXUSD`。

• apyUSD 的关键风险不是单看 share supply，而是 share 增发是否有足够底层 apxUSD 资产背书。异常 share mint 但 `totalAssets` 没同步增加，可能意味着无背书增发、权限滥用、合约逻辑错误或外部系统异常。

• Pendle apxUSD / apyUSD 市场、Curve apxUSD-USDC 池和 Curve apyUSD-apxUSD 池是主要链上流动性与价格发现位置之一；流动性、PT APY、PT price、池深度、value-adjusted 不平衡度、virtual price、apxUSD/USDC swap price 和 apyUSD/apxUSD 相对 vault priceAPXUSD 的偏离在 30 分钟窗口内剧烈变化，通常早于更慢的数据源反映出市场压力。

• CommitToken / UnlockToken 和收益分发合约是用户存取、解锁、cap 限制和收益归属的关键路径；这些合约的参数变化、锁仓资产异常、cap 使用率过高或未归属收益跳变，需要和稳定币价格、供应和 PoR 一起监控。

• 链上权限、升级、暂停事件是高优先级风险信号。`RoleGranted`、`Upgraded`、`Paused` 等事件本身未必代表攻击，但代表协议控制面发生变化，必须实时提示并在 `/status` 中保留异常状态。

• STRC / SATA 股价被纳入宏观风险监控。当前系统把任一标的跌破 `$95` 作为外部风险信号，不直接证明链上资产异常，但可以提示 APYX 相关市场压力。

🚪 离场 / 人工介入标准：

Accountable PoR 偿付率跌破 `100%`；或偿付率低于 `100.1%` 且持续恶化；或 PoR 数据超过 `30` 分钟未更新；或 apxUSD 价格偏离 1 美元超过 `0.30%`；或 apxUSD / apyUSD 供应量 1 分钟或 30 分钟变化超过 `10%`；或 apxUSD 单笔 mint/burn 超过 `5M`；或 apyUSD 单笔 mint/burn 超过 `2M`；或 apyUSD 新增 share 超过 `100K` 且底层资产背书低于 `99%`；或 Pendle 单池 liquidity / APY / PT price 在 30 分钟窗口触发阈值；或 Curve 池深度、virtual price 或 swap price 触发阈值；或 CommitToken cap/资产/解锁延迟异常；或收益分发年化收益资产量/APY/未归属收益异常；或任意被监控合约出现权限、升级、暂停、协议参数事件。

────────────────────────────

🔍 监控器（13 类，持续运行中）

🚨 APYX Accountable PoR 偿付状态（每 5 分钟检测一次）

通过 Accountable 官方 APYX Proof of Solvency 页面背后的公开接口读取实时偿付证明：

`https://accountable.apyx.fi/`

监控字段包括：

• `collateralization`：总储备 / 总供应  
• `reserves.total_reserves.value`：总储备  
• `reserves.total_supply.value`：总供应  
• `net`：净超额储备  
• `ts`：Accountable 数据更新时间

阈值：

• 偿付率 `<100%`、总储备 `<` 总供应或 `net < 0`：紧急告警  
• 偿付率 `<100.1%`：预警，表示储备缓冲不足
• 数据超过 `30` 分钟未更新：预警，表示实时 PoR 失去新鲜度

该接口请求需要带浏览器 `User-Agent`、`Origin` 和 `Referer` 头，否则可能返回 `403`。该监控是储备充足率信号，不替代 apxUSD 价格脱锚、STRC 价格、链上供应和权限事件监控。

🚨 apxUSD 价格脱锚（每 1 分钟检测一次）

通过 DefiLlama 读取 apxUSD 链上聚合价格，监控价格相对 `$1.00` 的偏离。阈值为 `0.30%`，即价格低于 `$0.9970` 或高于 `$1.0030` 时触发告警。  

该监控用于捕捉市场层面最直接的稳定币风险：储备/合约/流动性问题通常会先反映为价格脱锚。告警恢复条件是价格重新回到偏离 `<=0.30%`。

⚠️ apxUSD 供应量异常变化（每 1 分钟检测一次）

通过 Ethereum RPC 直接读取 apxUSD ERC20 `totalSupply()`。同时比较：

• 与上一分钟采样的变化  
• 与 30 分钟窗口基线的变化

任一窗口变化超过 `10%`，或绝对变化超过 `5M apxUSD`，即触发告警。该监控覆盖大额增发、回收、合约异常供应量变化。

动态阈值：百分比阈值跟随当前供应规模自动变化；绝对阈值固定为 `5M`，用于捕捉供应规模较大时百分比变化不明显但绝对金额很大的事件。

⚠️ apyUSD share supply 异常变化（每 1 分钟检测一次）

通过 Ethereum RPC 读取 apyUSD ERC20 `totalSupply()`。注意这里监控的是 apyUSD share supply，不是 vault 底层资产规模。

同时比较 1 分钟相邻采样和 30 分钟窗口。任一窗口变化超过 `10%`，或绝对变化超过 `2M shares`，即触发告警。

该监控用于发现 share 被大额 mint/burn 的结果型异常，但不能单独判断是否有足额资产背书，需要结合 `apyUSD totalAssets` 和 `mint backing` 监控一起看。

🚨 apyUSD totalAssets 异常变化（每 1 分钟检测一次）

通过 Ethereum RPC 读取 apyUSD ERC-4626 `totalAssets()`，代表 vault 底层 apxUSD 资产规模。

同时比较 1 分钟相邻采样和 30 分钟窗口。任一窗口变化超过 `10%`，或绝对变化超过 `5M apxUSD`，即触发告警。

该监控用于捕捉 vault 底层资产突然流入、流出、被错误计价或被异常提取。若 share supply 没明显变化但 `totalAssets` 大幅下降，应视为高优先级风险。

🚨 apyUSD priceAPXUSD 异常变化（每 1 分钟检测一次）

通过 ERC-4626 `previewRedeem(1e18)` 读取 1 个 apyUSD share 当前预览可赎回的 apxUSD 数量，即 `priceAPXUSD`。

同时比较 1 分钟相邻采样和 30 分钟窗口。任一窗口变化超过 `5%`，即触发告警。

该监控用于发现 share 兑换率异常跳变。兑换率异常可能来自收益/亏损异常、资产估值错误、share 供应逻辑异常或 vault 内资产变化。

🚨 apyUSD mint backing（每 1 分钟检测一次）

该监控把 apyUSD share 增量和底层资产增量放在一起验证：

• `share 增量 = 当前 totalSupply - 上次 totalSupply`  
• `理论应增加资产 = share 增量 × priceAPXUSD`  
• `实际增加资产 = 当前 totalAssets - 上次 totalAssets`  
• `背书比例 = 实际增加资产 / 理论应增加资产`

当新增 share 超过 `100K`，并且背书比例低于 `99%` 时触发 `apyUSD Mint Backing Mismatch`。

这个监控专门防“share 被铸出来了，但 vault 资产没进来”的场景，覆盖无背书增发、后端/权限异常、合约 mint 逻辑错误、ERC-4626 accounting 异常等风险。

🚨 链上安全事件（每 1 分钟检测一次）

通过 Ethereum RPC `eth_getLogs` 扫描最近区块日志，监控两类事件：

• apxUSD / apyUSD 单笔 mint 或 burn：识别 ERC20 `Transfer` 事件中 `from = 0x000...000` 或 `to = 0x000...000`。apxUSD 单笔超过 `5M`、apyUSD 单笔超过 `2M` 即告警。  
• 权限、升级、暂停和协议参数事件：监听 OpenZeppelin `AccessManager` 的 `OperationScheduled`、`OperationExecuted`、`OperationCanceled`、`RoleGranted(uint64,address,uint32,uint48,bool)`、`RoleRevoked`、`TargetFunctionRoleUpdated` 等事件，同时覆盖 `OwnershipTransferred`、`AdminChanged`、`Upgraded`、`Paused`、`Unpaused`、供应上限、解锁参数、收益归属、CommitToken、UnlockToken 和 Curve 管理参数事件。

首次启动默认扫描最近 `25` 个区块，后续从上次扫描位置继续，每轮最多扫 `100` 个区块。安全事件一旦发生会立即 Telegram 告警，并且 `/status` 的协议安全区保持红色 `60` 分钟。

⚠️ Pendle apxUSD / apyUSD 市场异常（每 1 分钟检测一次）

通过 Pendle API 监控两个市场：

• Pendle apxUSD market：`0x50dce085af29caba28f7308bea57c4043757b491`  
• Pendle apyUSD market：`0x3c53fae231ad3c0408a8b6d33138bbff1caec330`

每 1 分钟读取 liquidity、implied APY、PT price，并与 30 分钟窗口基线比较：

• liquidity 30 分钟下降超过 `10%` 告警  
• PT APY 30 分钟变化超过 `10%` 告警  
• PT price 30 分钟变化超过 `10%` 告警

该监控用于发现池子流动性被抽走、PT 定价异常、收益率异常跳变等市场层面风险。

⚠️ Curve 池异常（每 1 分钟检测一次）

通过 Ethereum RPC 读取官方 Curve 池：

• apxUSD-USDC：`0xE1B96555BbecA40E583BbB41a11C68Ca4706A414`
• apyUSD-apxUSD：`0xe41be7b340f7c2eda4da1e99b42ee1b228b526b7`

apxUSD-USDC 每 1 分钟读取池内 apxUSD / USDC 余额、`get_virtual_price()` 和 1 apxUSD 兑换 USDC 的 `get_dy()` 价格，并与 30 分钟窗口比较：

• 单币余额 30 分钟下降超过 `10%` 告警
• 池子不平衡度超过 `20%` 告警
• virtual price 30 分钟变化超过 `1%` 告警
• apxUSD/USDC swap price 偏离 1 美元超过 `0.30%` 告警

apyUSD-apxUSD 每 1 分钟读取池内 apyUSD / apxUSD 余额、apyUSD vault `priceAPXUSD`、`get_virtual_price()` 和 1 apyUSD 兑换 apxUSD 的 `get_dy()` 价格：

• 池子总价值按 `apyUSD balance * priceAPXUSD + apxUSD balance` 折算成 apxUSD，30 分钟下降超过 `10%` 告警
• value-adjusted 不平衡度按 `apyUSD balance * priceAPXUSD` 和 `apxUSD balance` 比较，超过 `20%` 告警
• virtual price 30 分钟变化超过 `1%` 告警
• apyUSD/apxUSD Curve 报价相对 vault `priceAPXUSD` 偏离超过 `1.50%` 告警

该监控用于发现主池流动性被抽走、池子失衡、LP 价格异常、链上价格脱锚或 apyUSD 二级市场报价明显偏离 vault 赎回价值。

⚠️ Commit / Unlock 异常（每 1 分钟检测一次）

通过 Ethereum RPC 读取官方 CommitToken：

• apxUSD Commit：`0x17122d869d981d184118B301313BCD157c79871e`
• apxUSD-USDC LP Commit：`0xdfC3cF7E540628a52862907DC1AB935Cd5859375`
• apyUSD-apxUSD LP Commit：`0x55095f69C30E58290eCaA80F44019557d2bC4A60`

监控字段包括 `totalAssets()`、`totalSupply()`、`supplyCap()`、`supplyCapRemaining()` 和 `unlockingDelay()`：

• cap 使用率超过 `90%` 告警
• totalAssets 1 分钟或 30 分钟变化超过 `10%`，或绝对变化超过配置阈值告警
• unlocking delay 任意变化告警

该监控用于发现锁仓资产快速流出、cap 被打满、解锁周期被调整或用户存取路径出现异常。

⚠️ apyUSD 收益分发异常（每 1 分钟检测一次）

通过 `ApyUSDRateView` 读取 `annualizedYield()` 和 APY，并从 apyUSD 关联的 vesting 合约读取已归属、未归属收益和剩余归属周期：

• ApyUSDRateView：`0xCABa36EDE2C08e16F3602e8688a8bE94c1B4e484`

年化收益资产量或 APY 30 分钟变化超过 `10%`，或未归属收益 30 分钟变化超过 `20%` 时告警。该监控用于发现收益输入、归属、分发或 rate view 计算异常。

⚠️ STRC / SATA 宏观风险（每 5 分钟检测一次）

通过 Finnhub 读取 STRC / SATA 股价。当前阈值为 `$95`，当任一标的价格低于 `$95` 时告警。

该监控不直接证明链上稳定币风险，但作为 APYX 相关外部市场压力信号。若 STRC / SATA 下跌与 apxUSD 脱锚、Pendle/Curve 流动性下降、供应量异常同时出现，应提升人工响应优先级。

────────────────────────────

💡 怎么看告警？

⚠️ 警告：指标开始接近风险区或出现异常变化，需要观察并准备人工确认。  
🚨 紧急：稳定币价格、供应、背书、权限或主要流动性发生异常，需要立刻处理。

`/status` 的颜色逻辑：

• 🟢 表示当前没有活跃告警。  
• 🔴 表示该 section 至少有一个活跃告警。  
• 对持续性指标，红色会持续到下一轮检查确认恢复。  
• 对链上安全事件，红色会在事件发生后保持 `60` 分钟，即使事件本身是一次性日志。  
• 对 Accountable PoR 偿付状态，红色会持续到下一轮 5 分钟检查确认偿付率、储备/供应和数据新鲜度恢复正常。

📝 当前监控范围说明：

当前系统覆盖 Ethereum 主网上配置的 apxUSD、apyUSD、apyUSD ERC-4626 vault、Pendle apxUSD/apyUSD 市场、Curve apxUSD-USDC 与 apyUSD-apxUSD 池、CommitToken / UnlockToken、收益分发合约、Accountable APYX PoR 偿付状态，以及 STRC / SATA 外部风险信号。系统尚未覆盖多链部署、跨链桥、CEX 深度、所有 DEX 池子和所有持仓地址集中度。若后续需要更完整的稳定币风控，应继续补充主要 holder concentration、多链 supply、跨链桥事件和 CEX order book 监控。
