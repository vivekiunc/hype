#!/usr/bin/env python3
"""
Oracle Latency Arbitrage Research Simulation (HIP-3)

Main entry point for data collection and simulation execution.
"""

import asyncio
import argparse
import sys
from decimal import Decimal
from dotenv import load_dotenv
from db import Database
from data_synchronizer import DataSynchronizer
from simulation_engine import SimulationEngine
from hyperliquid_fetcher import HyperliquidFetcher
from binance_fetcher import BinanceFetcher

load_dotenv()

def initialize_database(db: Database):
    """Initialize PostgreSQL database and schema."""
    print("\n=== Initializing Database ===")
    try:
        db.create_database()
        db.connect()
        db.init_schema()
        print("✓ Database initialization complete\n")
    except Exception as e:
        print(f"✗ Database initialization failed: {e}")
        sys.exit(1)

def collect_data(
    db: Database,
    hl_from_block: int = 900000000,
    hl_to_block: int = 900000100,
    binance_days: int = 1
):
    """Collect price data from both Hyperliquid and Binance."""
    print("\n=== Collecting Data ===")

    syncer = DataSynchronizer(db)

    # Sync Hyperliquid fills
    print(f"\n1. Fetching Hyperliquid fills (blocks {hl_from_block}-{hl_to_block})...")
    try:
        asyncio.run(syncer.sync_hl_fills(
            from_block=hl_from_block,
            to_block=hl_to_block,
            coins=['BTC', 'ETH']
        ))
    except Exception as e:
        print(f"✗ Hyperliquid sync failed: {e}")
        print("  (This is expected if API is unavailable)")

    # Sync Binance reference prices
    print(f"\n2. Fetching Binance reference prices (last {binance_days} day(s))...")
    try:
        syncer.sync_binance_candles(
            symbol='BTCUSDT',
            interval='1m',
            days_back=binance_days
        )
    except Exception as e:
        print(f"✗ Binance sync failed: {e}")

    # Create synchronized price traces
    print("\n3. Synchronizing price traces...")
    try:
        syncer.sync_price_traces(asset_symbol='BTC')
    except Exception as e:
        print(f"✗ Price trace sync failed: {e}")

    print("\n✓ Data collection phase complete")

def run_simulation(db: Database):
    """Run the arbitrage simulation."""
    print("\n=== Running Simulation ===")

    class MockDB:
        def insert_simulation_state(self, state):
            pass

    price_traces = []

    if db.conn is not None:
        try:
            rows = db.get_price_traces(asset_symbol='BTC', limit=1000)
            # rows come back most-recent-first; simulation needs chronological order
            price_traces = [
                (int(ts), Decimal(str(binance_price)), Decimal(str(hl_oracle_price)))
                for ts, binance_price, hl_oracle_price in reversed(rows)
            ]
        except Exception as e:
            print(f"✗ Failed to load price traces from database: {e}")

    if not price_traces:
        db = MockDB()
        print("⚠ No real price traces found — falling back to synthetic data")
        print("  (real Binance/Hyperliquid data must be collected first via --collect-data)")

        # Create synthetic data: BTC price with 0.5% oracle lag
        base_price = Decimal('45000.00')

        for i in range(1000):
            timestamp = 1721270400 + (i * 60)
            # Binance price increases gradually
            binance_price = base_price + Decimal(i * 0.5)
            # HL oracle lags by ~0.5%
            hl_oracle_price = binance_price * Decimal('0.995')
            price_traces.append((timestamp, binance_price, hl_oracle_price))

    engine = SimulationEngine(db)

    try:
        print(f"\nRunning simulation with {len(price_traces)} price points...")
        print("Agents:")
        print("  - Retail Maker: Unaware of latency, posts fair-spread orders")
        print("  - HFT Sniper: Exploits oracle lag, executes profitable snipes\n")

        states = engine.run_simulation(
            price_traces=price_traces,
            retail_order_size=Decimal('1.0'),
            arbitrage_threshold_bps=5.0
        )

        # Analyze results
        results = engine.analyze_results()
        print("\n=== Simulation Results ===")
        for key, value in results.items():
            if isinstance(value, float):
                print(f"{key.replace('_', ' ').title()}: {value:.2f}")
            else:
                print(f"{key.replace('_', ' ').title()}: {value}")

        # Export to CSV
        engine.export_results('simulation_results.csv')

    except Exception as e:
        print(f"✗ Simulation failed: {e}")
        import traceback
        traceback.print_exc()

def main():
    parser = argparse.ArgumentParser(
        description='Oracle Latency Arbitrage Research Simulation (HIP-3)'
    )
    parser.add_argument(
        '--mode',
        choices=['full', 'collect', 'simulate'],
        default='full',
        help='Execution mode'
    )
    parser.add_argument(
        '--collect-data',
        action='store_true',
        help='Collect fresh data from APIs'
    )
    parser.add_argument(
        '--hl-from-block',
        type=int,
        default=900000000,
        help='Hyperliquid starting block'
    )
    parser.add_argument(
        '--hl-to-block',
        type=int,
        default=900000100,
        help='Hyperliquid ending block'
    )
    parser.add_argument(
        '--binance-days',
        type=int,
        default=1,
        help='Days of Binance data to fetch'
    )
    parser.add_argument(
        '--db-host',
        default='localhost',
        help='PostgreSQL host'
    )
    parser.add_argument(
        '--db-port',
        type=int,
        default=5432,
        help='PostgreSQL port'
    )
    parser.add_argument(
        '--db-user',
        default='postgres',
        help='PostgreSQL user'
    )
    parser.add_argument(
        '--db-password',
        default='',
        help='PostgreSQL password'
    )
    parser.add_argument(
        '--db-name',
        default='hype_arbitrage',
        help='PostgreSQL database name'
    )

    args = parser.parse_args()

    # Initialize database
    db = Database(
        host=args.db_host,
        port=args.db_port,
        user=args.db_user,
        password=args.db_password,
        dbname=args.db_name
    )

    try:
        if args.mode != 'simulate':
            initialize_database(db)

        # Run phases based on mode
        if args.mode in ['full', 'collect'] and args.collect_data:
            initialize_database(db)
            collect_data(
                db=db,
                hl_from_block=args.hl_from_block,
                hl_to_block=args.hl_to_block,
                binance_days=args.binance_days
            )

        if args.mode in ['full', 'simulate']:
            if args.mode == 'simulate':
                print("\n=== Running Simulation (Database-Free Mode) ===")
            run_simulation(db)

        print("\n" + "="*50)
        print("✓ Simulation framework ready for analysis")
        print("  Results: simulation_results.csv")
        print("="*50)

    finally:
        db.close()

if __name__ == '__main__':
    main()
