# AlphaListar Scraper Module

A comprehensive financial data scraping and processing system that collects stock prices, financial statements, and press releases for analysis. The module supports both historical data hydration and incremental daily updates, with knowledge graph extraction capabilities.

## Overview

The scraper module is responsible for collecting, processing, and storing financial data from multiple sources into both PostgreSQL (structured data) and Neo4j (knowledge graph). It's designed to run in two modes:

1. **Hydration Mode** (`hydrate_all.py` / `hydrate.py`) - Initial bulk data collection for historical data
2. **Single-Ticker Incremental Mode** (`scrape.py`) - Incremental update for one ticker
3. **Distributed Incremental Mode** (`run_scraper/dispatcher.py` + `run_scraper/worker.py`) - Queue fan-out for per-ticker Lambda execution

## Architecture

### Core Components

#### Data Connectors
- **`connector_database.py`** - PostgreSQL database connector with AWS Secrets Manager integration
- **`connector_neo4j.py`** - Neo4j Aura connector for knowledge graph operations

#### Data Processors
- **`processor_stocks.py`** - Stock price and market data processing via Yahoo Finance
- **`processor_financials.py`** - Financial statement processing from SEC EDGAR (10-K/10-Q)
- **`processor_pressreleases.py`** - Press release processing from SEC EDGAR (8-K/10-K)
- **`processor_kg_pressreleases.py`** - Knowledge graph extraction from press releases
- **`processor_nlp.py`** - NLP processing with OpenAI for text analysis

#### Data Parsers
- **`parser_stock.py`** - Parses stock price data into SQL statements
- **`parser_financial.py`** - Maps EDGAR XBRL facts to canonical `financial_fact` rows
- **`concept_mapper.py`** / **`financial_gaap_map.py`** / **`concept_overrides.json`** - Concept to `line_code` mapping (anchor-first)

#### Utilities
- **`edgar_wrapper.py`** - AWS Lambda-compatible wrapper for edgartools library
- **`extractor_financial.py`** - Financial entity extraction using OpenAI
- **`scrape_latest_financials.py`** - Latest financial data scraper
- **`scrape_to_kg.py`** - Script for populating knowledge graph from existing data

### Data Sources

1. **Yahoo Finance** (via `yfinance`)
   - Daily stock prices (OHLCV)
   - Stock splits
   - Fundamental metrics (P/E, market cap, ratios, etc.)

2. **SEC EDGAR** (via `edgartools`)
   - 10-K: Annual financial reports
   - 10-Q: Quarterly financial reports
   - 8-K: Current event press releases

3. **OpenAI API** (via `openai`)
   - Press release summarization
   - Knowledge graph entity extraction
   - Financial metric extraction

## Database Schema

### PostgreSQL Tables

#### Core Tables
- **TICKER** - Company information (symbol, CIK, name, exchange)
- **PRICE** - Daily stock prices
- **SPLIT** - Stock split events
- **FUNDAMENTALS** - Comprehensive fundamental metrics
- **FILING** - SEC filing metadata

#### Financial statement tables (canonical)
- **financial_line** - Stable `line_code` dimension (statement type, display name, synonyms JSON for Text-to-SQL)
- **financial_fact** - One row per ticker, fiscal period, and `line_code` (value, `source_concept`, optional unit/decimals/scale, filing accession)

Apply migration [`postgres/013__financial_canonical.sql`](postgres/013__financial_canonical.sql) before running financial ingestion. It creates `financial_line` / `financial_fact` and seeds all canonical `line_code` rows used by the GAAP map (and **drops** legacy `balancesheet`, `income`, and `cashflow` wide tables if you uncomment those statements at the end of the file).

#### Press Release Tables
- **STATEMENTS** - Chunked press release content
- **SUMMARY** - Press release summaries

### Neo4j Knowledge Graph

#### Node Types
- **Company** - Company entities
- **Document** - Filing documents
- **Metric** - Financial metrics
- **Risk** - Risk factors
- **Strategy** - Business strategies
- **Product** - Products and services
- **Event** - Business events
- **Trend** - Market trends

#### Relationship Types
- **MENTIONED_IN** - Entity mentioned in document
- **HAS_METRIC** - Company has metric
- **RELATED_TO** - General relationships between entities

## Data Flow

