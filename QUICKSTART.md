# Oracle Latency Arbitrage - Quick Start Guide

## 5-Minute Setup

### Step 1: Install Dependencies
```bash
pip install -r requirements.txt
```

### Step 2: Database Setup (Optional but Recommended)

If you have PostgreSQL installed:
```bash
# Create database
createdb hype_arbitrage

# Or run setup script
bash setup.sh
```

If you don't have PostgreSQL, the simulation can still run with mock data.

### Step 3: Run Tests
Verify everything works:
```bash
python test_framework.py
```

### Step 4: Run the Simulation
```bash
# Run with simulation only (no API calls needed)
python main.py --mode simulate
```

## What Happens

The simulation demonstrates how HFT arbitrageurs exploit oracle latency:

1. **Retail Maker**: Places limit orders assuming Hyperliquid oracle price is fair
   - Posts symmetric bid/ask spread (default 10 bps)
   - Unaware of latency advantage

2. **HFT Sniper**: Observes true Binance price (ahead of oracle)
   - Detects profitable gaps in retail orders
   - Executes snipes when spread > threshold (5 bps)
   - Captures arbitrage profit

3. **Results**: Quantifies retail losses from stale pricing

## Next Steps

### Collect Real Data
```bash
# Fetch from Hyperliquid and Binance (requires API access)
python main.py --mode full --collect-data --binance-days 1
```

### Customize Simulation
Edit parameters in `main.py`:
```python
# Retail spread awareness (basis points)
RetailMakerAgent(spread_bps=20)  # More conservative

# HFT reaction time (milliseconds)
HFTSniperAgent(reaction_time_ms=50)  # Faster sniper

# Minimum profitable spread
run_simulation(arbitrage_threshold_bps=10)  # Higher threshold
```

### Analyze Results
```bash
# Export CSV results
python main.py --mode simulate
# Opens: simulation_results.csv

# Custom analysis
python -c "
import pandas as pd
results = pd.read_csv('simulation_results.csv')
print(f'Snipes: {results[\"hft_engaged\"].sum()}')
print(f'Total loss: {results[\"retail_loss\"].sum():.2f}')
"
```

## Project Files

- **main.py** - Entry point with CLI interface
- **simulation_engine.py** - Core agent logic
- **db.py** - Database layer
- **hyperliquid_fetcher.py** - HyperCore API integration
- **binance_fetcher.py** - Binance API integration
- **data_synchronizer.py** - Orchestrates data collection
- **schema.sql** - Database schema
- **test_framework.py** - Validation tests

## API Documentation

### HyperCore Fills API
Real-time trade execution data from Hyperliquid:
```bash
curl -X POST https://portal.sqd.dev/datasets/hyperliquid-fills/stream \
  -H 'Content-Type: application/json' \
  -d '{
    "type": "hyperliquidFills",
    "fromBlock": 900000000,
    "toBlock": 900000100
  }'
```

### Binance API
Public historical price data:
```bash
# Get 1-minute candles
curl 'https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=1m&limit=100'

# Get current price
curl 'https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT'
```

## Troubleshooting

**"No module named psycopg2"**
- Install: `pip install psycopg2-binary`
- Or skip PostgreSQL: simulation works with mock data

**"Connection refused" from PostgreSQL**
- Is PostgreSQL running? `psql`
- Or use Docker: `docker run -d -e POSTGRES_PASSWORD=pw -p 5432:5432 postgres`

**Hyperliquid API times out**
- Normal - public API can be rate-limited
- Results still valid with mock data
- Run simulation-only mode: `--mode simulate`

## Example Output

```
=== Running Simulation ===
Running simulation with 1000 price points...
✓ Simulation complete:
  - Total snipes: 342
  - Total retail loss: 12456.78
  - Avg loss per snipe: 36.42

=== Simulation Results ===
Total Timesteps: 1000
Total Snipes: 342
Snipe Frequency Pct: 34.20
Total Retail Loss: 12456.78
Avg Loss Per Snipe: 36.42
Avg Price Diff Bps: 42.50
```

## Research Extensions

Try varying these parameters:

### 1. Measure Retail Awareness Impact
```python
for spread_bps in [5, 10, 20, 50]:
    agent = RetailMakerAgent(spread_bps=spread_bps)
    # Run simulation and compare losses
```

### 2. Study HFT Reaction Time
```python
for reaction_ms in [10, 50, 100, 500]:
    agent = HFTSniperAgent(reaction_time_ms=reaction_ms)
    # Analyze how latency advantage translates to profit
```

### 3. Cross-Asset Analysis
```python
for asset in ['BTC', 'ETH', 'SOL']:
    traces = db.get_price_traces(asset_symbol=asset)
    engine.run_simulation(price_traces=traces)
    # Compare snipe frequency across assets
```

## Contact & Support

This framework is designed for research and educational purposes. For questions about Hyperliquid, Binance APIs, or the simulation methodology, see the main README.md.

---

**Happy researching! 🚀**
