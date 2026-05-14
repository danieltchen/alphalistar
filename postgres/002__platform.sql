CREATE TABLE IF NOT EXISTS TICKER (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    cik INTEGER NOT NULL,
    name VARCHAR(255) NOT NULL,
    exchange VARCHAR(10) NOT NULL,
    UNIQUE (symbol),
    UNIQUE (cik)
);

-- Add indices for common lookups
CREATE INDEX IF NOT EXISTS idx_ticker_symbol ON TICKER(symbol);
CREATE INDEX IF NOT EXISTS idx_ticker_cik ON TICKER(cik);

-- Add new columns to TICKER table for tracking latest processed periods
ALTER TABLE TICKER 
ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE,
ADD COLUMN IF NOT EXISTS latest_annual_period DATE,
ADD COLUMN IF NOT EXISTS latest_quarterly_period DATE,
ADD COLUMN IF NOT EXISTS latest_annual_year VARCHAR(4),
ADD COLUMN IF NOT EXISTS latest_quarterly_year VARCHAR(4),
ADD COLUMN IF NOT EXISTS latest_quarter INTEGER;

-- Add comments for documentation
COMMENT ON TABLE TICKER IS 'Stores company information and metadata';
COMMENT ON COLUMN TICKER.id IS 'Unique identifier for the company record';
COMMENT ON COLUMN TICKER.symbol IS 'Company ticker symbol';
COMMENT ON COLUMN TICKER.cik IS 'SEC CIK number';
COMMENT ON COLUMN TICKER.name IS 'Company name';
COMMENT ON COLUMN TICKER.exchange IS 'Stock exchange where the company is listed';
COMMENT ON COLUMN TICKER.is_active IS 'Indicates if the company is active';
COMMENT ON COLUMN TICKER.latest_annual_period IS 'Date of the latest annual filing';
COMMENT ON COLUMN TICKER.latest_quarterly_period IS 'Date of the latest quarterly filing';
COMMENT ON COLUMN TICKER.latest_annual_year IS 'Year of the latest annual filing as a CHAR(4)';
COMMENT ON COLUMN TICKER.latest_quarterly_year IS 'Year of the latest quarterly filing as a CHAR(4)';
COMMENT ON COLUMN TICKER.latest_quarter IS 'Quarter (1-4) of the latest quarterly filing';

-- Create FILING table
CREATE TABLE IF NOT EXISTS FILING (
    id SERIAL PRIMARY KEY,
    tickerId INTEGER NOT NULL,
    symbol VARCHAR(10) NOT NULL,
    type VARCHAR(10) NOT NULL,
    accessionNo VARCHAR(50) NOT NULL,
    year INTEGER NOT NULL,
    filingDate DATE NOT NULL,
    downloadDate DATE NOT NULL,
    completed BOOLEAN DEFAULT FALSE,
    FOREIGN KEY (tickerId) REFERENCES TICKER(id),
    CONSTRAINT unique_accession UNIQUE (accessionNo)
);

-- Create indexes for better performance
CREATE INDEX IF NOT EXISTS idx_filing_accession ON FILING(accessionNo);
CREATE INDEX IF NOT EXISTS idx_filing_symbol ON FILING(symbol);
CREATE INDEX IF NOT EXISTS idx_filing_ticker ON FILING(tickerId);

-- Add comments for documentation
COMMENT ON TABLE FILING IS 'Stores SEC filing information for companies';
COMMENT ON COLUMN FILING.id IS 'Unique identifier for the filing record';
COMMENT ON COLUMN FILING.tickerId IS 'Foreign key reference to the TICKER table';
COMMENT ON COLUMN FILING.symbol IS 'Company ticker symbol for easier querying';
COMMENT ON COLUMN FILING.type IS 'Filing type (e.g., 10-K, 10-Q, 8-K)';
COMMENT ON COLUMN FILING.accessionNo IS 'SEC EDGAR accession number';
COMMENT ON COLUMN FILING.year IS 'Year of the filing';
COMMENT ON COLUMN FILING.quarter IS 'Quarter number (1-4) for quarterly filings, NULL for annual';
COMMENT ON COLUMN FILING.filingDate IS 'Official SEC filing date';
COMMENT ON COLUMN FILING.downloadDate IS 'Date when the filing was downloaded';
COMMENT ON COLUMN FILING.completed IS 'Indicates if filing processing is complete';

-- Make sure pgvector extension is created
CREATE EXTENSION IF NOT EXISTS vector;

-- Create STATEMENTS table
CREATE TABLE IF NOT EXISTS STATEMENTS (
    id SERIAL PRIMARY KEY,
    filingId INTEGER NOT NULL,
    section VARCHAR(50) NOT NULL,  -- Identifies the section (e.g., 'Item 7', 'Item 7A')
    title TEXT,                    -- Section title/heading
    content TEXT NOT NULL,         -- The actual content
    word_count INTEGER,            -- Word count for content chunking
    processed_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    chunk_number INTEGER,          -- Chunk number for large content
    embedding VECTOR(1536)      ,  -- Sentence embedding for similarity search
    FOREIGN KEY (filingId) REFERENCES FILING(id),
    UNIQUE(filingId, section)
);

ALTER TABLE STATEMENTS 
ADD CONSTRAINT unique_filing_section_chunk UNIQUE (filingId, section, chunk_number);

-- Optionally add an index for vector similarity search
CREATE INDEX ON STATEMENTS USING ivfflat (embedding vector_cosine_ops);

-- Added a new column for storing markdown formatted content for the content/chunked text
ALTER TABLE STATEMENTS ADD COLUMN markdown_content TEXT;
-- Added a new column for storing the raw_content prior to any cleaning or markdown conversion
ALTER TABLE STATEMENTS ADD COLUMN raw_content TEXT;

-- Add comments for documentation
COMMENT ON TABLE STATEMENTS IS 'Stores extracted sections from SEC filings';
COMMENT ON COLUMN STATEMENTS.id IS 'Unique identifier for the statement record';
COMMENT ON COLUMN STATEMENTS.filingId IS 'Foreign key reference to the FILING table';
COMMENT ON COLUMN STATEMENTS.section IS 'Section identifier (e.g., Item 7, Item 7A, 8-K PR)';
COMMENT ON COLUMN STATEMENTS.title IS 'Section title or heading';
COMMENT ON COLUMN STATEMENTS.content IS 'Extracted content from the filing which has been cleaned and chunked';
COMMENT ON COLUMN STATEMENTS.word_count IS 'Word count for content';
COMMENT ON COLUMN STATEMENTS.processed_date IS 'Timestamp of when the content was processed';
COMMENT ON COLUMN STATEMENTS.chunk_number IS 'Chunk number of the split content';
COMMENT ON COLUMN STATEMENTS.embedding IS 'Vector embedding of the content for similarity search';
COMMENT ON COLUMN STATEMENTS.markdown_content IS 'Markdown formatted content';
COMMENT ON COLUMN STATEMENTS.raw_content IS 'Raw content prior to any cleaning or markdown conversion';
