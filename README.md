# APYX Monitor

监控 Apyx 稳定币（apxUSD / apyUSD）及 Pendle 市场的 Python 服务，通过 Telegram 发送告警和状态查询。

## 监控指标

| 模块 | 指标 | 数据源 | 频率 |
|------|------|--------|------|
| Peg | apxUSD 锚定价格偏差 | DefiLlama | 1 min |
| Supply | 链上 totalSupply 变动 | ETH RPC | 1 min |
| STRC | STRC 股价跌破阈值 | Finnhub | 5 min |
| Pendle | 流动性 / APY / PT 价格变动 | Pendle API | 5 min |
| TVL | 流通供应量变动 | DefiLlama Stablecoin | 5 min |

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
| `TG_CHAT_ID` | 接收消息的 Chat ID | `2097712941` |
| `ETH_RPC_URL` | Ethereum JSON-RPC 端点（需支持 eth_call） | Alchemy / Infura |
| `FINNHUB_API_KEY` | Finnhub API Key（免费注册） | `d7lk...` |

## Telegram 命令

| 命令 | 说明 |
|------|------|
| `/status` | 查看所有监控指标当前值及阈值 |
| `/health` | 服务自检：运行时间、成功率、数据新鲜度、错误分布 |

## 项目结构

```
main.py           入口，调度器 + 定时任务
config.py         配置加载（config.yaml + .env）
config.yaml       监控参数配置
health.py         运行状态追踪
history.py        滚动指标历史记录
status.py         /status 和 /health 消息生成
alert/
  engine.py       告警引擎（触发 / 冷却 / 恢复）
  telegram.py     Telegram 发送 + 命令监听
monitors/
  peg.py          锚定价格
  supply.py       链上供应量
  tvl.py          TVL / 流通量
  pendle.py       Pendle 市场数据
  strc_price.py   STRC 股价
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
