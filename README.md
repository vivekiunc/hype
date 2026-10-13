# Oracle Latency & Rate-Limiting Arbitrage Research (HIP-3)

A research simulation framework for studying adversarial interactions between retail liquidity providers and HFT arbitrageurs exploiting oracle latency on Hyperliquid perpetual futures.

## Architecture Overview

```
┌─────────────────────────────────────────────┐
│   PostgreSQL Database                       │
│   • price_traces (Binance vs HL oracle)    │
│   • hl_fills (Trade execution data)        │
│   • binance_candles (Reference prices)     │
│   • simulation_state (Results)             │
└──────────────────┬──────────────────────────┘
                   │
        ┌──────────┴──────────┐
        ▼                     ▼
   Data Collection      Simulation Engine
   • Hyperliquid SDK    • Retail Maker Agent
   • Binance API        • HFT Sniper Agent
   • Synchronization    • Arbitrage Detection
```

## Components

### 1. Data Collection Layer

#### `hyperliquid_fetcher.py`
Fetches Hyperliquid fills data via HyperCore streaming API.

**Features:**
- Streams trade execution data (fills) with millisecond precision
- Extracts price, size, side, and builder routing information
- Async/streaming support for efficient data ingestion
- Real-time callback processing

**Key Classes:**
- `HLFill`: Dataclass representing a single trade execution
- `HyperliquidFetcher`: Async API client for HyperCore

#### `binance_fetcher.py`
Fetches Binance reference price data for ground truth comparison.

**Features:**
- Historical K-line (candlestick) data at multiple intervals
- Current price snapshots for real-time alignment
- Date-range queries with automatic batching
- Rate limiting to comply with API policies

**Key Classes:**
- `BinanceCandle`: OHLCV data structure
- `BinanceFetcher`: API client for Binance public data

### 2. Data Synchronization

#### `data_synchronizer.py`
Orchestrates data collection from both sources and creates synchronized price traces.

**Key Methods:**
- `sync_hl_fills()`: Fetch Hyperliquid trade data
- `sync_binance_candles()`: Fetch Binance reference prices
- `sync_price_traces()`: Align prices at each timestamp
- `continuous_sync()`: Ongoing sync for live research

### 3. Database Layer

#### `db.py`
PostgreSQL wrapper managing all data persistence.

**Schema Tables:**
1. **price_traces**: Synchronized market prices
   - timestamp (PK)
   - binance_price (true market price)
   - hl_oracle_price (Hyperliquid oracle price)
   - asset_symbol

2. **hl_fills**: Raw Hyperliquid trade data
   - block_number, timestamp
   - user_address, coin
   - price (px), size (sz), side
   - fee, realized_pnl
   - crossed (taker/maker flag), tid

3. **binance_candles**: Reference price candles
   - symbol, open_time, close_time
   - OHLCV data
   - interval

4. **simulation_state**: Agent interaction results
   - timestamp
   - retail_order_price, retail_order_size
   - hl_oracle_price, binance_price
   - hft_sniper_engaged
   - hft_execution_price, retail_loss

### 4. Simulation Engine

#### `simulation_engine.py`
Runs the agent-based simulation with two competing actors.

**Agents:**

1. **RetailMakerAgent**
   - Assumes HL oracle price is fair
   - Places symmetric limit orders (bid/ask spread)
   - Default spread: 10 basis points
   - Unaware of latency arbitrage

2. **HFTSniperAgent**
   - Observes true Binance price (milliseconds ahead)
   - Monitors retail maker's stale orders
   - Executes profitable snipes when spread widens
   - Captures all arbitrage profit

**Simulation Flow:**
```python
For each timestamp:
  1. Retail places orders based on (stale) HL oracle price
  2. HFT checks if true price ≠ retail prices by >threshold
  3. If profitable, HFT executes snipe
  4. Record state: engagement, execution, retail loss
```

### 5. Main Orchestrator

#### `main.py`
Command-line interface and orchestration logic.

## Installation

### Prerequisites
- Python 3.8+
- PostgreSQL 12+

### Setup

