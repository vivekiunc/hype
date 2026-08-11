from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
from decimal import Decimal
import bisect
from db import Database

@dataclass
class SimulationState:
    """Represents the state at a single time step."""
    timestamp: int
    retail_order_price: Decimal
    retail_order_size: Decimal
    hl_oracle_price: Decimal
    binance_price: Decimal
    hft_sniper_engaged: bool
    hft_execution_price: Optional[Decimal] = None
    retail_loss: Optional[Decimal] = None

class RetailMakerAgent:
    """Simulates a retail liquidity provider unaware of latency arbitrage."""

    def __init__(self, spread_bps: float = 10.0):
        """
        Initialize retail maker.

        Args:
            spread_bps: Maker spread in basis points (e.g., 10 = 0.1%)
        """
        self.spread_bps = spread_bps  # Belief about fair spread

    def place_order(self, fair_price: Decimal, size: Decimal) -> Tuple[Decimal, Decimal]:
        """
        Place limit order based on believed fair price.

        The retail maker assumes:
        - HyperLiquid's oracle price reflects true market price
        - This spread is sufficient for profitable market making

        Returns:
            Tuple of (bid_price, ask_price) around oracle price
        """
        spread_multiplier = 1 + (self.spread_bps / 10000)

        bid_price = fair_price / Decimal(spread_multiplier)
        ask_price = fair_price * Decimal(spread_multiplier)

        return (bid_price, ask_price)

class HFTSniperAgent:
    """Simulates an HFT agent exploiting oracle latency."""

    def __init__(self, reaction_time_ms: int = 100):
        """
        Initialize HFT sniper.

        Args:
            reaction_time_ms: Milliseconds of latency advantage
        """
        self.reaction_time_ms = reaction_time_ms

    def should_snipe(
        self,
        retail_bid: Decimal,
        retail_ask: Decimal,
        true_price: Decimal,
        arbitrage_threshold_bps: float = 5.0
    ) -> bool:
        """
        Determine if arbitrage opportunity exists.

        Args:
            retail_bid: Retail maker's bid price
            retail_ask: Retail maker's ask price
            true_price: True Binance price
            arbitrage_threshold_bps: Min profitable spread (basis points)

        Returns:
            True if profitable snipe exists
        """
        threshold = Decimal(1 + (arbitrage_threshold_bps / 10000))

        # Profitable if we can buy from retail and sell at true price
        if retail_ask < true_price / threshold:
            return True

        # Profitable if we can sell to retail and buy at true price
        if retail_bid > true_price * threshold:
            return True

        return False

    def execute_snipe(
        self,
        retail_bid: Decimal,
        retail_ask: Decimal,
        true_price: Decimal,
        retail_size: Decimal
    ) -> Tuple[Decimal, Decimal]:
        """
        Execute snipe and calculate retail loss.

        Returns:
            Tuple of (execution_price, retail_loss)
        """
        # Buy from retail at their ask (they lose)
        if retail_ask < true_price:
            execution_price = retail_ask
            retail_loss = (true_price - retail_ask) * retail_size
            return (execution_price, retail_loss)

        # Sell to retail at their bid (they lose)
        if retail_bid > true_price:
            execution_price = retail_bid
            retail_loss = (retail_bid - true_price) * retail_size
            return (execution_price, retail_loss)

        return (true_price, Decimal(0))

