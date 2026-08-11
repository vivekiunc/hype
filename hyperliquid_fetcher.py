import httpx
import json
import asyncio
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from datetime import datetime

@dataclass
class HLFill:
    block_number: int
    block_timestamp: int
    user_address: str
    coin: str
    px: str  # Decimal string
    sz: str  # Decimal string
    side: str  # 'A' or 'B'
    direction: str
    fee: Optional[str] = None
    realized_pnl: Optional[str] = None
    crossed: Optional[bool] = None
    tid: Optional[str] = None
    builder_fee: Optional[str] = None

class HyperliquidFetcher:
    """Fetches Hyperliquid fills data via HyperCore streaming API."""

    BASE_URL = "https://portal.sqd.dev/datasets/hyperliquid-fills/stream"
    TIMEOUT = 30.0

    def __init__(self, timeout: float = TIMEOUT):
        self.timeout = timeout

    async def stream_fills(
        self,
        from_block: int,
        to_block: Optional[int] = None,
        coins: Optional[List[str]] = None,
        callback=None
    ) -> List[HLFill]:
        """
        Stream fills data from Hyperliquid via HyperCore API.

        Args:
            from_block: Starting block number
            to_block: Ending block number (optional, streams until dataset height if omitted)
            coins: List of coin symbols to filter (e.g., ['BTC', 'ETH'])
            callback: Async callback function to process each fill as it arrives

        Returns:
            List of HLFill objects
        """
        fills = []

        # Build fills filter
        fills_filter = []
        if coins:
            fills_filter = [{"coin": coins}]

        payload = {
            "type": "hyperliquidFills",
            "fromBlock": from_block,
            "fields": {
                "block": {
                    "number": True,
                    "timestamp": True
                },
                "fill": {
                    "user": True,
                    "coin": True,
                    "px": True,
                    "sz": True,
                    "side": True,
                    "dir": True,
                    "fee": True,
                    "closedPnl": True,
                    "crossed": True,
                    "tid": True,
                    "builderFee": True
                }
            },
            "fills": fills_filter
        }

        if to_block is not None:
            payload["toBlock"] = to_block

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                async with client.stream("POST", self.BASE_URL, json=payload) as response:
                    if response.status_code != 200:
                        raise Exception(f"API returned status {response.status_code}")

                    async for line in response.aiter_lines():
                        if not line.strip():
                            continue

                        block_data = json.loads(line)
                        block_number = block_data.get("header", {}).get("number")
                        block_timestamp = block_data.get("header", {}).get("timestamp")

                        for fill in block_data.get("fills", []):
                            hl_fill = HLFill(
                                block_number=block_number,
                                block_timestamp=block_timestamp,
                                user_address=fill.get("user", ""),
                                coin=fill.get("coin", ""),
                                px=fill.get("px", ""),
                                sz=fill.get("sz", ""),
                                side=fill.get("side", ""),
                                direction=fill.get("dir", ""),
                                fee=fill.get("fee"),
                                realized_pnl=fill.get("closedPnl"),
                                crossed=fill.get("crossed"),
                                tid=fill.get("tid"),
                                builder_fee=fill.get("builderFee")
                            )
                            fills.append(hl_fill)

                            # Call callback if provided
                            if callback:
                                await callback(hl_fill)

        except Exception as e:
            print(f"✗ Error streaming fills: {e}")
            raise

        return fills

    async def fetch_fills_batch(
        self,
        from_block: int,
        to_block: Optional[int] = None,
        coins: Optional[List[str]] = None
    ) -> List[HLFill]:
        """
        Fetch fills data synchronously (blocking until complete).

        Args:
            from_block: Starting block number
            to_block: Ending block number
            coins: List of coin symbols to filter

        Returns:
            List of HLFill objects
        """
        return await self.stream_fills(from_block, to_block, coins)

    def fetch_fills_sync(
        self,
        from_block: int,
        to_block: Optional[int] = None,
        coins: Optional[List[str]] = None
    ) -> List[HLFill]:
        """
        Synchronous wrapper for fetching fills.

        Args:
            from_block: Starting block number
            to_block: Ending block number
            coins: List of coin symbols to filter

        Returns:
            List of HLFill objects
        """
        return asyncio.run(self.fetch_fills_batch(from_block, to_block, coins))