### Hydration Flow (`hydrate_all.py`)

```
1. Stock Data Hydration
   └─> Fetch 5 years of historical stock prices from Yahoo Finance
   └─> Parse into PRICE, SPLIT, FUNDAMENTALS tables
   └─> Store in PostgreSQL

2. Financial Data Hydration
   └─> Fetch last 5 annual (10-K) filings from SEC EDGAR
   └─> Fetch last 20 quarterly (10-Q) filings from SEC EDGAR
   └─> Parse balance sheet, income statement, cash flow
   └─> Map to canonical line_code and upsert into financial_fact (join key: financial_line)

3. Press Release Hydration
   └─> Fetch last 40 8-K filings from SEC EDGAR
   └─> Fetch last 5 10-K MD&A sections from SEC EDGAR
   └─> Chunk text into manageable segments
   └─> Generate summaries using OpenAI
   └─> Store in STATEMENTS and SUMMARY tables

4. Knowledge Graph Extraction (Optional)
   └─> Process existing press releases
   └─> Extract entities and relationships using OpenAI
   └─> Store in Neo4j knowledge graph
```

### Daily Scraping Flow (`scrape.py`)

```
1. Market Open Check
   └─> Check if today is a weekend
   └─> Check if today is a US federal holiday
   └─> Skip if market is closed

2. Latest Stock Data
   └─> Fetch last 5 days of stock prices
   └─> Compare with latest date in database
   └─> Insert only new records

3. Latest Financial Data
   └─> Check for new 10-K/10-Q filings
   └─> Process only new filings
   └─> Update financial tables

4. Latest Press Releases
   └─> Check for new 8-K filings (last 2)
   └─> Check for new 10-K MD&A (last 1)
   └─> Process and store new content
   └─> Extract knowledge graph entities
```

## Configuration

### Environment Variables

#### Database Configuration
```bash
DB_NAME=your_database_name
DB_HOST=your_database_host
DB_USER=your_database_user
DB_PASS=your_database_password
DB_PORT=5432
```

#### Neo4j Configuration
```bash
NEO4J_URI=neo4j+s://your-instance.databases.neo4j.io
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=your_password
```

#### API Keys
```bash
OPENAI_API_KEY=your_openai_api_key
```

#### AWS Configuration (Optional)
```bash
AWS_REGION=us-east-1
AWS_SECRET_NAME=your_secret_name
```

### Tracked Tickers

The system tracks 7 tickers stored in the `TICKER` table with `is_active = TRUE`. These are configured in the database and can be modified by updating the TICKER table.

Example tickers (configure as needed):
- AAPL (Apple)
- MSFT (Microsoft)
- GOOGL (Alphabet)
- AMZN (Amazon)
- META (Meta)
- TSLA (Tesla)
- NVDA (NVIDIA)

## Running Locally

### Prerequisites

```bash
pip install -r requirements.txt
```

### Initial Data Hydration

```bash
# Full hydration (stocks + financials + press releases)
python hydrate_all.py

# Knowledge graph extraction only (if you already have press releases)
python hydrate_all.py --kg-only
```

**Expected Runtime:**
- Stock data: ~5-10 minutes (7 tickers × 5 years)
- Financials: ~15-20 minutes (5 annual + 20 quarterly × 7 tickers)
- Press releases: ~30-45 minutes (40 8-Ks + 5 10-Ks × 7 tickers)

### Daily Scraping

```bash
# Run incremental update for one ticker
python scrape.py NVDA --days 5 --8k 2 --10k 1 --10q 1
```

**Expected Runtime:** 5-10 minutes

## AWS Lambda Deployment

### Docker Build

The module is containerized for AWS Lambda deployment using a Docker image based on `public.ecr.aws/lambda/python:3.11`.

```bash
# Build Docker image
docker build -t alphalistar-scraper .

# Tag for ECR
docker tag alphalistar-scraper:latest <your-ecr-repo>:latest

# Push to ECR
docker push <your-ecr-repo>:latest
```

### Lambda Configuration

#### Function Handlers
- **Hydration (single ticker):** `hydrate.lambda_handler`
- **Dispatcher fan-out:** `run_scraper.dispatcher.lambda_handler`
- **SQS Worker (single ticker scrape):** `run_scraper.worker.lambda_handler`

