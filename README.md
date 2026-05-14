# APYX Monitor

监控 Apyx 稳定币（apxUSD / apyUSD）、主要链上市场、权限事件和外部风险信号的 Python 服务，通过 Telegram 发送告警和状态查询。

## 监控指标

| 模块 | 指标 | 数据源 | 频率 |
|------|------|--------|------|
| Peg | apxUSD 锚定价格偏差 | DefiLlama | 1 min |
| Supply | 链上 totalSupply 变动 | ETH RPC | 1 min |
| Security Events | 大额 mint/burn、AccessManager、升级/暂停、协议参数事件 | ETH RPC logs | 1 min |
| Solvency | Accountable PoR 偿付率 / 储备 / 供应 | Accountable API | 5 min |
| TradFi | STRC / SATA 跌破阈值 | Finnhub | 5 min |
| Pendle | 流动性 / APY / PT 价格变动 | Pendle API | 1 min |
| Morpho | Total Market Size / Total Liquidity / borrow rate / oracle price 变动 | Morpho Blue API + ETH RPC | 1 min |
| Curve | apxUSD-USDC / apyUSD-apxUSD 池深度 / virtual price / swap price | ETH RPC | 1 min |
| Commit / Unlock | CommitToken totalAssets / cap 使用率 / unlocking delay | ETH RPC | 1 min |
| apyUSD | totalAssets / priceAPXUSD 变动 | ETH RPC | 1 min |
| Yield Distribution | 年化收益资产量 / APY / 未归属收益 | ETH RPC | 1 min |

说明：

- `Pendle` 每 1 分钟检查一次，同时比较相邻 1 分钟采样和 30 分钟窗口内 liquidity / PT APY / PT price 的变化。
- `Morpho` 每 1 分钟检查一次 `PT-apyUSD-18JUN2026-USDC` 市场，同时比较相邻 1 分钟采样和 30 分钟窗口内 Total Market Size、Total Liquidity（可提取流动性）、borrow rate 和 oracle price 的变化；oracle price 变化超过 `2%` 时告警。
- `apxUSD supply` 每 1 分钟读取 apxUSD ERC20 `totalSupply()`，同时比较 1 分钟相邻采样和 30 分钟窗口；任一窗口变化超过 `10%` 或绝对变化超过 `5M` 时告警。
- `apyUSD supply` 每 1 分钟读取 apyUSD ERC20 `totalSupply()`，代表 share supply，不代表底层资产规模；同时比较 1 分钟相邻采样和 30 分钟窗口，任一窗口变化超过 `10%` 或绝对变化超过 `2M` share 时告警。
- `apyUSD totalAssets` 每 1 分钟读取 apyUSD ERC-4626 `totalAssets()`，代表 vault 底层 apxUSD 资产规模；同时比较 1 分钟相邻采样和 30 分钟窗口，任一窗口变化超过 `10%` 或绝对变化超过 `5M apxUSD` 时告警。
- `apyUSD priceAPXUSD` 每 1 分钟读取 apyUSD ERC-4626 `previewRedeem(1e18)`，代表 1 apyUSD 当前预览可赎回的 apxUSD 数量；同时比较 1 分钟相邻采样和 30 分钟窗口，任一窗口变化超过 `5%` 时告警。
- `Security Events` 每 1 分钟扫描最近区块日志：当 apxUSD / apyUSD 单笔 mint 或 burn 超过各自供应量绝对阈值时告警；当被监控合约、AccessManager、CommitToken、UnlockToken、Curve 池和收益分发相关合约出现权限、升级、暂停、供应上限、解锁参数、收益归属或 Curve 管理参数事件时告警。安全事件发生后，`/status` 的协议安全区会保持红色 60 分钟。
- `apyUSD mint backing` 对比 share supply 增量和 `totalAssets` 增量；当新增 share 超过 `100K` 且新增资产低于按 `priceAPXUSD` 计算所需资产的 `99%` 时告警。
- `Curve` 每 1 分钟读取 apxUSD-USDC 池余额、`get_virtual_price()` 和 apxUSD->USDC `get_dy()` 价格；同时读取 apyUSD-apxUSD 池总价值、value-adjusted 不平衡度、`get_virtual_price()` 和 apyUSD->apxUSD 相对 vault `priceAPXUSD` 的偏离。池余额、总价值和 virtual price 同时比较相邻 1 分钟采样和 30 分钟窗口；价值折算后池子失衡或价格偏离按当前值触发告警。
- `Commit / Unlock` 每 1 分钟读取官方 CommitToken 的 `totalAssets()`、`totalSupply()`、`supplyCap()`、`supplyCapRemaining()` 和 `unlockingDelay()`；cap 使用率过高、锁仓资产异常变化或解锁延迟改变触发告警。
- `Yield Distribution` 每 1 分钟读取 `ApyUSDRateView` 的 `annualizedYield()` 和 APY，并从 apyUSD 关联的 vesting 合约读取已归属和未归属收益；收益资产量、收益率或未归属收益在窗口内跳变触发告警。
- `TradFi` 每 5 分钟通过 Finnhub 读取 STRC 和 SATA，任一标的跌破配置阈值时作为外部风险信号告警。
- `Solvency` 每 5 分钟读取 Accountable APYX PoR API；当偿付率低于 `100.1%`、低于 `100%`、总储备低于总供应、净超额储备为负，或数据超过 `30` 分钟未更新时告警。`/status` 会展示偿付率、储备/供应和更新时间。

