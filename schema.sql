-- Price traces: Synchronized market prices from Binance vs Hyperliquid
CREATE TABLE IF NOT EXISTS price_traces (
    timestamp BIGINT PRIMARY KEY,
    binance_price REAL,
    hl_oracle_price REAL,
    asset_symbol VARCHAR(50) DEFAULT 'BTC',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_trace_time ON price_traces(timestamp);
CREATE INDEX IF NOT EXISTS idx_trace_asset ON price_traces(asset_symbol);

-- Hyperliquid fills: Raw trade execution data
CREATE TABLE IF NOT EXISTS hl_fills (
    fill_id BIGINT PRIMARY KEY,
    block_number BIGINT NOT NULL,
    block_timestamp BIGINT NOT NULL,
    user_address VARCHAR(255) NOT NULL,
    coin VARCHAR(50) NOT NULL,
    px DECIMAL(20, 8) NOT NULL,
    sz DECIMAL(20, 8) NOT NULL,
    side VARCHAR(1) NOT NULL,  -- 'A' for ask (sell), 'B' for bid (buy)
    direction VARCHAR(20) NOT NULL,  -- Open Long, Close Long, Open Short, Close Short
    fee DECIMAL(20, 8),
    realized_pnl DECIMAL(20, 8),
    crossed BOOLEAN,  -- true = taker, false = maker
    tid VARCHAR(100),  -- Trade ID for pairing maker/taker
    builder_fee DECIMAL(20, 8),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_fills_block ON hl_fills(block_number);
CREATE INDEX IF NOT EXISTS idx_fills_timestamp ON hl_fills(block_timestamp);
CREATE INDEX IF NOT EXISTS idx_fills_coin ON hl_fills(coin);
CREATE INDEX IF NOT EXISTS idx_fills_user ON hl_fills(user_address);
CREATE INDEX IF NOT EXISTS idx_fills_tid ON hl_fills(tid);

-- Binance candles: Reference price data
CREATE TABLE IF NOT EXISTS binance_candles (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(50) NOT NULL,
    open_time BIGINT NOT NULL,
    close_time BIGINT NOT NULL,
    open_price DECIMAL(20, 8),
    close_price DECIMAL(20, 8),
    high_price DECIMAL(20, 8),
    low_price DECIMAL(20, 8),
    volume DECIMAL(20, 8),
    quote_volume DECIMAL(20, 8),
    interval VARCHAR(10) NOT NULL DEFAULT '1s',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, open_time)
);

CREATE INDEX IF NOT EXISTS idx_candles_symbol_time ON binance_candles(symbol, open_time);
CREATE INDEX IF NOT EXISTS idx_candles_time ON binance_candles(open_time);

-- Arbitrage opportunities detected
CREATE TABLE IF NOT EXISTS arbitrage_opportunities (
    id SERIAL PRIMARY KEY,
    timestamp BIGINT NOT NULL,
    asset_symbol VARCHAR(50),
    binance_price DECIMAL(20, 8),
    hl_oracle_price DECIMAL(20, 8),
    price_diff DECIMAL(20, 8),
    price_diff_pct DECIMAL(10, 6),
    min_profit_spread DECIMAL(10, 6),
    detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_arb_timestamp ON arbitrage_opportunities(timestamp);
CREATE INDEX IF NOT EXISTS idx_arb_asset ON arbitrage_opportunities(asset_symbol);

-- Simulation state: Track retail maker and HFT sniper interactions
CREATE TABLE IF NOT EXISTS simulation_state (
    id SERIAL PRIMARY KEY,
    timestamp BIGINT NOT NULL,
    retail_order_price DECIMAL(20, 8),
    retail_order_size DECIMAL(20, 8),
    hl_oracle_price DECIMAL(20, 8),
    binance_price DECIMAL(20, 8),
    hft_sniper_engaged BOOLEAN DEFAULT FALSE,
    hft_execution_price DECIMAL(20, 8),
    retail_loss DECIMAL(20, 8),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_sim_timestamp ON simulation_state(timestamp);
CREATE INDEX IF NOT EXISTS idx_sim_hft_engaged ON simulation_state(hft_sniper_engaged);
