-- Prediction Market Intelligence Agent
-- PostgreSQL Schema

-- ============================================
-- MARKETS (Polymarket data)
-- ============================================

CREATE TABLE IF NOT EXISTS markets (
    id VARCHAR(255) PRIMARY KEY,
    question TEXT NOT NULL,
    description TEXT,
    outcome_prices JSONB,           -- {"Yes": 0.73, "No": 0.27}
    outcomes JSONB,                 -- ["Yes", "No"] or multiple options
    volume_24h DECIMAL(20, 2),
    liquidity DECIMAL(20, 2),
    start_date TIMESTAMP,
    end_date TIMESTAMP,
    status VARCHAR(50),             -- active, closed, resolved
    resolution TEXT,                -- final outcome if resolved
    category VARCHAR(100),
    tags TEXT[],
    source_url TEXT,
    raw_data JSONB,                 -- full API response
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_markets_status ON markets(status);
CREATE INDEX IF NOT EXISTS idx_markets_category ON markets(category);
CREATE INDEX IF NOT EXISTS idx_markets_end_date ON markets(end_date);
CREATE INDEX IF NOT EXISTS idx_markets_volume ON markets(volume_24h DESC);

-- ============================================
-- NEWS ARTICLES (Guardian, gov.uk)
-- ============================================

CREATE TABLE IF NOT EXISTS articles (
    id SERIAL PRIMARY KEY,
    source VARCHAR(50) NOT NULL,    -- guardian, govuk
    external_id VARCHAR(255),       -- source's own ID
    title TEXT NOT NULL,
    content TEXT,
    summary TEXT,
    url TEXT,
    published_at TIMESTAMP,
    author TEXT,
    section VARCHAR(100),
    tags TEXT[],
    raw_data JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(source, external_id)
);

CREATE INDEX IF NOT EXISTS idx_articles_source ON articles(source);
CREATE INDEX IF NOT EXISTS idx_articles_published ON articles(published_at DESC);
CREATE INDEX IF NOT EXISTS idx_articles_section ON articles(section);

-- Full text search on title and content
CREATE INDEX IF NOT EXISTS idx_articles_search ON articles 
    USING GIN (to_tsvector('english', title || ' ' || COALESCE(content, '')));

-- ============================================
-- ECONOMIC INDICATORS (FRED data)
-- ============================================

CREATE TABLE IF NOT EXISTS economic_indicators (
    id SERIAL PRIMARY KEY,
    series_id VARCHAR(50) NOT NULL, -- FRED series ID (e.g., FEDFUNDS, CPIAUCSL)
    name VARCHAR(255) NOT NULL,
    value DECIMAL(20, 6),
    unit VARCHAR(50),
    date DATE NOT NULL,
    frequency VARCHAR(20),          -- daily, weekly, monthly, quarterly
    source VARCHAR(50) DEFAULT 'FRED',
    raw_data JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(series_id, date)
);

CREATE INDEX IF NOT EXISTS idx_indicators_series ON economic_indicators(series_id);
CREATE INDEX IF NOT EXISTS idx_indicators_date ON economic_indicators(date DESC);

-- ============================================
-- DATA LINEAGE (tracking data origins)
-- ============================================

CREATE TABLE IF NOT EXISTS data_lineage (
    id SERIAL PRIMARY KEY,
    table_name VARCHAR(100) NOT NULL,
    record_id VARCHAR(255) NOT NULL,
    source VARCHAR(100) NOT NULL,
    source_url TEXT,
    fetched_at TIMESTAMP NOT NULL,
    transformation TEXT,            -- description of any transforms applied
    checksum VARCHAR(64),           -- SHA256 of raw data
    metadata JSONB,
    
    UNIQUE(table_name, record_id, fetched_at)
);

CREATE INDEX IF NOT EXISTS idx_lineage_table ON data_lineage(table_name);
CREATE INDEX IF NOT EXISTS idx_lineage_source ON data_lineage(source);

-- ============================================
-- AGENT LOGS (tracking agent behaviour)
-- ============================================

CREATE TABLE IF NOT EXISTS agent_logs (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ DEFAULT NOW(),
    query TEXT NOT NULL,                 -- user's question
    tools_called JSONB,                  -- ["polymarket", "guardian", "fred"]
    context_retrieved JSONB,             -- summary of data retrieved
    response TEXT,                       -- agent's answer
    sources_cited JSONB,                 -- sources used in response
    reasoning TEXT,                      -- chain of thought / explanation
    latency_ms INTEGER,                  -- response time
    success BOOLEAN DEFAULT TRUE,
    error_message TEXT
);

CREATE INDEX IF NOT EXISTS idx_agent_logs_timestamp ON agent_logs(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_agent_logs_success ON agent_logs(success);

-- ============================================
-- HELPER FUNCTION: Update timestamp
-- ============================================

CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Apply to markets table
DROP TRIGGER IF EXISTS markets_updated_at ON markets;
CREATE TRIGGER markets_updated_at
    BEFORE UPDATE ON markets
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at();