```bash
# Install dependencies
pip install -r requirements.txt

# Configure database (edit .env if using non-defaults)
export DB_HOST=localhost
export DB_USER=postgres
export DB_PASSWORD=your_password

# Initialize database
python -c "from db import Database; db = Database(); db.create_database(); db.init_schema()"
```

## Usage

### Full Workflow (Data Collection + Simulation)

```bash
# Collect fresh data and run simulation
python main.py --mode full --collect-data

# With custom parameters
python main.py --mode full --collect-data \
  --hl-from-block 900000000 \
  --hl-to-block 900000100 \
  --binance-days 7 \
  --db-host localhost
```

### Simulation Only (Using Existing Data)

```bash
# Run simulation against data in database
python main.py --mode simulate
```

### Data Collection Only

```bash
# Fetch and sync data without simulation
python main.py --mode collect --collect-data --binance-days 1
```

## Output

### Console Output
Real-time progress and statistics:
```
=== Initializing Database ===
✓ Connected to database: hype_arbitrage
✓ Schema initialized successfully

=== Collecting Data ===
1. Fetching Hyperliquid fills (blocks 900000000-900000100)...
   ✓ Synced 1000 fills

2. Fetching Binance reference prices (last 1 day(s))...
   ✓ Binance sync complete: 1440 candles

=== Running Simulation ===
Running simulation with 1000 price points...
✓ Simulation complete:
  - Total snipes: 234
  - Total retail loss: 45.23456789
  - Avg loss per snipe: 0.19333333
```

### Results File: `simulation_results.csv`

```csv
timestamp,retail_price,hl_oracle_price,binance_price,hft_engaged,hft_execution_price,retail_loss
1721270400,45234.50,45233.00,45235.00,true,45233.00,1.50
1721270460,45240.25,45239.50,45242.00,true,45239.50,2.75
...
```

## Latest Simulation Stats

Computed from the current `simulation_results.csv` (600 price points, default parameters: 10 bps retail spread, 5 bps arbitrage threshold, 100ms HFT reaction time):

| Metric | Value | Definition |
|---|---|---|
| Total timesteps | 600 | Number of synchronized price points simulated — each row is one moment where retail quotes are placed and checked against the true price. |
| Total snipes | 10 | Count of timesteps where the HFT sniper agent found retail's quote stale enough (vs. Binance) to profitably trade against it. |
| Snipe frequency | 1.67% | `total_snipes / total_timesteps`. Share of all timesteps that resulted in a successful snipe — a proxy for how often oracle latency is actually exploitable. |
| Total retail loss | $529.42 | Sum of `(true_price - retail_quote) × size` across all snipes — the cumulative USD value transferred from the retail maker to the HFT sniper. |
| Avg loss per snipe | $52.94 | `total_retail_loss / total_snipes`. Average size of a single adverse-selection event when one does occur. |
| Avg price diff (Binance vs HL oracle) | 5.49 bps | Mean absolute basis-point gap between the HL oracle price and the true Binance price across all timesteps — the raw latency/staleness the oracle exhibits, independent of whether it was exploited. |
| Time span covered | 109,860s (~30.5 hours) | Wall-clock duration spanned by the 600 timesteps in this dataset (`max(timestamp) - min(timestamp)`). |

A snipe only occurs when the oracle/Binance price diff exceeds the arbitrage threshold (5 bps default) *and* retail's quote (based on the stale oracle price) is on the wrong side of the true price — so snipe frequency will typically be lower than the raw price-diff frequency, since not every divergence is large enough to clear the threshold.

**What this means for the research question:** yes — these results support the existence of a viable latency-arbitrage strategy against HL's oracle pricing. The oracle lags the true market by ~5.5 bps on average, and in roughly 1 in 60 timesteps that lag is large enough (and on the right side) for an HFT sniper to pick off a retail maker's stale quote at an average profit of ~$53 per occurrence. A real HFT desk could run this as a pure latency-sniping strategy: watch Binance as the leading price signal, hold a model of HL's oracle update lag, and submit marketable orders the instant the gap crosses the arbitrage threshold — capturing the retail maker's spread with near-zero directional risk since the "true" price is already known at execution time. The frequency is low per-asset-pair here, but it is systematic and repeatable rather than random, which is exactly the signature of an exploitable microstructure edge rather than noise; the practical takeaway for retail makers on HL is that quoting directly off the oracle price (rather than a faster external reference) leaves a persistent, harvestable edge on the table.

