import psycopg2
from psycopg2 import sql
import os
from dotenv import load_dotenv

load_dotenv()

class Database:
    def __init__(self, host='localhost', port=5432, user='postgres', password='', dbname='hype_arbitrage'):
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.dbname = dbname
        self.conn = None

    def connect(self):
        """Establish connection to PostgreSQL database."""
        try:
            self.conn = psycopg2.connect(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                dbname=self.dbname
            )
            self.conn.autocommit = True
            print(f"✓ Connected to database: {self.dbname}")
            return self.conn
        except psycopg2.Error as e:
            print(f"✗ Database connection failed: {e}")
            raise

    def create_database(self):
        """Create the database if it doesn't exist."""
        try:
            conn = psycopg2.connect(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                dbname='postgres'
            )
            conn.autocommit = True
            cursor = conn.cursor()
            try:
                cursor.execute(sql.SQL("CREATE DATABASE {}").format(
                    sql.Identifier(self.dbname)
                ))
                print(f"✓ Database created: {self.dbname}")
            except psycopg2.Error as e:
                if 'already exists' in str(e):
                    print(f"✓ Database already exists: {self.dbname}")
                else:
                    raise
            cursor.close()
            conn.close()
        except psycopg2.Error as e:
            print(f"✗ Database creation failed: {e}")
            raise

    def init_schema(self):
        """Initialize database schema from schema.sql."""
        self.connect()
        schema_path = os.path.join(os.path.dirname(__file__), 'schema.sql')

        try:
            with open(schema_path, 'r') as f:
                schema = f.read()

            cursor = self.conn.cursor()
            cursor.execute(schema)
            cursor.close()
            print("✓ Schema initialized successfully")
        except Exception as e:
            print(f"✗ Schema initialization failed: {e}")
            raise

    def insert_price_trace(self, timestamp, binance_price, hl_oracle_price, asset_symbol='BTC'):
        """Insert a price trace entry."""
        cursor = self.conn.cursor()
        try:
            cursor.execute("""
                INSERT INTO price_traces (timestamp, binance_price, hl_oracle_price, asset_symbol)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (timestamp) DO UPDATE SET
                    binance_price = EXCLUDED.binance_price,
                    hl_oracle_price = EXCLUDED.hl_oracle_price
            """, (timestamp, binance_price, hl_oracle_price, asset_symbol))
            cursor.close()
        except psycopg2.Error as e:
            print(f"✗ Insert price trace failed: {e}")
            raise

    def insert_hl_fill(self, block_number, block_timestamp, user_address, coin, px, sz,
                       side, direction, fee=None, realized_pnl=None, crossed=None,
                       tid=None, builder_fee=None):
        """Insert a Hyperliquid fill record."""
        cursor = self.conn.cursor()
        try:
            fill_id = hash((block_number, block_timestamp, user_address, coin, tid)) & 0x7fffffffffffffff
            cursor.execute("""
                INSERT INTO hl_fills
                (fill_id, block_number, block_timestamp, user_address, coin, px, sz,
                 side, direction, fee, realized_pnl, crossed, tid, builder_fee)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (fill_id) DO NOTHING
            """, (fill_id, block_number, block_timestamp, user_address, coin, px, sz,
                  side, direction, fee, realized_pnl, crossed, tid, builder_fee))
            cursor.close()
        except psycopg2.Error as e:
            print(f"✗ Insert hl_fill failed: {e}")
            raise

    def insert_binance_candle(self, symbol, open_time, close_time, open_price, close_price,
                             high_price, low_price, volume, quote_volume, interval='1s'):
        """Insert a Binance candle record."""
        cursor = self.conn.cursor()
        try:
            cursor.execute("""
                INSERT INTO binance_candles
                (symbol, open_time, close_time, open_price, close_price, high_price,
                 low_price, volume, quote_volume, interval)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (symbol, open_time) DO UPDATE SET
                    close_price = EXCLUDED.close_price,
                    high_price = EXCLUDED.high_price,
                    low_price = EXCLUDED.low_price,
                    volume = EXCLUDED.volume,
                    quote_volume = EXCLUDED.quote_volume
            """, (symbol, open_time, close_time, open_price, close_price, high_price,
                  low_price, volume, quote_volume, interval))
            cursor.close()
        except psycopg2.Error as e:
            print(f"✗ Insert binance_candle failed: {e}")
            raise

    def get_binance_candles(self, symbol='BTCUSDT', limit=1000000):
        """Fetch stored Binance candles ordered by time, for price-trace alignment."""
        cursor = self.conn.cursor()
        try:
            cursor.execute("""
                SELECT open_time, close_price
                FROM binance_candles
                WHERE symbol = %s
                ORDER BY open_time ASC
                LIMIT %s
            """, (symbol, limit))
            rows = cursor.fetchall()
            cursor.close()
            return rows
        except psycopg2.Error as e:
            print(f"✗ Fetch binance_candles failed: {e}")
            raise

    def delete_price_traces(self, asset_symbol='BTC'):
        """Remove existing price traces for an asset before a fresh sync."""
        cursor = self.conn.cursor()
        try:
            cursor.execute("DELETE FROM price_traces WHERE asset_symbol = %s", (asset_symbol,))
            cursor.close()
        except psycopg2.Error as e:
            print(f"✗ Delete price_traces failed: {e}")
            raise

    def get_hl_fills(self, coin='BTC', limit=5000000):
        """Fetch Hyperliquid fills ordered by timestamp, for price-trace alignment."""
        cursor = self.conn.cursor()
        try:
            cursor.execute("""
                SELECT block_timestamp, px
                FROM hl_fills
                WHERE coin = %s
                ORDER BY block_timestamp ASC
                LIMIT %s
            """, (coin, limit))
            rows = cursor.fetchall()
            cursor.close()
            return rows
        except psycopg2.Error as e:
            print(f"✗ Fetch hl_fills failed: {e}")
            raise

    def get_price_traces(self, asset_symbol='BTC', limit=1000):
        """Fetch price traces for analysis."""
        cursor = self.conn.cursor()
        try:
            cursor.execute("""
                SELECT timestamp, binance_price, hl_oracle_price
                FROM price_traces
                WHERE asset_symbol = %s
                ORDER BY timestamp DESC
                LIMIT %s
            """, (asset_symbol, limit))
            rows = cursor.fetchall()
            cursor.close()
            return rows
        except psycopg2.Error as e:
            print(f"✗ Fetch price traces failed: {e}")
            raise

    def insert_simulation_state(self, state):
        """Insert a simulation state record."""
        cursor = self.conn.cursor()
        try:
            cursor.execute("""
                INSERT INTO simulation_state
                (timestamp, retail_order_price, retail_order_size, hl_oracle_price,
                 binance_price, hft_sniper_engaged, hft_execution_price, retail_loss)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (state.timestamp, float(state.retail_order_price), float(state.retail_order_size),
                  float(state.hl_oracle_price), float(state.binance_price),
                  state.hft_sniper_engaged, float(state.hft_execution_price) if state.hft_execution_price else None,
                  float(state.retail_loss) if state.retail_loss else None))
            cursor.close()
        except psycopg2.Error as e:
            print(f"✗ Insert simulation state failed: {e}")
            raise

    def close(self):
        """Close database connection."""
        if self.conn:
            self.conn.close()
            print("✓ Database connection closed")
