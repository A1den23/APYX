# APYX Monitor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the APYX stablecoin and Pendle pool monitoring service described in `docs/superpowers/specs/2026-04-24-apyx-monitor-design.md`.

**Architecture:** A single async Python process runs APScheduler jobs at 1-minute and 5-minute intervals. Monitors fetch external data, convert it into metric values, pass breach state through a shared alert engine, and send deduplicated Telegram alerts and recoveries.

**Tech Stack:** Python 3.11+, APScheduler, aiohttp, web3.py, PyYAML, python-dotenv, python-telegram-bot, pytest, pytest-asyncio.

---

## Source Spec

- `docs/superpowers/specs/2026-04-24-apyx-monitor-design.md`

## File Structure

Create this structure:

```text
APYX/
├── .env.example
├── .gitignore
├── config.yaml
├── config.py
├── history.py
├── main.py
├── requirements.txt
├── requirements-dev.txt
├── alert/
│   ├── __init__.py
│   ├── engine.py
│   └── telegram.py
├── monitors/
│   ├── __init__.py
│   ├── peg.py
│   ├── pendle.py
│   ├── strc_price.py
│   ├── supply.py
│   └── tvl.py
└── tests/
    ├── test_alert_engine.py
    ├── test_config.py
    ├── test_history.py
    ├── test_peg.py
    ├── test_pendle.py
    ├── test_strc_price.py
    ├── test_supply.py
    └── test_tvl.py
```

Current workspace note: `/home/tan81/workspace/APYX` is not a git repository. Task 0 initializes git so the commit steps are executable.

## Behavioral Decisions Locked By This Plan

- STRC alert threshold: alert when current price is strictly below `$95.00`.
- STRC drop percent: `(100.0 - current_price) / 100.0`, because the alert content asks for drop and distance from par.
- Peg deviation: `(price - 1.0) / 1.0`; alert when absolute deviation is greater than `0.003`.
- One-hour change rules: compare current value against the sample closest to but not newer than `now - window_minutes`.
- Pendle liquidity breach: one-hour percent change is less than `-threshold`.
- Pendle PT APY, PT price, and TVL breach: absolute one-hour percent change is greater than `threshold`.
- Supply breach: compare with the immediately previous observed supply sample for the same token.
- First observations and missing one-hour baselines do not alert.
- ERC20 supply values are normalized using each token contract's `decimals()` result.
- Telegram recovery messages bypass the alert cooldown and are sent once when a metric returns to normal.
- The spec text says "13 alert checks", while the rule table enumerates 12 checks. This plan implements the 12 checks listed in the table.

---

### Task 0: Bootstrap Project

**Files:**
- Create: `.gitignore`
- Create: `.env.example`
- Create: `requirements.txt`
- Create: `requirements-dev.txt`
- Create: `config.yaml`
- Create: `alert/__init__.py`
- Create: `monitors/__init__.py`

- [ ] **Step 1: Initialize git**

Run:

```bash
git init
```

Expected: `Initialized empty Git repository` or `Reinitialized existing Git repository`.

- [ ] **Step 2: Create dependency files**

Create `requirements.txt` with:

```text
aiohttp>=3.9,<4
apscheduler>=3.10,<4
python-dotenv>=1,<2
python-telegram-bot>=21,<22
pyyaml>=6,<7
web3>=6,<7
```

Create `requirements-dev.txt` with:

```text
-r requirements.txt
pytest>=8,<9
pytest-asyncio>=0.23,<1
```

- [ ] **Step 3: Create environment and ignore files**

Create `.env.example` with:

```text
FINNHUB_API_KEY=
TG_BOT_TOKEN=
TG_CHAT_ID=
ETH_RPC_URL=
```

Create `.gitignore` with:

```text
.env
.venv/
__pycache__/
.pytest_cache/
*.pyc
```

- [ ] **Step 4: Create base config**

Create `config.yaml` with:

```yaml
finnhub:
  symbol: "STRC"
  threshold_price: 95.0

peg:
  token:
    name: "apxUSD"
    address: "0x98A878b1Cd98131B271883B390f68D2c90674665"
  threshold_pct: 0.003

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
      url: "https://api.llama.fi/tvl/apxUSD"
    - name: "apyUSD"
      url: "https://api.llama.fi/tvl/apyUSD"
  threshold_pct: 0.10
  window_minutes: 60

alert:
  cooldown_minutes: 5
```

- [ ] **Step 5: Create package marker files**

Create empty files:

```text
alert/__init__.py
monitors/__init__.py
```

- [ ] **Step 6: Install dependencies**

Run:

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-dev.txt
```

Expected: dependency installation completes without errors.

- [ ] **Step 7: Commit bootstrap**

Run:

```bash
git add .gitignore .env.example requirements.txt requirements-dev.txt config.yaml alert/__init__.py monitors/__init__.py
git commit -m "chore: bootstrap apyx monitor project"
```

Expected: commit succeeds.

---

### Task 1: Configuration Loader

**Files:**
- Create: `config.py`
- Create: `tests/test_config.py`

- [ ] **Step 1: Write the failing config tests**

Create `tests/test_config.py` with:

```python
from pathlib import Path

from config import load_app_config


