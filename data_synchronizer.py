import asyncio
import bisect
from typing import Optional, List
from db import Database
from hyperliquid_fetcher import HyperliquidFetcher, HLFill
from binance_fetcher import BinanceFetcher
from decimal import Decimal
import time

class DataSynchronizer:
    """Synchronizes price data from Hyperliquid oracle vs Binance reference price."""

    def __init__(self, db: Database, hl_fetcher: HyperliquidFetcher = None,
                 binance_fetcher: BinanceFetcher = None):
        self.db = db
        self.hl_fetcher = hl_fetcher or HyperliquidFetcher()
        self.binance_fetcher = binance_fetcher or BinanceFetcher()
        self.fill_count = 0
        self.candle_count = 0

    async def sync_hl_fills(
        self,
        from_block: int,
        to_block: Optional[int] = None,
        coins: Optional[List[str]] = None
    ):
        """
        Fetch Hyperliquid fills and store in database.

        Args:
            from_block: Starting block number
            to_block: Ending block number
            coins: List of coin symbols to fetch
        """
        print(f"Starting Hyperliquid fills sync from block {from_block}...")

        async def on_fill(fill: HLFill):
            """Callback to process each fill as it arrives."""
            try:
                self.db.insert_hl_fill(
                    block_number=fill.block_number,
                    block_timestamp=fill.block_timestamp,
                    user_address=fill.user_address,
                    coin=fill.coin,
                    px=fill.px,
                    sz=fill.sz,
                    side=fill.side,
                    direction=fill.direction,
                    fee=fill.fee,
                    realized_pnl=fill.realized_pnl,
                    crossed=fill.crossed,
                    tid=fill.tid,
                    builder_fee=fill.builder_fee
                )
                self.fill_count += 1

                if self.fill_count % 1000 == 0:
                    print(f"  ✓ Synced {self.fill_count} fills")

            except Exception as e:
                print(f"✗ Error processing fill: {e}")

        try:
            fills = await self.hl_fetcher.stream_fills(
                from_block=from_block,
                to_block=to_block,
                coins=coins,
                callback=on_fill
            )
            print(f"✓ Hyperliquid sync complete: {len(fills)} fills")

        except Exception as e:
            print(f"✗ Hyperliquid sync failed: {e}")
            raise

    def sync_binance_candles(
        self,
        symbol: str = 'BTCUSDT',
        interval: str = '1m',
        days_back: int = 7
    ):
        """
        Fetch Binance candles and store in database.

        Args:
            symbol: Trading pair
            interval: Kline interval
            days_back: Number of days to fetch
        """
        print(f"Starting Binance candles sync for {symbol}...")

        try:
            candles = self.binance_fetcher.fetch_historical_range(
                symbol=symbol,
                interval=interval,
                days_back=days_back
            )

            for candle in candles:
                self.db.insert_binance_candle(
                    symbol=symbol,
                    open_time=candle.open_time,
                    close_time=candle.close_time,
                    open_price=candle.open_price,
                    close_price=candle.close_price,
                    high_price=candle.high_price,
                    low_price=candle.low_price,
                    volume=candle.volume,
                    quote_volume=candle.quote_volume,
                    interval=interval
                )
                self.candle_count += 1

            print(f"✓ Binance sync complete: {self.candle_count} candles")

        except Exception as e:
            print(f"✗ Binance sync failed: {e}")
            raise

    def sync_price_traces(self, asset_symbol: str = 'BTC', max_lag_ms: int = 5000):
        """
        Create synchronized price traces by pairing each Binance candle with
        the real Hyperliquid fill closest to it in time (nearest-neighbor
        join on block_timestamp, which HyperCore reports in milliseconds —
        same unit as Binance's open_time).

        Args:
            asset_symbol: Asset symbol (e.g., 'BTC', 'ETH')
            max_lag_ms: Max gap allowed between a candle and its nearest
                fill for them to be paired; wider gaps are dropped rather
                than faked
        """
        print(f"Syncing price traces for {asset_symbol}...")

        try:
            # Use already-synced Binance candles from the database rather
            # than re-fetching (sync_binance_candles already populated them;
            # hitting the API a second time here just doubles rate-limit
            # exposure for no benefit).
            binance_symbol = f'{asset_symbol}USDT'
            candles = self.db.get_binance_candles(symbol=binance_symbol)

            if not candles:
                print("✗ No Binance candles found")
                return

            # Real Hyperliquid fill prices to use as the oracle side
            hl_fills = self.db.get_hl_fills(coin=asset_symbol)
            if not hl_fills:
                print(f"✗ No Hyperliquid fills found for {asset_symbol} in the "
                      f"database — sync fills first with a block range that "
                      f"overlaps this time window")
                return

            fill_timestamps = [ts for ts, _ in hl_fills]

            # Each sync fully replaces this asset's traces so stale rows
            # from a previous (possibly mismatched) run can't leak into
            # a simulation that reads them later.
            self.db.delete_price_traces(asset_symbol)

            trace_count = 0
            skipped = 0
            for candle_ts_ms, close_price in candles:
                binance_price = float(close_price)

                idx = bisect.bisect_left(fill_timestamps, candle_ts_ms)
                candidate_idxs = [i for i in (idx - 1, idx) if 0 <= i < len(fill_timestamps)]
                nearest_idx = min(candidate_idxs, key=lambda i: abs(fill_timestamps[i] - candle_ts_ms))
                lag_ms = abs(fill_timestamps[nearest_idx] - candle_ts_ms)

                if lag_ms > max_lag_ms:
                    skipped += 1
                    continue

                hl_price = float(hl_fills[nearest_idx][1])

                self.db.insert_price_trace(
                    timestamp=candle_ts_ms // 1000,  # Convert to seconds
                    binance_price=binance_price,
                    hl_oracle_price=hl_price,
                    asset_symbol=asset_symbol
                )
                trace_count += 1

            print(f"✓ Price traces synced: {trace_count} records "
                  f"({skipped} candles skipped, no fill within {max_lag_ms}ms)")

            if trace_count == 0:
                print("  ⚠ No candles were paired with a real fill. Your "
                      "--hl-from-block/--hl-to-block range likely doesn't "
                      "overlap the Binance --binance-days window — use a "
                      "recent block range covering the same time period.")

        except Exception as e:
            print(f"✗ Price trace sync failed: {e}")
            raise

    async def continuous_sync(
        self,
        hl_from_block: int,
        binance_symbol: str = 'BTCUSDT',
        poll_interval: int = 60
    ):
        """
        Continuously sync data from both sources.

        Args:
            hl_from_block: Starting Hyperliquid block
            binance_symbol: Binance trading pair
            poll_interval: Seconds between polls
        """
        print("Starting continuous data sync...")

        current_block = hl_from_block

        while True:
            try:
                # Sync Hyperliquid fills
                await self.sync_hl_fills(
                    from_block=current_block,
                    to_block=current_block + 100,
                    coins=['BTC', 'ETH']
                )

                # Sync Binance candles (recent only)
                self.sync_binance_candles(
                    symbol=binance_symbol,
                    interval='1m',
                    days_back=1
                )

                # Create synchronized traces
                self.sync_price_traces(asset_symbol=binance_symbol.replace('USDT', ''))

                current_block += 100
                print(f"✓ Sync cycle complete. Next block: {current_block}")

                await asyncio.sleep(poll_interval)

            except Exception as e:
                print(f"✗ Continuous sync error: {e}")
                await asyncio.sleep(poll_interval)
