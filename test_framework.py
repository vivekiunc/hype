#!/usr/bin/env python3
"""
Test and validate the Oracle Latency Arbitrage simulation framework.
This script runs self-contained tests without requiring external APIs.
"""

import sys
from decimal import Decimal
from datetime import datetime, timedelta

def test_retail_maker_agent():
    """Test retail maker order placement logic."""
    from simulation_engine import RetailMakerAgent

    print("Testing RetailMakerAgent...")
    agent = RetailMakerAgent(spread_bps=10.0)

    fair_price = Decimal('45000.00')
    bid, ask = agent.place_order(fair_price, Decimal('1.0'))

    assert bid < fair_price < ask, "Bid should be below fair price, ask above"
    assert ask - bid > 0, "Ask-bid spread should be positive"

    # Check spread is approximately 10 bps (0.2%)
    # Note: 10 bps with multiplier of (1 + 10/10000) = 1.001 gives ~0.2% spread
    spread_pct = float((ask - bid) / fair_price * 100)
    assert 0.15 < spread_pct < 0.25, f"Spread should be ~0.2%, got {spread_pct}%"

    print(f"  ✓ Order placement: bid={bid}, ask={ask}, spread={spread_pct:.3f}%")

def test_hft_sniper_agent():
    """Test HFT sniper arbitrage detection and execution."""
    from simulation_engine import HFTSniperAgent

    print("Testing HFTSniperAgent...")
    agent = HFTSniperAgent(reaction_time_ms=100)

    # Scenario 1: Retail orders are stale, should snipe
    retail_bid = Decimal('45000.00')
    retail_ask = Decimal('45010.00')
    true_price = Decimal('45500.00')  # Huge gap!

    should_snipe = agent.should_snipe(retail_bid, retail_ask, true_price, 5.0)
    assert should_snipe, "Should snipe when true price is far above retail ask"
    print(f"  ✓ Detects snipe opportunity (gap={float(true_price - retail_ask):.2f})")

    # Scenario 2: Fair market, shouldn't snipe
    retail_bid = Decimal('45000.00')
    retail_ask = Decimal('45010.00')
    true_price = Decimal('45005.00')

    should_snipe = agent.should_snipe(retail_bid, retail_ask, true_price, 5.0)
    assert not should_snipe, "Should not snipe in fair market"
    print(f"  ✓ Avoids false positives in fair market")

    # Test execution in profitable scenario
    retail_bid = Decimal('44900.00')
    retail_ask = Decimal('44950.00')
    true_price = Decimal('45500.00')

    execution_price, retail_loss = agent.execute_snipe(retail_bid, retail_ask, true_price, Decimal('1.0'))
    assert execution_price == retail_ask, "Should execute at retail ask when buying from them"
    assert retail_loss > 0, "Retail should lose money"
    assert retail_loss == true_price - retail_ask, "Loss should be price difference × size"
    print(f"  ✓ Execution: price={execution_price}, retail_loss={retail_loss:.2f}")

def test_simulation_engine():
    """Test simulation engine with synthetic data."""
    from simulation_engine import SimulationEngine
    from db import Database

    print("Testing SimulationEngine...")

    # Create in-memory database (mock)
    class MockDB:
        def insert_simulation_state(self, state):
            pass

    engine = SimulationEngine(MockDB())

    # Create synthetic price traces
    # Scenario: Hyperliquid oracle lags Binance by 1-2%
    traces = []
    base_price = Decimal('45000.00')
    for i in range(100):
        timestamp = 1721270400 + (i * 60)
        binance_price = base_price + Decimal(i)  # Price increases
        hl_oracle_price = binance_price * Decimal('0.9985')  # 1.5% lag

        traces.append((timestamp, binance_price, hl_oracle_price))

    states = engine.run_simulation(
        price_traces=traces,
        retail_order_size=Decimal('1.0'),
        arbitrage_threshold_bps=5.0
    )

    assert len(states) == len(traces), "Should have state for each trace"
    assert any(s.hft_sniper_engaged for s in states), "Should detect at least one snipe"

    results = engine.analyze_results()
    assert results['total_snipes'] > 0, "Should detect snipes"
    print(f"  ✓ Simulation ran: {results['total_snipes']} snipes detected")
    print(f"    - Snipe frequency: {results['snipe_frequency_pct']:.1f}%")
    print(f"    - Retail loss: {results['total_retail_loss']:.2f}")

def test_database_schema():
    """Verify database schema definitions."""
    import os

    print("Testing Database Schema...")
    schema_file = os.path.join(os.path.dirname(__file__), 'schema.sql')

    with open(schema_file, 'r') as f:
        schema = f.read()

    # Verify key tables exist in schema
    required_tables = [
        'price_traces',
        'hl_fills',
        'binance_candles',
        'simulation_state',
        'arbitrage_opportunities'
    ]

    for table in required_tables:
        assert f'CREATE TABLE' in schema and table in schema, f"Table {table} not in schema"

    print(f"  ✓ Schema contains {len(required_tables)} required tables")
    print(f"    - Tables: {', '.join(required_tables)}")

def test_binance_fetcher():
    """Test Binance data structure without making API calls."""
    from binance_fetcher import BinanceFetcher, BinanceCandle

    print("Testing BinanceFetcher...")

    # Create mock candle
    candle = BinanceCandle(
        symbol='BTCUSDT',
        open_time=1721270400000,
        close_time=1721270460000,
        open_price='45000.00',
        close_price='45010.00',
        high_price='45050.00',
        low_price='44950.00',
        volume='123.45',
        quote_volume='5554231.50'
    )

    assert candle.symbol == 'BTCUSDT'
    assert Decimal(candle.close_price) > Decimal(candle.open_price)
    print(f"  ✓ BinanceCandle structure valid")
    print(f"    - Symbol: {candle.symbol}")
    print(f"    - Open: {candle.open_price}, Close: {candle.close_price}")

def test_hyperliquid_fetcher():
    """Test Hyperliquid data structure without making API calls."""
    from hyperliquid_fetcher import HLFill

    print("Testing HyperliquidFetcher...")

    fill = HLFill(
        block_number=900000100,
        block_timestamp=1721270400,
        user_address='0x1234567890abcdef',
        coin='BTC',
        px='45000.50',
        sz='0.1',
        side='B',
        direction='Open Long',
        fee='0.0045',
        realized_pnl=None,
        crossed=True,
        tid='tid_12345',
        builder_fee='0.0001'
    )

    assert fill.coin == 'BTC'
    assert fill.side in ['A', 'B']
    assert Decimal(fill.px) > 0
    assert Decimal(fill.sz) > 0
    print(f"  ✓ HLFill structure valid")
    print(f"    - Asset: {fill.coin}")
    print(f"    - Price: {fill.px}, Size: {fill.sz}")
    print(f"    - Side: {fill.side} (B=buy), Direction: {fill.direction}")

def run_all_tests():
    """Run all framework tests."""
    print("=" * 60)
    print("Oracle Latency Arbitrage Framework - Test Suite")
    print("=" * 60)
    print()

    tests = [
        test_retail_maker_agent,
        test_hft_sniper_agent,
        test_simulation_engine,
        test_database_schema,
        test_binance_fetcher,
        test_hyperliquid_fetcher,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            test()
            passed += 1
            print()
        except AssertionError as e:
            print(f"  ✗ FAILED: {e}\n")
            failed += 1
        except Exception as e:
            print(f"  ✗ ERROR: {e}\n")
            failed += 1

    print("=" * 60)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 60)

    return failed == 0

if __name__ == '__main__':
    success = run_all_tests()
    sys.exit(0 if success else 1)