def test_load_app_config_parses_thresholds_and_addresses(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
finnhub:
  symbol: "STRC"
  threshold_price: 95.0
peg:
  token:
    name: "apxUSD"
    address: "0x98A878b1Cd98131B271883B390f68D2c90674665"
  threshold_pct: 0.003
pendle:
  markets:
    - name: "apxUSD"
      address: "0x50dce085af29caba28f7308bea57c4043757b491"
  liquidity_drop_pct: 0.10
  apy_change_pct: 0.10
  pt_price_change_pct: 0.10
  window_minutes: 60
supply:
  tokens:
    - name: "apxUSD"
      address: "0x98A878b1Cd98131B271883B390f68D2c90674665"
  threshold_pct: 0.10
tvl:
  tokens:
    - name: "apxUSD"
      url: "https://api.llama.fi/tvl/apxUSD"
  threshold_pct: 0.10
  window_minutes: 60
alert:
  cooldown_minutes: 5
""".strip(),
        encoding="utf-8",
    )

    settings = load_app_config(config_path)

    assert settings.finnhub.symbol == "STRC"
    assert settings.finnhub.threshold_price == 95.0
    assert settings.peg.token.name == "apxUSD"
    assert settings.peg.threshold_pct == 0.003
    assert settings.pendle.markets[0].address == "0x50dce085af29caba28f7308bea57c4043757b491"
    assert settings.tvl.tokens[0].url == "https://api.llama.fi/tvl/apxUSD"
    assert settings.alert.cooldown_minutes == 5
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
. .venv/bin/activate
pytest tests/test_config.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'config'`.

- [ ] **Step 3: Implement config loader**

Create `config.py` with:

```python
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True)
class NamedAddress:
    name: str
    address: str


@dataclass(frozen=True)
class TvlToken:
    name: str
    url: str


@dataclass(frozen=True)
class FinnhubConfig:
    symbol: str
    threshold_price: float


@dataclass(frozen=True)
class PegConfig:
    token: NamedAddress
    threshold_pct: float


@dataclass(frozen=True)
class PendleConfig:
    markets: list[NamedAddress]
    liquidity_drop_pct: float
    apy_change_pct: float
    pt_price_change_pct: float
    window_minutes: int


@dataclass(frozen=True)
class SupplyConfig:
    tokens: list[NamedAddress]
    threshold_pct: float


@dataclass(frozen=True)
class TvlConfig:
    tokens: list[TvlToken]
    threshold_pct: float
    window_minutes: int


@dataclass(frozen=True)
class AlertConfig:
    cooldown_minutes: int


@dataclass(frozen=True)
class AppConfig:
    finnhub: FinnhubConfig
    peg: PegConfig
    pendle: PendleConfig
    supply: SupplyConfig
    tvl: TvlConfig
    alert: AlertConfig


def load_app_config(path: str | Path = "config.yaml") -> AppConfig:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return AppConfig(
        finnhub=FinnhubConfig(
            symbol=data["finnhub"]["symbol"],
            threshold_price=float(data["finnhub"]["threshold_price"]),
        ),
        peg=PegConfig(
            token=NamedAddress(**data["peg"]["token"]),
            threshold_pct=float(data["peg"]["threshold_pct"]),
        ),
        pendle=PendleConfig(
            markets=[NamedAddress(**item) for item in data["pendle"]["markets"]],
            liquidity_drop_pct=float(data["pendle"]["liquidity_drop_pct"]),
            apy_change_pct=float(data["pendle"]["apy_change_pct"]),
            pt_price_change_pct=float(data["pendle"]["pt_price_change_pct"]),
            window_minutes=int(data["pendle"]["window_minutes"]),
        ),
        supply=SupplyConfig(
            tokens=[NamedAddress(**item) for item in data["supply"]["tokens"]],
            threshold_pct=float(data["supply"]["threshold_pct"]),
        ),
        tvl=TvlConfig(
            tokens=[TvlToken(**item) for item in data["tvl"]["tokens"]],
            threshold_pct=float(data["tvl"]["threshold_pct"]),
            window_minutes=int(data["tvl"]["window_minutes"]),
        ),
        alert=AlertConfig(
            cooldown_minutes=int(data["alert"]["cooldown_minutes"]),
        ),
    )
```

- [ ] **Step 4: Run config tests**

Run:

```bash
pytest tests/test_config.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit config loader**

Run:

```bash
git add config.py tests/test_config.py
git commit -m "feat: load monitor configuration"
```

Expected: commit succeeds.

---

### Task 2: Alert Engine And Telegram Sender

**Files:**
- Create: `alert/engine.py`
- Create: `alert/telegram.py`
- Create: `tests/test_alert_engine.py`

- [ ] **Step 1: Write failing alert engine tests**

Create `tests/test_alert_engine.py` with:

```python
from datetime import datetime, timedelta, timezone

from alert.engine import AlertEngine


def test_alert_engine_deduplicates_within_cooldown() -> None:
    engine = AlertEngine(cooldown=timedelta(minutes=5))
    now = datetime(2026, 4, 24, 14, 30, tzinfo=timezone.utc)

    first = engine.evaluate(
        metric_key="peg:apxUSD",
        breached=True,
        alert_title="apxUSD Peg Deviation",
        alert_body="Price: $0.9960",
        recovery_title="apxUSD Peg Normal",
        recovery_body="Price: $1.0001",
        now=now,
    )
    second = engine.evaluate(
        metric_key="peg:apxUSD",
        breached=True,
        alert_title="apxUSD Peg Deviation",
        alert_body="Price: $0.9950",
        recovery_title="apxUSD Peg Normal",
        recovery_body="Price: $1.0001",
        now=now + timedelta(minutes=1),
    )

    assert first is not None
    assert first.kind == "ALERT"
    assert second is None


def test_alert_engine_sends_recovery_once() -> None:
    engine = AlertEngine(cooldown=timedelta(minutes=5))
    now = datetime(2026, 4, 24, 14, 30, tzinfo=timezone.utc)

    engine.evaluate(
        metric_key="peg:apxUSD",
        breached=True,
        alert_title="apxUSD Peg Deviation",
        alert_body="Price: $0.9960",
        recovery_title="apxUSD Peg Normal",
        recovery_body="Price: $1.0001",
        now=now,
    )
    recovery = engine.evaluate(
        metric_key="peg:apxUSD",
        breached=False,
        alert_title="apxUSD Peg Deviation",
        alert_body="Price: $0.9960",
        recovery_title="apxUSD Peg Normal",
        recovery_body="Price: $1.0001",
        now=now + timedelta(minutes=1),
    )
    duplicate = engine.evaluate(
        metric_key="peg:apxUSD",
        breached=False,
        alert_title="apxUSD Peg Deviation",
        alert_body="Price: $0.9960",
        recovery_title="apxUSD Peg Normal",
        recovery_body="Price: $1.0001",
        now=now + timedelta(minutes=2),
    )

    assert recovery is not None
    assert recovery.kind == "RECOVERY"
    assert duplicate is None
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
pytest tests/test_alert_engine.py -q
```

Expected: FAIL with `ModuleNotFoundError` for `alert.engine`.

- [ ] **Step 3: Implement alert engine**

Create `alert/engine.py` with:

```python
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone


@dataclass(frozen=True)
class AlertEvent:
    kind: str
    title: str
    body: str
    timestamp: datetime

    def telegram_text(self) -> str:
        stamp = self.timestamp.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        return f"[APYX {self.kind}] {self.title}\n{self.body}\nTime: {stamp}"


@dataclass
class AlertState:
    active: bool = False
    last_sent_at: datetime | None = None


class AlertEngine:
    def __init__(self, cooldown: timedelta) -> None:
        self.cooldown = cooldown
        self._states: dict[str, AlertState] = {}

    def evaluate(
        self,
        *,
        metric_key: str,
        breached: bool,
        alert_title: str,
        alert_body: str,
        recovery_title: str,
        recovery_body: str,
        now: datetime,
    ) -> AlertEvent | None:
        state = self._states.setdefault(metric_key, AlertState())
        if breached:
            if state.last_sent_at is None or now - state.last_sent_at >= self.cooldown:
                state.active = True
                state.last_sent_at = now
                return AlertEvent("ALERT", alert_title, alert_body, now)
            state.active = True
            return None

        if state.active:
            state.active = False
            state.last_sent_at = now
            return AlertEvent("RECOVERY", recovery_title, recovery_body, now)

        return None
```

- [ ] **Step 4: Implement Telegram sender**

Create `alert/telegram.py` with:

```python
from __future__ import annotations

from telegram import Bot

from alert.engine import AlertEvent


class TelegramSender:
    def __init__(self, bot_token: str, chat_id: str) -> None:
        self._bot = Bot(token=bot_token)
        self._chat_id = chat_id

    async def send(self, event: AlertEvent) -> None:
        await self._bot.send_message(chat_id=self._chat_id, text=event.telegram_text())
```

- [ ] **Step 5: Run alert tests**

Run:

```bash
pytest tests/test_alert_engine.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit alert engine**

Run:

```bash
git add alert/engine.py alert/telegram.py tests/test_alert_engine.py
git commit -m "feat: add alert engine"
```

Expected: commit succeeds.

---

### Task 3: Rolling Metric History

**Files:**
- Create: `history.py`
- Create: `tests/test_history.py`

- [ ] **Step 1: Write failing history tests**

Create `tests/test_history.py` with:

```python
from datetime import datetime, timedelta, timezone

from history import RollingMetricHistory, percent_change


def test_percent_change_returns_relative_delta() -> None:
    assert percent_change(current=90.0, baseline=100.0) == -0.10
    assert percent_change(current=110.0, baseline=100.0) == 0.10


def test_window_change_uses_sample_at_or_before_cutoff() -> None:
    history = RollingMetricHistory()
    now = datetime(2026, 4, 24, 15, 0, tzinfo=timezone.utc)
    history.record("tvl:apxUSD", 100.0, now - timedelta(minutes=65))
    history.record("tvl:apxUSD", 98.0, now - timedelta(minutes=55))

    change = history.window_change("tvl:apxUSD", current=85.0, now=now, window_minutes=60)

    assert change is not None
    assert change.baseline == 100.0
    assert change.current == 85.0
    assert change.percent == -0.15


def test_latest_change_uses_previous_sample() -> None:
    history = RollingMetricHistory()
    now = datetime(2026, 4, 24, 15, 0, tzinfo=timezone.utc)
    history.record("supply:apxUSD", 1000.0, now - timedelta(minutes=1))

    change = history.latest_change("supply:apxUSD", current=1125.0)

    assert change is not None
    assert change.percent == 0.125
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
pytest tests/test_history.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'history'`.

- [ ] **Step 3: Implement rolling history**

Create `history.py` with:

```python
from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass(frozen=True)
class MetricSample:
    value: float
    timestamp: datetime


@dataclass(frozen=True)
class MetricChange:
    baseline: float
    current: float
    percent: float


def percent_change(*, current: float, baseline: float) -> float:
    if baseline == 0:
        raise ValueError("baseline cannot be zero")
    return (current - baseline) / baseline


class RollingMetricHistory:
    def __init__(self, retention_minutes: int = 180) -> None:
        self._retention = timedelta(minutes=retention_minutes)
        self._samples: dict[str, deque[MetricSample]] = defaultdict(deque)

    def record(self, key: str, value: float, timestamp: datetime) -> None:
        samples = self._samples[key]
        samples.append(MetricSample(value=value, timestamp=timestamp))
        cutoff = timestamp - self._retention
        while samples and samples[0].timestamp < cutoff:
            samples.popleft()

    def latest_change(self, key: str, *, current: float) -> MetricChange | None:
        samples = self._samples.get(key)
        if not samples:
            return None
        baseline = samples[-1].value
        return MetricChange(baseline=baseline, current=current, percent=percent_change(current=current, baseline=baseline))

    def window_change(self, key: str, *, current: float, now: datetime, window_minutes: int) -> MetricChange | None:
        samples = self._samples.get(key)
        if not samples:
            return None
        cutoff = now - timedelta(minutes=window_minutes)
        baseline_sample = None
        for sample in samples:
            if sample.timestamp <= cutoff:
                baseline_sample = sample
            else:
                break
        if baseline_sample is None:
            return None
        return MetricChange(
            baseline=baseline_sample.value,
            current=current,
            percent=percent_change(current=current, baseline=baseline_sample.value),
        )
```

- [ ] **Step 4: Run history tests**

Run:

```bash
pytest tests/test_history.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit metric history**

Run:

```bash
git add history.py tests/test_history.py
git commit -m "feat: track rolling metric history"
```

Expected: commit succeeds.

---

### Task 4: STRC Price And apxUSD Peg Monitors

**Files:**
- Create: `monitors/strc_price.py`
- Create: `monitors/peg.py`
- Create: `tests/test_strc_price.py`
- Create: `tests/test_peg.py`

- [ ] **Step 1: Write failing STRC tests**

Create `tests/test_strc_price.py` with:

```python
from datetime import datetime, timedelta, timezone

from alert.engine import AlertEngine
from monitors.strc_price import evaluate_strc_price


def test_evaluate_strc_price_alerts_below_threshold() -> None:
    engine = AlertEngine(cooldown=timedelta(minutes=5))
    now = datetime(2026, 4, 24, 14, 30, tzinfo=timezone.utc)

    event = evaluate_strc_price(price=94.25, threshold=95.0, engine=engine, now=now)

    assert event is not None
    assert event.kind == "ALERT"
    assert "Current price: $94.25" in event.body
    assert "Drop from par: 5.75%" in event.body
    assert "Distance from par: $5.75" in event.body


def test_evaluate_strc_price_recovers_at_threshold() -> None:
    engine = AlertEngine(cooldown=timedelta(minutes=5))
    now = datetime(2026, 4, 24, 14, 30, tzinfo=timezone.utc)
    evaluate_strc_price(price=94.25, threshold=95.0, engine=engine, now=now)

    event = evaluate_strc_price(price=95.00, threshold=95.0, engine=engine, now=now + timedelta(minutes=1))

    assert event is not None
    assert event.kind == "RECOVERY"
```

- [ ] **Step 2: Write failing peg tests**

Create `tests/test_peg.py` with:

```python
from datetime import datetime, timedelta, timezone

from alert.engine import AlertEngine
from monitors.peg import evaluate_peg_price, parse_defillama_price


def test_parse_defillama_price_extracts_coin_price() -> None:
    payload = {
        "coins": {
            "ethereum:0x98A878b1Cd98131B271883B390f68D2c90674665": {
                "price": 0.9965
            }
        }
    }

    assert parse_defillama_price(payload, "ethereum:0x98A878b1Cd98131B271883B390f68D2c90674665") == 0.9965


def test_evaluate_peg_price_alerts_on_deviation() -> None:
    engine = AlertEngine(cooldown=timedelta(minutes=5))
    now = datetime(2026, 4, 24, 14, 30, tzinfo=timezone.utc)

    event = evaluate_peg_price(token_name="apxUSD", price=0.9965, threshold_pct=0.003, engine=engine, now=now)

    assert event is not None
    assert event.kind == "ALERT"
    assert "Price: $0.9965" in event.body
    assert "Deviation: -0.35%" in event.body
```

- [ ] **Step 3: Run tests to verify they fail**

Run:

```bash
pytest tests/test_strc_price.py tests/test_peg.py -q
```

Expected: FAIL with missing monitor modules.

- [ ] **Step 4: Implement STRC monitor**

Create `monitors/strc_price.py` with:

```python
from __future__ import annotations

from datetime import datetime

from aiohttp import ClientSession

from alert.engine import AlertEngine, AlertEvent


FINNHUB_QUOTE_URL = "https://finnhub.io/api/v1/quote"


async def fetch_strc_price(session: ClientSession, *, api_key: str, symbol: str) -> float:
    async with session.get(FINNHUB_QUOTE_URL, params={"symbol": symbol, "token": api_key}) as response:
        response.raise_for_status()
        payload = await response.json()
    return float(payload["c"])


def evaluate_strc_price(*, price: float, threshold: float, engine: AlertEngine, now: datetime) -> AlertEvent | None:
    breached = price < threshold
    drop_pct = (100.0 - price) / 100.0
    distance = 100.0 - price
    body = f"Current price: ${price:.2f}\nDrop from par: {drop_pct:.2%}\nDistance from par: ${distance:.2f}"
    recovery_body = f"Current price: ${price:.2f}\nDrop from par: {drop_pct:.2%}\nDistance from par: ${distance:.2f}"
    return engine.evaluate(
        metric_key="strc:price",
        breached=breached,
        alert_title="STRC Price Below Threshold",
        alert_body=body,
        recovery_title="STRC Price Recovered",
        recovery_body=recovery_body,
        now=now,
    )
```

- [ ] **Step 5: Implement peg monitor**

Create `monitors/peg.py` with:

```python
from __future__ import annotations

from datetime import datetime

from aiohttp import ClientSession

from alert.engine import AlertEngine, AlertEvent


DEFILLAMA_PRICE_URL = "https://coins.llama.fi/prices"


def coin_id(address: str) -> str:
    return f"ethereum:{address}"


async def fetch_peg_price(session: ClientSession, *, address: str) -> float:
    key = coin_id(address)
    async with session.get(DEFILLAMA_PRICE_URL, params={"coins": key}) as response:
        response.raise_for_status()
        payload = await response.json()
    return parse_defillama_price(payload, key)


def parse_defillama_price(payload: dict, key: str) -> float:
    return float(payload["coins"][key]["price"])


def evaluate_peg_price(
    *,
    token_name: str,
    price: float,
    threshold_pct: float,
    engine: AlertEngine,
    now: datetime,
) -> AlertEvent | None:
    deviation = price - 1.0
    breached = abs(deviation) > threshold_pct
    body = f"Price: ${price:.4f}\nDeviation: {deviation:+.2%}"
    return engine.evaluate(
        metric_key=f"peg:{token_name}",
        breached=breached,
        alert_title=f"{token_name} Peg Deviation",
        alert_body=body,
        recovery_title=f"{token_name} Peg Normal",
        recovery_body=body,
        now=now,
    )
```

- [ ] **Step 6: Run monitor tests**

Run:

```bash
pytest tests/test_strc_price.py tests/test_peg.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit STRC and peg monitors**

Run:

```bash
git add monitors/strc_price.py monitors/peg.py tests/test_strc_price.py tests/test_peg.py
git commit -m "feat: monitor strc price and apxusd peg"
```

Expected: commit succeeds.

---

### Task 5: Pendle Market Monitor

**Files:**
- Create: `monitors/pendle.py`
- Create: `tests/test_pendle.py`

- [ ] **Step 1: Write failing Pendle tests**

Create `tests/test_pendle.py` with:

```python
from datetime import datetime, timedelta, timezone

from alert.engine import AlertEngine
from history import RollingMetricHistory
from monitors.pendle import PendleMarketSnapshot, evaluate_pendle_market, parse_pendle_market


def test_parse_pendle_market_extracts_snapshot() -> None:
    payload = {"liquidity": 2500000, "impliedApy": 0.081, "ptPrice": 0.962}

    snapshot = parse_pendle_market("apxUSD", payload)

    assert snapshot == PendleMarketSnapshot(name="apxUSD", liquidity=2500000.0, implied_apy=0.081, pt_price=0.962)


def test_evaluate_pendle_market_alerts_on_liquidity_drop() -> None:
    history = RollingMetricHistory()
    engine = AlertEngine(cooldown=timedelta(minutes=5))
    now = datetime(2026, 4, 24, 15, 30, tzinfo=timezone.utc)
    history.record("pendle_liquidity:apxUSD", 1000000.0, now - timedelta(minutes=60))

    events = evaluate_pendle_market(
        snapshot=PendleMarketSnapshot("apxUSD", liquidity=890000.0, implied_apy=0.08, pt_price=0.96),
        liquidity_drop_pct=0.10,
        apy_change_pct=0.10,
        pt_price_change_pct=0.10,
        window_minutes=60,
        history=history,
        engine=engine,
        now=now,
    )

    assert len(events) == 1
    assert events[0].title == "Pendle apxUSD Liquidity Drop"
    assert "Current liquidity: $890,000.00" in events[0].body
    assert "1h change: -11.00%" in events[0].body
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
pytest tests/test_pendle.py -q
```

Expected: FAIL with `ModuleNotFoundError` for `monitors.pendle`.

- [ ] **Step 3: Implement Pendle monitor**

Create `monitors/pendle.py` with:

```python
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from aiohttp import ClientSession

from alert.engine import AlertEngine, AlertEvent
from history import RollingMetricHistory


@dataclass(frozen=True)
class PendleMarketSnapshot:
    name: str
    liquidity: float
    implied_apy: float
    pt_price: float


def market_url(address: str) -> str:
    return f"https://api-v2.pendle.finance/core/v1/markets/{address}"


async def fetch_pendle_market(session: ClientSession, *, name: str, address: str) -> PendleMarketSnapshot:
    async with session.get(market_url(address)) as response:
        response.raise_for_status()
        payload = await response.json()
    return parse_pendle_market(name, payload)


def parse_pendle_market(name: str, payload: dict) -> PendleMarketSnapshot:
    return PendleMarketSnapshot(
        name=name,
        liquidity=float(payload["liquidity"]),
        implied_apy=float(payload["impliedApy"]),
        pt_price=float(payload["ptPrice"]),
    )


def evaluate_pendle_market(
    *,
    snapshot: PendleMarketSnapshot,
    liquidity_drop_pct: float,
    apy_change_pct: float,
    pt_price_change_pct: float,
    window_minutes: int,
    history: RollingMetricHistory,
    engine: AlertEngine,
    now: datetime,
) -> list[AlertEvent]:
    events: list[AlertEvent] = []
    checks = [
        (
            "pendle_liquidity",
            snapshot.liquidity,
            liquidity_drop_pct,
            lambda pct: pct < -liquidity_drop_pct,
            f"Pendle {snapshot.name} Liquidity Drop",
            f"Pendle {snapshot.name} Liquidity Recovered",
            "Current liquidity",
            "${:,.2f}",
        ),
        (
            "pendle_apy",
            snapshot.implied_apy,
            apy_change_pct,
            lambda pct: abs(pct) > apy_change_pct,
            f"Pendle {snapshot.name} PT APY Change",
            f"Pendle {snapshot.name} PT APY Recovered",
            "Current APY",
            "{:.2%}",
        ),
        (
            "pendle_pt_price",
            snapshot.pt_price,
            pt_price_change_pct,
            lambda pct: abs(pct) > pt_price_change_pct,
            f"Pendle {snapshot.name} PT Price Change",
            f"Pendle {snapshot.name} PT Price Recovered",
            "Current PT price",
            "${:.4f}",
        ),
    ]
    for metric, value, _threshold, predicate, alert_title, recovery_title, label, value_format in checks:
        key = f"{metric}:{snapshot.name}"
        change = history.window_change(key, current=value, now=now, window_minutes=window_minutes)
        if change is None:
            history.record(key, value, now)
            continue
        body = f"{label}: {value_format.format(value)}\n1h change: {change.percent:+.2%}"
        event = engine.evaluate(
            metric_key=key,
            breached=predicate(change.percent),
            alert_title=alert_title,
            alert_body=body,
            recovery_title=recovery_title,
            recovery_body=body,
            now=now,
        )
        history.record(key, value, now)
        if event is not None:
            events.append(event)
    return events
```

- [ ] **Step 4: Run Pendle tests**

Run:

```bash
pytest tests/test_pendle.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit Pendle monitor**

Run:

```bash
git add monitors/pendle.py tests/test_pendle.py
git commit -m "feat: monitor pendle markets"
```

Expected: commit succeeds.

---

### Task 6: On-Chain Supply Monitor

**Files:**
- Create: `monitors/supply.py`
- Create: `tests/test_supply.py`

- [ ] **Step 1: Write failing supply tests**

Create `tests/test_supply.py` with:

```python
from datetime import datetime, timedelta, timezone

from alert.engine import AlertEngine
from history import RollingMetricHistory
from monitors.supply import evaluate_supply


def test_evaluate_supply_alerts_on_previous_sample_change() -> None:
    history = RollingMetricHistory()
    engine = AlertEngine(cooldown=timedelta(minutes=5))
    now = datetime(2026, 4, 24, 15, 30, tzinfo=timezone.utc)
    history.record("supply:apyUSD", 1000000.0, now - timedelta(minutes=1))

    event = evaluate_supply(
        token_name="apyUSD",
        supply=1110000.0,
        threshold_pct=0.10,
        history=history,
        engine=engine,
        now=now,
    )

    assert event is not None
    assert event.title == "apyUSD Supply Change"
    assert "Current supply: 1,110,000.00" in event.body
    assert "Change: +11.00%" in event.body
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
pytest tests/test_supply.py -q
```

Expected: FAIL with `ModuleNotFoundError` for `monitors.supply`.

- [ ] **Step 3: Implement supply monitor**

Create `monitors/supply.py` with:

```python
from __future__ import annotations

from datetime import datetime

from web3 import Web3

from alert.engine import AlertEngine, AlertEvent
from history import RollingMetricHistory


ERC20_ABI = [
    {"constant": True, "inputs": [], "name": "totalSupply", "outputs": [{"name": "", "type": "uint256"}], "type": "function"},
    {"constant": True, "inputs": [], "name": "decimals", "outputs": [{"name": "", "type": "uint8"}], "type": "function"},
]


def fetch_total_supply(web3: Web3, *, address: str) -> float:
    contract = web3.eth.contract(address=Web3.to_checksum_address(address), abi=ERC20_ABI)
    raw_supply = contract.functions.totalSupply().call()
    decimals = contract.functions.decimals().call()
    return float(raw_supply) / float(10**decimals)


def evaluate_supply(
    *,
    token_name: str,
    supply: float,
    threshold_pct: float,
    history: RollingMetricHistory,
    engine: AlertEngine,
    now: datetime,
) -> AlertEvent | None:
    key = f"supply:{token_name}"
    change = history.latest_change(key, current=supply)
    history.record(key, supply, now)
    if change is None:
        return None
    body = f"Current supply: {supply:,.2f}\nChange: {change.percent:+.2%}"
    return engine.evaluate(
        metric_key=key,
        breached=abs(change.percent) > threshold_pct,
        alert_title=f"{token_name} Supply Change",
        alert_body=body,
        recovery_title=f"{token_name} Supply Normal",
        recovery_body=body,
        now=now,
    )
```

- [ ] **Step 4: Run supply tests**

Run:

```bash
pytest tests/test_supply.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit supply monitor**

Run:

```bash
git add monitors/supply.py tests/test_supply.py
git commit -m "feat: monitor token supply"
```

Expected: commit succeeds.

---

### Task 7: TVL Monitor

**Files:**
- Create: `monitors/tvl.py`
- Create: `tests/test_tvl.py`

- [ ] **Step 1: Write failing TVL tests**

Create `tests/test_tvl.py` with:

```python
from datetime import datetime, timedelta, timezone

from alert.engine import AlertEngine
from history import RollingMetricHistory
from monitors.tvl import evaluate_tvl, parse_tvl


def test_parse_tvl_accepts_numeric_payload() -> None:
    assert parse_tvl(1234567.89) == 1234567.89


def test_parse_tvl_accepts_json_tvl_field() -> None:
    assert parse_tvl({"tvl": 1234567.89}) == 1234567.89


def test_evaluate_tvl_alerts_on_one_hour_change() -> None:
    history = RollingMetricHistory()
    engine = AlertEngine(cooldown=timedelta(minutes=5))
    now = datetime(2026, 4, 24, 15, 30, tzinfo=timezone.utc)
    history.record("tvl:apxUSD", 1000000.0, now - timedelta(minutes=60))

    event = evaluate_tvl(
        token_name="apxUSD",
        tvl=870000.0,
        threshold_pct=0.10,
        window_minutes=60,
        history=history,
        engine=engine,
        now=now,
    )

    assert event is not None
    assert event.title == "apxUSD TVL Change"
    assert "Current TVL: $870,000.00" in event.body
    assert "1h change: -13.00%" in event.body
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
pytest tests/test_tvl.py -q
```

Expected: FAIL with `ModuleNotFoundError` for `monitors.tvl`.

- [ ] **Step 3: Implement TVL monitor**

Create `monitors/tvl.py` with:

```python
from __future__ import annotations

from datetime import datetime

from aiohttp import ClientSession

from alert.engine import AlertEngine, AlertEvent
from history import RollingMetricHistory


async def fetch_tvl(session: ClientSession, *, url: str) -> float:
    async with session.get(url) as response:
        response.raise_for_status()
        payload = await response.json()
    return parse_tvl(payload)


def parse_tvl(payload: object) -> float:
    if isinstance(payload, int | float):
        return float(payload)
    if isinstance(payload, dict) and "tvl" in payload:
        return float(payload["tvl"])
    raise ValueError(f"Unsupported TVL payload: {payload!r}")


def evaluate_tvl(
    *,
    token_name: str,
    tvl: float,
    threshold_pct: float,
    window_minutes: int,
    history: RollingMetricHistory,
    engine: AlertEngine,
    now: datetime,
) -> AlertEvent | None:
    key = f"tvl:{token_name}"
    change = history.window_change(key, current=tvl, now=now, window_minutes=window_minutes)
    history.record(key, tvl, now)
    if change is None:
        return None
    body = f"Current TVL: ${tvl:,.2f}\n1h change: {change.percent:+.2%}"
    return engine.evaluate(
        metric_key=key,
        breached=abs(change.percent) > threshold_pct,
        alert_title=f"{token_name} TVL Change",
        alert_body=body,
        recovery_title=f"{token_name} TVL Normal",
        recovery_body=body,
        now=now,
    )
```

- [ ] **Step 4: Run TVL tests**

Run:

```bash
pytest tests/test_tvl.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit TVL monitor**

Run:

```bash
git add monitors/tvl.py tests/test_tvl.py
git commit -m "feat: monitor stablecoin tvl"
```

Expected: commit succeeds.

---

### Task 8: Scheduler And Runtime Wiring

**Files:**
- Create: `main.py`
- Modify: `config.py`

- [ ] **Step 1: Add environment loader test**

Append to `tests/test_config.py`:

```python
from config import load_env_config


def test_load_env_config_reads_required_values(monkeypatch) -> None:
    monkeypatch.setenv("FINNHUB_API_KEY", "finnhub-key")
    monkeypatch.setenv("TG_BOT_TOKEN", "telegram-token")
    monkeypatch.setenv("TG_CHAT_ID", "12345")
    monkeypatch.setenv("ETH_RPC_URL", "https://rpc.example")

    env = load_env_config()

    assert env.finnhub_api_key == "finnhub-key"
    assert env.telegram_bot_token == "telegram-token"
    assert env.telegram_chat_id == "12345"
    assert env.eth_rpc_url == "https://rpc.example"
```

- [ ] **Step 2: Run config test to verify it fails**

Run:

```bash
pytest tests/test_config.py -q
```

Expected: FAIL with `ImportError` for `load_env_config`.

- [ ] **Step 3: Extend config.py with env support**

Append these definitions to `config.py`:

```python
import os

from dotenv import load_dotenv


@dataclass(frozen=True)
class EnvConfig:
    finnhub_api_key: str
    telegram_bot_token: str
    telegram_chat_id: str
    eth_rpc_url: str


def _required_env(name: str) -> str:
    value = os.getenv(name)
    if value is None or value == "":
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def load_env_config(env_file: str | Path = ".env") -> EnvConfig:
    load_dotenv(env_file)
    return EnvConfig(
        finnhub_api_key=_required_env("FINNHUB_API_KEY"),
        telegram_bot_token=_required_env("TG_BOT_TOKEN"),
        telegram_chat_id=_required_env("TG_CHAT_ID"),
        eth_rpc_url=_required_env("ETH_RPC_URL"),
    )
```

- [ ] **Step 4: Create runtime entry point**

Create `main.py` with:

```python
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timedelta, timezone

from aiohttp import ClientSession
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from web3 import Web3

from alert.engine import AlertEngine, AlertEvent
from alert.telegram import TelegramSender
from config import AppConfig, EnvConfig, load_app_config, load_env_config
from history import RollingMetricHistory
from monitors.peg import fetch_peg_price, evaluate_peg_price
from monitors.pendle import evaluate_pendle_market, fetch_pendle_market
from monitors.strc_price import evaluate_strc_price, fetch_strc_price
from monitors.supply import evaluate_supply, fetch_total_supply
from monitors.tvl import evaluate_tvl, fetch_tvl


async def send_events(sender: TelegramSender, events: list[AlertEvent]) -> None:
    for event in events:
        await sender.send(event)


async def run_one_minute_checks(
    *,
    session: ClientSession,
    web3: Web3,
    settings: AppConfig,
    env: EnvConfig,
    history: RollingMetricHistory,
    engine: AlertEngine,
    sender: TelegramSender,
) -> None:
    now = datetime.now(timezone.utc)
    events: list[AlertEvent] = []

    peg_price = await fetch_peg_price(session, address=settings.peg.token.address)
    peg_event = evaluate_peg_price(
        token_name=settings.peg.token.name,
        price=peg_price,
        threshold_pct=settings.peg.threshold_pct,
        engine=engine,
        now=now,
    )
    if peg_event is not None:
        events.append(peg_event)

    for token in settings.supply.tokens:
        supply = fetch_total_supply(web3, address=token.address)
        supply_event = evaluate_supply(
            token_name=token.name,
            supply=supply,
            threshold_pct=settings.supply.threshold_pct,
            history=history,
            engine=engine,
            now=now,
        )
        if supply_event is not None:
            events.append(supply_event)

    await send_events(sender, events)


async def run_five_minute_checks(
    *,
    session: ClientSession,
    settings: AppConfig,
    env: EnvConfig,
    history: RollingMetricHistory,
    engine: AlertEngine,
    sender: TelegramSender,
) -> None:
    now = datetime.now(timezone.utc)
    events: list[AlertEvent] = []

    strc_price = await fetch_strc_price(session, api_key=env.finnhub_api_key, symbol=settings.finnhub.symbol)
    strc_event = evaluate_strc_price(
        price=strc_price,
        threshold=settings.finnhub.threshold_price,
        engine=engine,
        now=now,
    )
    if strc_event is not None:
        events.append(strc_event)

    for market in settings.pendle.markets:
        snapshot = await fetch_pendle_market(session, name=market.name, address=market.address)
        events.extend(
            evaluate_pendle_market(
                snapshot=snapshot,
                liquidity_drop_pct=settings.pendle.liquidity_drop_pct,
                apy_change_pct=settings.pendle.apy_change_pct,
                pt_price_change_pct=settings.pendle.pt_price_change_pct,
                window_minutes=settings.pendle.window_minutes,
                history=history,
                engine=engine,
                now=now,
            )
        )

    for token in settings.tvl.tokens:
        tvl = await fetch_tvl(session, url=token.url)
        tvl_event = evaluate_tvl(
            token_name=token.name,
            tvl=tvl,
            threshold_pct=settings.tvl.threshold_pct,
            window_minutes=settings.tvl.window_minutes,
            history=history,
            engine=engine,
            now=now,
        )
        if tvl_event is not None:
            events.append(tvl_event)

    await send_events(sender, events)


async def run_service(*, once: bool) -> None:
    settings = load_app_config()
    env = load_env_config()
    engine = AlertEngine(cooldown=timedelta(minutes=settings.alert.cooldown_minutes))
    history = RollingMetricHistory()
    sender = TelegramSender(env.telegram_bot_token, env.telegram_chat_id)
    web3 = Web3(Web3.HTTPProvider(env.eth_rpc_url))

    async with ClientSession() as session:
        if once:
            await run_one_minute_checks(session=session, web3=web3, settings=settings, env=env, history=history, engine=engine, sender=sender)
            await run_five_minute_checks(session=session, settings=settings, env=env, history=history, engine=engine, sender=sender)
            return

        scheduler = AsyncIOScheduler(timezone=timezone.utc)
        scheduler.add_job(
            run_one_minute_checks,
            "interval",
            minutes=1,
            kwargs={"session": session, "web3": web3, "settings": settings, "env": env, "history": history, "engine": engine, "sender": sender},
            max_instances=1,
            coalesce=True,
        )
        scheduler.add_job(
            run_five_minute_checks,
            "interval",
            minutes=5,
            kwargs={"session": session, "settings": settings, "env": env, "history": history, "engine": engine, "sender": sender},
            max_instances=1,
            coalesce=True,
        )
        scheduler.start()
        await asyncio.Event().wait()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="APYX stablecoin and Pendle pool monitor")
    parser.add_argument("--once", action="store_true", help="run one 1-minute cycle and one 5-minute cycle, then exit")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    asyncio.run(run_service(once=args.once))
```

- [ ] **Step 5: Run scheduler-related checks**

Run:

```bash
pytest tests/test_config.py -q
python -m compileall config.py history.py alert monitors main.py
```

Expected: tests pass and compileall prints no syntax errors.

- [ ] **Step 6: Commit scheduler**

Run:

```bash
git add config.py main.py tests/test_config.py
git commit -m "feat: wire scheduler runtime"
```

Expected: commit succeeds.

---

### Task 9: Full Verification And Operator Docs

**Files:**
- Create: `README.md`

- [ ] **Step 1: Create README**

Create `README.md` with:

````markdown
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
````

- [ ] **Step 2: Run full test suite**

Run:

```bash
. .venv/bin/activate
pytest -q
```

Expected: all tests pass.

- [ ] **Step 3: Run syntax check**

Run:

```bash
python -m compileall config.py history.py alert monitors main.py
```

Expected: no syntax errors.

- [ ] **Step 4: Run import smoke test**

Run:

```bash
python - <<'PY'
from config import load_app_config
from alert.engine import AlertEngine
from history import RollingMetricHistory

settings = load_app_config("config.yaml")
engine = AlertEngine.__name__
history = RollingMetricHistory.__name__
print(settings.finnhub.symbol, engine, history)
PY
```

Expected output:

```text
STRC AlertEngine RollingMetricHistory
```

- [ ] **Step 5: Commit docs and verification**

Run:

```bash
git add README.md
git commit -m "docs: document apyx monitor setup"
```

Expected: commit succeeds.

---

## Final Acceptance Checklist

- [ ] `pytest -q` passes.
- [ ] `python -m compileall config.py history.py alert monitors main.py` passes.
- [ ] `config.yaml` includes both APYX token addresses and both Pendle market addresses from the spec.
- [ ] `.env.example` includes `FINNHUB_API_KEY`, `TG_BOT_TOKEN`, `TG_CHAT_ID`, and `ETH_RPC_URL`.
- [ ] `main.py` schedules 1-minute checks for peg and supply.
- [ ] `main.py` schedules 5-minute checks for STRC, Pendle, and TVL.
- [ ] Alert engine enforces 5-minute same-metric cooldown.
- [ ] Alert engine emits one recovery after breach clears.
- [ ] README includes setup, run, one-cycle run, and test commands.

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-04-24-apyx-monitor.md`. Two execution options:

1. Subagent-Driven (recommended) - dispatch a fresh subagent per task, review between tasks, fast iteration
2. Inline Execution - execute tasks in this session using executing-plans, batch execution with checkpoints