#### Recommended Settings
- **Memory:** 2048 MB
- **Timeout:** 900 seconds (15 minutes)
- **Ephemeral Storage:** 1024 MB (for EDGAR file caching)

#### Environment Variables
Set all required environment variables in Lambda configuration or use AWS Secrets Manager.

### EventBridge Schedule (Dispatcher)

Schedule `run_scraper.dispatcher.lambda_handler` to run daily:

```json
{
  "schedule": "cron(0 21 ? * MON-FRI *)",
  "description": "Run scraper at 9 PM UTC (market close) on weekdays"
}
```

Ticker jobs are enqueued immediately and processed asynchronously by the worker Lambda.

### SQS Fan-out Topology (Recommended)

Create two Lambda functions backed by the same image:

1. **Dispatcher Lambda** (`run_scraper.dispatcher.lambda_handler`)
   - Trigger: EventBridge schedule or manual invoke
   - Responsibility: query `TICKER` where `is_active = TRUE`, enqueue one message per ticker
   - Returns quickly; does not wait for ticker jobs

2. **Worker Lambda** (`run_scraper.worker.lambda_handler`)
   - Trigger: SQS event source mapping from scraper queue
   - Responsibility: run `SingleStockScraper` for one message/ticker
   - Supports partial batch response (`batchItemFailures`) so only failed messages are retried

3. **SQS + DLQ**
   - Main queue: receives ticker scrape jobs
   - DLQ: receives poison messages after max receive count

Recommended worker queue settings:
- Visibility timeout: at least `6 x` worker Lambda timeout
- Batch size: start with `1` to isolate heavy tickers, then tune upward
- Redrive policy: move to DLQ after 3-5 failed receives

### Fan-out Payload

Each SQS message body is JSON:

```json
{
  "ticker": "NVDA",
  "days": 5,
  "annual_limit": 1,
  "quarterly_limit": 1,
  "limit_8k": 2,
  "limit_10k": 1,
  "limit_10q": 1,
  "skip_market_check": false,
  "force_press_releases": false,
  "request_id": "uuid",
  "triggered_at": "2026-05-12T09:00:00+00:00"
}
```

### Environment Variables for Dispatcher and Worker

Required:

```bash
DB_NAME=your_database_name
DB_HOST=your_database_host
DB_USER=your_database_user
DB_PASS=your_database_password
DB_PORT=5432
OPENAI_API_KEY=your_openai_api_key
```

Dispatcher specific:

```bash
SCRAPE_QUEUE_URL=https://sqs.us-east-1.amazonaws.com/<account-id>/<queue-name>
```

Optional defaults used by `run_scraper/dispatcher.py` (overridable per event payload):

```bash
SCRAPE_DAYS=5
SCRAPE_ANNUAL_LIMIT=1
SCRAPE_QUARTERLY_LIMIT=1
SCRAPE_8K_LIMIT=2
SCRAPE_10K_LIMIT=1
SCRAPE_10Q_LIMIT=1
SCRAPE_SKIP_MARKET_CHECK=false
SCRAPE_FORCE_PRESS_RELEASES=false
```

## Key Features

### 1. Smart Scheduling
- Automatically skips weekends
- Checks US Federal Holiday calendar
- Only processes data on market open days

### 2. Incremental Updates
- Tracks last processed date for each ticker
- Only inserts new data to avoid duplicates
- Efficient delta processing

### 3. Rate Limiting & Retries
- Built-in delays between API calls (1-2 seconds)
- Automatic retry on rate limit errors
- Exponential backoff for failed requests

### 4. Lambda Optimization
- IPv4 enforcement for faster connections
- Temporary directory management for EDGAR cache
- NLTK data pre-downloaded in container
- Efficient memory usage

### 5. Knowledge Graph Integration
- Automatic entity extraction from press releases
- Neo4j Aura cloud integration
- Schema initialization and validation
- Relationship mapping between entities

