# APYX Stablecoin & Pendle Pool Monitor

## Overview

Python monitoring service for Apyx stablecoins (apxUSD, apyUSD) and their Pendle pools. Sends Telegram alerts when thresholds are breached.

## Architecture

Single Python process using APScheduler with two frequency groups. All monitors share an Alert Engine that deduplicates and sends Telegram notifications.

```
APYX Monitor (Python)
├── 1-min scheduler
│   ├── apxUSD peg check (DeFiLlama)
│   ├── apxUSD total supply check (on-chain)
│   └── apyUSD total supply check (on-chain)
├── 5-min scheduler
│   ├── STRC price check (Finnhub)
│   ├── Pendle apxUSD pool: liquidity, PT APY, PT price
│   ├── Pendle apyUSD pool: liquidity, PT APY, PT price
│   ├── apxUSD TVL (DeFiLlama)
│   └── apyUSD TVL (DeFiLlama)
└── Alert Engine (threshold → dedup → Telegram)
```

## Contract Addresses (Ethereum Mainnet)

| Token | Address |
|-------|---------|
| apxUSD | `0x98A878b1Cd98131B271883B390f68D2c90674665` |
| apyUSD | `0x38EEb52F0771140d10c4E9A9a72349A329Fe8a6A` |
| Pendle apxUSD market | `0x50dce085af29caba28f7308bea57c4043757b491` |
| Pendle apyUSD market | `0x3c53fae231ad3c0408a8b6d33138bbff1caec330` |

## Data Sources

| Metric | Source | Method |
|--------|--------|--------|
| STRC stock price | Finnhub REST API | `GET /api/v1/quote?symbol=STRC` |
| apxUSD peg price | DeFiLlama | `GET https://coins.llama.fi/prices?coins=ethereum:0x98A8...4665` |
| Pendle pool data (x2) | Pendle V2 API | `GET https://api-v2.pendle.finance/core/v1/markets/{addr}` |
| apxUSD total supply | Ethereum RPC | `eth_call` → `totalSupply()` on ERC20 contract |
| apyUSD total supply | Ethereum RPC | `eth_call` → `totalSupply()` on ERC20 contract |
| apxUSD TVL | DeFiLlama | `GET https://api.llama.fi/tvl/apxUSD` or stablecoin endpoint |
| apyUSD TVL | DeFiLlama / on-chain | DeFiLlama protocol TVL or `totalAssets()` on ERC-4626 |

Pendle API returns per market: `liquidity` (USD), `impliedApy` (decimal), `ptPrice` (USD).

## Alert Rules

| Metric | Freq | Condition | Alert Content |
|--------|------|-----------|---------------|
| STRC price | 5min | < $95 | Current price, drop %, distance from par |
| apxUSD peg | 1min | Deviation from $1 > 0.3% | Current price, deviation |
| Pendle liquidity (apxUSD) | 5min | 1h drop > 10% | Current value, delta, pool name |
| Pendle liquidity (apyUSD) | 5min | 1h drop > 10% | Current value, delta, pool name |
| PT APY (apxUSD) | 5min | 1h change > 10% | Current APY, delta |
| PT APY (apyUSD) | 5min | 1h change > 10% | Current APY, delta |
| PT price (apxUSD) | 5min | 1h change > 10% | Current price, delta |
| PT price (apyUSD) | 5min | 1h change > 10% | Current price, delta |
| apxUSD supply | 1min | Change > 10% | Current supply, delta |
| apyUSD supply | 1min | Change > 10% | Current supply, delta |
| apxUSD TVL | 5min | 1h change > 10% | Current TVL, delta |
| apyUSD TVL | 5min | 1h change > 10% | Current TVL, delta |

Total: 13 alert checks per cycle.

## Deduplication

- Same metric alert: 5-minute cooldown. No repeat within window.
- Recovery: when metric returns to normal, send one "recovered" message.

Cooldown key format: `{metric}:{token_or_pool}` e.g. `pendle_liquidity:apxUSD`.

## Project Structure

```
APYX/
├── config.yaml          # Thresholds, API keys, addresses
├── requirements.txt
├── main.py              # Entry point, starts scheduler
├── monitors/
│   ├── strc_price.py    # STRC stock price monitor
│   ├── peg.py           # apxUSD peg monitor
│   ├── pendle.py        # Pendle pool data (liquidity/APY/PT price) x2 pools
│   └── supply.py        # On-chain supply monitor (apxUSD + apyUSD)
│   └── tvl.py           # TVL monitor (apxUSD + apyUSD)
├── alert/
│   ├── engine.py        # Threshold check + cooldown dedup
│   └── telegram.py      # TG Bot message sender
└── .env                 # FINNHUB_API_KEY, TG_BOT_TOKEN, TG_CHAT_ID, ETH_RPC_URL
```

## Configuration (config.yaml)

```yaml
finnhub:
  symbol: "STRC"
  threshold_price: 95.0

peg:
  threshold_pct: 0.003  # 0.3%

pendle:
  markets:
    - name: "apxUSD"
      address: "0x50dce085af29caba28f7308bea57c4043757b491"
    - name: "apyUSD"
      address: "0x3c53fae231ad3c0408a8b6d33138bbff1caec330"
  liquidity_drop_pct: 0.10
  apy_change_pct: 0.10
  pt_price_change_pct: 0.10
  window_minutes: 60

supply:
  tokens:
    - name: "apxUSD"
      address: "0x98A878b1Cd98131B271883B390f68D2c90674665"
    - name: "apyUSD"
      address: "0x38EEb52F0771140d10c4E9A9a72349A329Fe8a6A"
  threshold_pct: 0.10

tvl:
  tokens:
    - name: "apxUSD"
      # DeFiLlama stablecoin ID
    - name: "apyUSD"
      # DeFiLlama protocol or ERC-4626 totalAssets
  threshold_pct: 0.10
  window_minutes: 60

alert:
  cooldown_minutes: 5
```

## Dependencies

- `apscheduler` — job scheduling
- `aiohttp` — async HTTP client
- `web3` — on-chain supply reads
- `python-telegram-bot` — TG notifications
- `pyyaml` — config loading
- `python-dotenv` — .env loading

## Telegram Message Format

```
[APYX ALERT] apxUSD Peg Deviation
Price: $0.9965
Deviation: -0.35%
Time: 2026-04-24 14:30 UTC
```

```
[APYX RECOVERY] apxUSD Peg Normal
Price: $1.0002
Deviation: +0.02%
Time: 2026-04-24 14:36 UTC
```

## Running

```bash
pip install -r requirements.txt
cp .env.example .env  # fill in API keys
python main.py
```

Use systemd or pm2 for production keep-alive.