## 部署（Docker）

```bash
cp .env.example .env
# 编辑 .env 填入配置
docker compose up -d --build
```

查看日志：

```bash
docker compose logs -f
```

## 环境变量

| 变量 | 说明 | 示例 |
|------|------|------|
| `TG_BOT_TOKEN` | Telegram Bot API Token | `123456:ABC-DEF` |
| `TG_CHAT_ID` | 接收消息的 Chat ID | `<your-chat-id>` |
| `ETH_RPC_URL` | Ethereum JSON-RPC 端点（需支持 eth_call） | Alchemy / Infura |
| `ETH_RPC_FALLBACK_URL` | 备用 Ethereum JSON-RPC 端点；启动时主 RPC 不可用则切换到此端点 | Infura / QuickNode |
| `FINNHUB_API_KEY` | Finnhub API Key（免费注册） | `d7lk...` |

## Telegram 命令

| 命令 | 说明 |
|------|------|
| `/status` | 查看所有监控指标当前值 |
| `/thresholds` | 查看所有预警阈值 |
| `/health` | 服务自检：运行时间、成功率、数据新鲜度、错误分布 |
| `/strategy` | 查看当前监控策略说明 |
| `/help` | 查看 Telegram 命令帮助 |

## 生命周期通知

服务以常驻模式运行时会发送 Telegram 系统通知：

- Docker 容器启动并完成调度器初始化后，发送 `[APYX SYSTEM] APYX Monitor Started`。
- Docker stop / redeploy 触发 `SIGTERM` 或 `SIGINT` 时，发送 `[APYX SYSTEM] APYX Monitor Stopping`，随后停止调度器和 Telegram 命令轮询。

## 项目结构

```
main.py           CLI 入口
config.yaml       监控参数配置
app/
  config.py       配置加载（config.yaml + .env）
  service.py      服务启动、调度器、生命周期
  jobs.py         定时监控任务编排
  security_scan.py 链上安全事件扫描编排
  runtime_state.py 运行状态持久化
  history.py      滚动指标历史记录
  status_cache.py /status 最近快照缓存
alert/
  engine.py       告警引擎（触发 / 冷却 / 恢复）
  telegram.py     Telegram 发送 + 命令监听
commands/
  health.py       运行状态追踪
  status.py       /status 和 /health 消息生成
  thresholds.py   /thresholds 阈值说明生成
monitors/
  peg.py          锚定价格
  supply.py       链上供应量
  apyusd.py       apyUSD ERC-4626 totalAssets / priceAPXUSD
  solvency.py     Accountable PoR 偿付状态
  security_events.py 链上安全事件日志
  pendle.py       Pendle 市场数据
  morpho.py       Morpho 市场数据
  curve.py        Curve 池链上状态
  commit.py       CommitToken / Unlock 参数
  yield_distribution.py apyUSD 收益分发
  strc_price.py   Finnhub TradFi 价格
```

## 本地运行

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

单次执行：

```bash
python main.py --once
```

## 测试

```bash
pip install -r requirements-dev.txt
pytest -q
```

`pytest.ini` 已设置 `pythonpath = .` 和 `--capture=sys`，上述命令可直接运行。
