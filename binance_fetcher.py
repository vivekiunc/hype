import requests
import time
from typing import Optional, List, Dict, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

@dataclass
class BinanceCandle:
    symbol: str
    open_time: int
    close_time: int
    open_price: str
    close_price: str
    high_price: str
    low_price: str
    volume: str
    quote_volume: str

class BinanceFetcher:
    """Fetches historical price data from Binance API."""

    BASE_URL = "https://api.binance.us/api/v3"
    RATE_LIMIT_DELAY = 0.1  # Seconds between requests

    def __init__(self, symbols: List[str] = None):
        self.symbols = symbols or ['BTCUSDT', 'ETHUSDT']
        self.last_request_time = 0

    def _rate_limit(self):
        """Enforce rate limiting to avoid hitting Binance API limits."""
        elapsed = time.time() - self.last_request_time
        if elapsed < self.RATE_LIMIT_DELAY:
            time.sleep(self.RATE_LIMIT_DELAY - elapsed)
        self.last_request_time = time.time()

    def fetch_klines(
        self,
        symbol: str,
        interval: str = '1s',
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        limit: int = 1000
    ) -> List[BinanceCandle]:
        """
        Fetch K-line (candlestick) data from Binance.

        Args:
            symbol: Trading pair (e.g., 'BTCUSDT')
            interval: Kline interval ('1s', '1m', '5m', etc.)
            start_time: Start time in milliseconds (optional)
            end_time: End time in milliseconds (optional)
            limit: Number of candles to fetch (max 1000)

        Returns:
            List of BinanceCandle objects
        """
        self._rate_limit()

        params = {
            'symbol': symbol,
            'interval': interval,
            'limit': limit
        }

        if start_time:
            params['startTime'] = start_time
        if end_time:
            params['endTime'] = end_time

        try:
            response = requests.get(
                f"{self.BASE_URL}/klines",
                params=params,
                timeout=20
            )
            response.raise_for_status()

            candles = []
            for kline in response.json():
                candle = BinanceCandle(
                    symbol=symbol,
                    open_time=int(kline[0]),
                    close_time=int(kline[6]),
                    open_price=kline[1],
                    close_price=kline[4],
                    high_price=kline[2],
                    low_price=kline[3],
                    volume=kline[7],
                    quote_volume=kline[8]
                )
                candles.append(candle)

            return candles

        except requests.RequestException as e:
            print(f"✗ Binance API error for {symbol}: {e}")
            raise

    def fetch_current_price(self, symbol: str) -> Decimal:
        """
        Fetch current price for a symbol.

        Args:
            symbol: Trading pair (e.g., 'BTCUSDT')

        Returns:
            Current price as Decimal
        """
        self._rate_limit()

        try:
            response = requests.get(
                f"{self.BASE_URL}/ticker/price",
                params={'symbol': symbol},
                timeout=10
            )
            response.raise_for_status()
            return Decimal(response.json()['price'])
        except requests.RequestException as e:
            print(f"✗ Binance API error for {symbol}: {e}")
            raise

    def fetch_historical_range(
        self,
        symbol: str,
        interval: str = '1m',
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        days_back: int = 7
    ) -> List[BinanceCandle]:
        """
        Fetch historical data for a date range.

        Args:
            symbol: Trading pair
            interval: Kline interval
            start_date: Start date (YYYY-MM-DD) or None to use days_back
            end_date: End date (YYYY-MM-DD) or None for today
            days_back: Days to go back if start_date not provided

        Returns:
            List of BinanceCandle objects
        """
        if end_date:
            end_dt = datetime.strptime(end_date, '%Y-%m-%d')
        else:
            end_dt = datetime.utcnow()

        if start_date:
            start_dt = datetime.strptime(start_date, '%Y-%m-%d')
        else:
            start_dt = end_dt - timedelta(days=days_back)

        all_candles = []
        current_dt = start_dt

        while current_dt < end_dt:
            start_ms = int(current_dt.timestamp() * 1000)
            next_dt = current_dt + timedelta(hours=1)
            end_ms = int(next_dt.timestamp() * 1000)

            # A transient timeout on one hourly chunk shouldn't abort every
            # remaining hour in the range, so retry a couple of times before
            # giving up on just this chunk and moving on.
            candles = None
            for attempt in range(3):
                try:
                    candles = self.fetch_klines(
                        symbol=symbol,
                        interval=interval,
                        start_time=start_ms,
                        end_time=end_ms,
                        limit=1000
                    )
                    break
                except Exception as e:
                    print(f"✗ Error fetching historical data ({current_dt.date()} "
                          f"{current_dt.hour:02d}:00, attempt {attempt + 1}/3): {e}")
                    time.sleep(1)

            if candles is None:
                current_dt = next_dt
                continue

            all_candles.extend(candles)
            current_dt = next_dt

        return all_candles

    def get_price_at_time(
        self,
        symbol: str,
        target_time_ms: int,
        interval: str = '1m'
    ) -> Optional[Tuple[str, str]]:
        """
        Get open/close price for a specific time.

        Args:
            symbol: Trading pair
            target_time_ms: Target time in milliseconds
            interval: Kline interval to search

        Returns:
            Tuple of (open_price, close_price) or None if not found
        """
        # Fetch candles around the target time
        start_ms = target_time_ms - (60 * 60 * 1000)  # 1 hour before
        end_ms = target_time_ms + (60 * 60 * 1000)    # 1 hour after

        try:
            candles = self.fetch_klines(
                symbol=symbol,
                interval=interval,
                start_time=start_ms,
                end_time=end_ms,
                limit=100
            )

            for candle in candles:
                if candle.open_time <= target_time_ms <= candle.close_time:
                    return (candle.open_price, candle.close_price)

            return None

        except Exception as e:
            print(f"✗ Error fetching price at time: {e}")
            return None