Regenerate with:

```bash
python main.py --mode simulate
```

## Research Methodology

### Key Metrics

1. **Snipe Frequency**: % of timesteps where HFT executes
2. **Retail Loss**: Total USD loss across all snipes
3. **Price Differential**: Basis points between Binance and HL oracle
4. **Arbitrage Threshold**: Minimum profitable spread (5-10 bps typical)

### Experimental Parameters to Vary

```python
# Retail spread assumption (basis points)
RetailMakerAgent(spread_bps=10.0)  # Try: 5, 10, 20, 50

# HFT reaction time (milliseconds)
HFTSniperAgent(reaction_time_ms=100)  # Try: 50, 100, 200, 500

# Minimum profitable spread
run_simulation(arbitrage_threshold_bps=5.0)  # Try: 1, 5, 10, 20

# Asset selection
coins=['BTC', 'ETH']  # Try: ['SOL'], single vs multi-asset
```

## Advanced Usage

### Continuous Data Sync

```python
from data_synchronizer import DataSynchronizer
from db import Database

db = Database()
db.connect()
syncer = DataSynchronizer(db)

# Runs indefinitely, polling both APIs
import asyncio
asyncio.run(syncer.continuous_sync(
    hl_from_block=900000000,
    binance_symbol='BTCUSDT',
    poll_interval=60  # seconds
))
```

### Custom Analysis

```python
from simulation_engine import SimulationEngine
from db import Database

db = Database()
db.connect()
engine = SimulationEngine(db)

# Fetch data and run simulation
traces = db.get_price_traces(asset_symbol='BTC', limit=5000)
engine.run_simulation(price_traces=traces)

# Export and analyze
engine.export_results('my_results.csv')
results = engine.analyze_results()
print(f"Snipe frequency: {results['snipe_frequency_pct']:.2f}%")
```

## Database Schema Reference

### Indexes

All tables are indexed on frequently-queried dimensions:
- `price_traces`: timestamp, asset_symbol
- `hl_fills`: block_number, block_timestamp, coin, user_address, tid
- `binance_candles`: symbol + open_time, open_time alone
- `simulation_state`: timestamp, hft_sniper_engaged

Query performance is O(log n) for timestamp lookups on large datasets.

## API Documentation

### HyperCore Fills API

The Hyperliquid HyperCore API streams real-time fills data:

```
POST https://portal.sqd.dev/datasets/hyperliquid-fills/stream

Request:
{
  "type": "hyperliquidFills",
  "fromBlock": <starting block>,
  "toBlock": <ending block>,  # optional
  "fields": { ... }          # field selector
}

Response: JSON-lines stream of blocks with fills
```

See `hyperliquid_fetcher.py` for full integration.

### Binance API

Public REST API (no authentication required):

```
GET https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=1m&limit=1000
GET https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT
```

See `binance_fetcher.py` for implementation.

## Troubleshooting

### PostgreSQL Connection Failed
```bash
# Check if PostgreSQL is running
psql -h localhost -U postgres -d postgres

# Create database manually if needed
createdb hype_arbitrage
```

### Hyperliquid API Unavailable
The simulator will gracefully skip Hyperliquid data collection. Use `--mode simulate` to run against existing database data.

### Out of Memory
Reduce batch sizes in `data_synchronizer.py`:
```python
sync_hl_fills(from_block=current_block, to_block=current_block + 10)  # was 100
```

## References

- [HyperCore Fills API Documentation](https://squid.subsquid.io/)
- [Binance Public API](https://binance-docs.github.io/apidocs/)
- [Hyperliquid Perpetuals](https://hyperliquid.gitbook.io/hyperliquid-docs/)

## License

This research framework is provided as-is for academic and experimental purposes.

## Contact

For questions or research collaboration, reach out to the Hype research team.