### 6. Error Handling
- Comprehensive logging at INFO level
- Graceful error recovery
- Transaction rollback on failures
- Individual ticker isolation (one failure doesn't stop others)

## Monitoring & Logging

### Log Format
```
%(levelname)s | %(name)s | %(funcName)s:%(lineno)d | %(message)s
```

### Key Log Messages
- `"Processing historical data for {symbol}"` - Stock processing started
- `"Successfully processed {symbol}"` - Processing completed
- `"Skipping {symbol} - no data available"` - No data from source
- `"Rate limit detected, waiting..."` - API throttling
- `"Today is not a market open day"` - Automatic skip

### CloudWatch Metrics (Lambda)
- Invocation count
- Error rate
- Duration
- Memory usage

## Error Scenarios & Recovery

### Common Issues

1. **Rate Limiting**
   - Automatically retries after 10 seconds
   - Logs warning message
   - Continues with next ticker

2. **Missing Data**
   - Logs warning and skips ticker
   - Does not halt execution
   - Retries on next run

3. **Database Connection Failure**
   - Raises exception immediately
   - Lambda retry handles reconnection
   - Transaction rollback ensures consistency

4. **EDGAR API Timeout**
   - HTTP client retry with exponential backoff
   - Falls back to default timeout
   - Logs detailed error for debugging

## Development Guidelines

### Adding New Tickers

1. Insert into TICKER table:
```sql
INSERT INTO TICKER (symbol, cik, name, exchange, is_active)
VALUES ('AAPL', '0000320193', 'Apple Inc.', 'NASDAQ', TRUE);
```

2. Run hydration for the new ticker:
```bash
python hydrate_all.py
```

### Adding New Data Sources

1. Create new processor class inheriting from `DatabaseConnector`
2. Implement data fetching logic
3. Create parser for SQL generation
4. Add to `hydrate_all.py` and `scrape_all.py`

### Testing

```bash
# Test individual components
python -c "from processor_stocks import StockDataProcessor; print('OK')"

# Test database connection
python -c "from connector_database import DatabaseConnector; print(DatabaseConnector.get_db_config())"

# Test Neo4j connection
python -c "from connector_neo4j import Neo4jConnector; print(Neo4jConnector().is_connected())"
```

## Performance Optimization

### Database
- Use batch inserts where possible
- Index on `tickerId`, `date`, `fiscal_period_end`
- Partition PRICE table by date range (for large datasets)

### API Calls
- Respect rate limits (1-2 second delays)
- Cache EDGAR files in `/tmp/edgar`
- Reuse database connections within batch

### Lambda
- Pre-warm with scheduled CloudWatch Events
- Use provisioned concurrency for predictable performance
- Monitor cold start times

## Troubleshooting

### "No data available" for ticker
- Check if ticker symbol is correct
- Verify ticker is traded on supported exchange
- Check Yahoo Finance API status

### "Failed to retrieve secret"
- Verify AWS IAM permissions for Secrets Manager
- Check secret name matches configuration
- Ensure Lambda execution role has access

### "Neo4j connection failed"
- Verify NEO4J_URI, USERNAME, PASSWORD
- Check Neo4j Aura instance status
- Verify network connectivity (Lambda VPC config)

### "EDGAR rate limited"
- Reduce batch sizes
- Increase delays between requests
- Set proper User-Agent in `edgar_wrapper.py`

## Dependencies

See `requirements.txt` for full list:

- **pyarrow** 16.1.0 - Efficient data serialization
- **edgartools** 3.12.1 - SEC EDGAR data access
- **httpx** 0.28.1 - HTTP client with retry logic
- **nltk** 3.9.1 - Natural language processing
- **openai** 1.65.4 - OpenAI API client
- **numpy** 1.26.4 - Numerical operations
- **pandas** 2.2.3 - Data manipulation
- **psycopg2-binary** 2.9.10 - PostgreSQL adapter
- **pydantic** 2.10.6 - Data validation
- **tiktoken** 0.9.0 - Token counting for OpenAI
- **yfinance** 0.2.64 - Yahoo Finance data
- **neo4j** 5.28.1 - Neo4j driver

## License

Part of the AlphaListar project. See main repository for license details.

## Support

For issues or questions:
1. Check logs for detailed error messages
2. Verify environment variables are set correctly
3. Test database connectivity separately
4. Review AWS Lambda CloudWatch logs

## Changelog

### Current Version (v1.2)
- Added knowledge graph extraction
- Implemented daily scraping with market calendar
- AWS Lambda deployment support
- IPv4 enforcement for faster connections
- EDGAR wrapper for Lambda compatibility
- Comprehensive error handling and logging
