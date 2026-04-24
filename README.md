# APYX Stablecoin & Pendle Pool Monitor

Python monitoring service for Apyx stablecoins and Pendle pools. It sends Telegram alerts for STRC price, apxUSD peg, Pendle liquidity, PT APY, PT price, token supply, and TVL threshold breaches.

## Setup

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
```

Set these values in `.env`:

```text
FINNHUB_API_KEY=
TG_BOT_TOKEN=
TG_CHAT_ID=
ETH_RPC_URL=
```

## Run

```bash
python main.py
```

Run one immediate cycle:

```bash
python main.py --once
```

## Tests

```bash
python -m pip install -r requirements-dev.txt
pytest -q
python -m compileall config.py history.py alert monitors main.py
```