class SimulationEngine:
    """Main simulation engine orchestrating retail vs HFT interaction."""

    def __init__(self, db: Database):
        self.db = db
        self.retail_agent = RetailMakerAgent(spread_bps=10.0)
        self.hft_agent = HFTSniperAgent(reaction_time_ms=100)
        self.simulation_states: List[SimulationState] = []

    def run_simulation(
        self,
        price_traces: List[Tuple[int, Decimal, Decimal]],
        retail_order_size: Decimal = Decimal('1.0'),
        arbitrage_threshold_bps: float = 5.0
    ) -> List[SimulationState]:
        """
        Run simulation across time using price traces.

        Args:
            price_traces: List of (timestamp, binance_price, hl_oracle_price)
            retail_order_size: Size of retail orders
            arbitrage_threshold_bps: Minimum spread for HFT snipe

        Returns:
            List of SimulationState objects
        """
        print(f"Running simulation with {len(price_traces)} price points...")

        self.simulation_states = []
        total_retail_loss = Decimal(0)
        snipes_executed = 0

        for timestamp, binance_price, hl_oracle_price in price_traces:
            # Retail maker believes HL oracle is fair price
            bid_price, ask_price = self.retail_agent.place_order(
                fair_price=hl_oracle_price,
                size=retail_order_size
            )

            # HFT sees true price (Binance) and retail's stale prices
            hft_should_snipe = self.hft_agent.should_snipe(
                retail_bid=bid_price,
                retail_ask=ask_price,
                true_price=binance_price,
                arbitrage_threshold_bps=arbitrage_threshold_bps
            )

            hft_execution_price = None
            retail_loss = None

            if hft_should_snipe:
                hft_execution_price, retail_loss = self.hft_agent.execute_snipe(
                    retail_bid=bid_price,
                    retail_ask=ask_price,
                    true_price=binance_price,
                    retail_size=retail_order_size
                )
                total_retail_loss += retail_loss
                snipes_executed += 1

            state = SimulationState(
                timestamp=timestamp,
                retail_order_price=(bid_price + ask_price) / 2,
                retail_order_size=retail_order_size,
                hl_oracle_price=hl_oracle_price,
                binance_price=binance_price,
                hft_sniper_engaged=hft_should_snipe,
                hft_execution_price=hft_execution_price,
                retail_loss=retail_loss
            )

            self.simulation_states.append(state)

            # Store in database
            try:
                self.db.insert_simulation_state(state)
            except Exception as e:
                print(f"✗ Error storing simulation state: {e}")

        print(f"✓ Simulation complete:")
        print(f"  - Total snipes: {snipes_executed}")
        print(f"  - Total retail loss: {total_retail_loss:.8f}")
        print(f"  - Avg loss per snipe: {total_retail_loss / snipes_executed if snipes_executed > 0 else 0:.8f}")

        return self.simulation_states

    def analyze_results(self) -> Dict:
        """Analyze simulation results."""
        if not self.simulation_states:
            return {}

        total_snipes = sum(1 for s in self.simulation_states if s.hft_sniper_engaged)
        total_loss = sum(s.retail_loss or Decimal(0) for s in self.simulation_states)
        avg_price_diff = sum(
            abs(s.binance_price - s.hl_oracle_price)
            for s in self.simulation_states
        ) / len(self.simulation_states)

        return {
            'total_timesteps': len(self.simulation_states),
            'total_snipes': total_snipes,
            'snipe_frequency_pct': (total_snipes / len(self.simulation_states)) * 100,
            'total_retail_loss': float(total_loss),
            'avg_loss_per_snipe': float(
                total_loss / total_snipes if total_snipes > 0 else 0
            ),
            'avg_price_diff_bps': float(
                (avg_price_diff / self.simulation_states[0].binance_price) * 10000
                if self.simulation_states else 0
            )
        }

    def export_results(self, output_file: str = 'simulation_results.csv'):
        """Export simulation results to CSV."""
        import csv

        try:
            with open(output_file, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([
                    'timestamp', 'retail_price', 'hl_oracle_price',
                    'binance_price', 'hft_engaged', 'hft_execution_price',
                    'retail_loss'
                ])

                for state in self.simulation_states:
                    writer.writerow([
                        state.timestamp,
                        float(state.retail_order_price),
                        float(state.hl_oracle_price),
                        float(state.binance_price),
                        state.hft_sniper_engaged,
                        float(state.hft_execution_price) if state.hft_execution_price else '',
                        float(state.retail_loss) if state.retail_loss else ''
                    ])

            print(f"✓ Results exported to {output_file}")

        except Exception as e:
            print(f"✗ Export failed: {e}")
            raise
