# AlphaListar Scraper Module

A comprehensive financial data scraping and processing system that collects stock prices, financial statements, press releases, and insider transactions for analysis. The module supports both historical data hydration and incremental daily updates, with knowledge graph extraction capabilities. Equities, ETFs, and mutual funds are all supported, with EDGAR-only data sources automatically gated by instrument type.

## Overview

The scraper module is responsible for collecting, processing, and storing financial data from multiple sources into both PostgreSQL (structured data) and Neo4j (knowledge graph). It's designed to run in two modes:

1. **Hydration Mode** (`hydrate_all.py` / `hydrate.py`) - Initial bulk data collection for historical data
2. **Single-Ticker Incremental Mode** (`scrape.py`) - Incremental update for one ticker
3. **Distributed Incremental Mode** (`run_scraper/dispatcher.py` + `run_scraper/worker.py`) - Queue fan-out for per-ticker Lambda execution

### What's New

- **ETF / fund support** - The TICKER `quote_type` (raw yfinance `quoteType`) drives processing. Non-equity instruments (ETF, MUTUALFUND, etc.) collect prices and fund-specific fundamentals (NAV, expense ratio, yield, returns) but automatically skip EDGAR-only sources (financials, press releases, insider transactions) via `is_edgar_eligible()`.
- **Insider transactions** - SEC Forms 3, 4, and 5 (initial ownership, changes, and annual catch-up) are parsed into a normalized star schema (`insider`, `insider_filing`, `insider_transaction`, `insider_transaction_code`).
- **Per-process run state & locking** - Each data source tracks its own run state in `PROCESS_RUN_STATE`, with stale-lock takeover, success/failure cursors, and "fail-open" preflight checks so a transient error never silently drops a source.
- **Offline unit test suite** - A `pytest` suite under `tests/` covers orchestration (`scrape.py`, `hydrate.py`) and all pure helpers with DB, EDGAR, OpenAI, and yfinance fully mocked.

## Architecture

### Core Components

#### Data Connectors
- **`connector_database.py`** - PostgreSQL database connector with AWS Secrets Manager integration
- **`connector_neo4j.py`** - Neo4j Aura connector for knowledge graph operations

#### Data Processors
- **`processor_stocks.py`** - Stock price, split, and fundamentals processing via Yahoo Finance (equity and ETF/fund metrics)
- **`processor_financials.py`** - Financial statement processing from SEC EDGAR (10-K/10-Q)
- **`processor_pressreleases.py`** - Press release processing from SEC EDGAR (8-K/10-K/10-Q MD&A)
- **`processor_insiders.py`** - Insider ownership processing from SEC EDGAR (Forms 3/4/5)
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
   - ETF / fund metrics (NAV, expense ratio, yield, trailing returns) and instrument `quoteType`

2. **SEC EDGAR** (via `edgartools`) - equities only (`quote_type` EQUITY or unknown)
   - 10-K: Annual financial reports
   - 10-Q: Quarterly financial reports
   - 8-K: Current event press releases
   - Forms 3 / 4 / 5: Insider ownership and transactions

3. **OpenAI API** (via `openai`)
   - Press release summarization
   - Knowledge graph entity extraction
   - Financial metric extraction

## Database Schema

### PostgreSQL Tables

#### Core Tables
- **TICKER** - Company/instrument information (symbol, CIK, name, exchange) plus instrument-type fields: `quote_type`, `type_disp`, `legal_type`, `fund_family`, `category`, `fund_inception_date`
- **PRICE** - Daily stock prices
- **SPLIT** - Stock split events
- **FUNDAMENTALS** - Comprehensive fundamental metrics, including ETF/fund columns (`nav_price`, `total_assets`, `net_assets`, `net_expense_ratio`, `yield_pct`, `ytd_return`, trailing returns, etc.)
- **FILING** - SEC filing metadata
- **PROCESS_RUN_STATE** - Per-ticker, per-process run state (`stocks`, `financials`, `press_releases`, `insider_transactions`) with status, lock token, attempt count, last error, and last-success cursor

#### Insider Transaction Tables (star schema)
- **insider** - Reporting insiders (officers, directors, 10%+ owners) deduplicated by SEC CIK
- **insider_filing** - One row per Form 3/4/5 filing (form type, filing date, net change/value, remaining shares, 10b5-1 flag, `completed`)
- **insider_transaction** - Transaction-level ledger: one row per line item (code, shares, price, ownership, derivative details, footnotes)
- **insider_transaction_code** - SEC transaction-code reference (P, S, M, A, etc.) for LLM-friendly joins
- **insider_position_current** (view) - Latest known position per insider/security from completed filings

Apply migration [`postgres/013__insider_transactions.sql`](postgres/013__insider_transactions.sql) before running insider ingestion. It creates the insider tables/view, seeds the transaction-code reference, and extends the `PROCESS_RUN_STATE` process-name check to include `insider_transactions`. ETF/fund columns come from [`postgres/002__ticker_etf_support.sql`](postgres/002__ticker_etf_support.sql).

#### Financial statement tables (canonical)
- **financial_line** - Stable `line_code` dimension (statement type, display name, synonyms JSON for Text-to-SQL)
- **financial_fact** - One row per ticker, fiscal period, and `line_code` (value, `source_concept`, optional unit/decimals/scale, filing accession)

Apply migration [`postgres/005__financial_canonical.sql`](postgres/005__financial_canonical.sql) before running financial ingestion. It creates `financial_line` / `financial_fact` and seeds all canonical `line_code` rows used by the GAAP map (and **drops** legacy `balancesheet`, `income`, and `cashflow` wide tables if you uncomment those statements at the end of the file).

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
1. Stock Data Hydration (all instruments)
   └─> Fetch historical stock prices from Yahoo Finance (from --start-date)
   └─> Parse into PRICE, SPLIT, FUNDAMENTALS tables (equity + ETF/fund metrics)
   └─> Store in PostgreSQL

   ── EDGAR-eligibility gate ──
   └─> Read TICKER.quote_type; if non-equity (ETF/MUTUALFUND/etc.) skip steps 2-4

2. Financial Data Hydration (equities only)
   └─> Fetch last 5 annual (10-K) filings from SEC EDGAR
   └─> Fetch last 20 quarterly (10-Q) filings from SEC EDGAR
   └─> Parse balance sheet, income statement, cash flow
   └─> Map to canonical line_code and upsert into financial_fact (join key: financial_line)

3. Press Release Hydration (equities only)
   └─> Fetch last 40 8-K filings from SEC EDGAR
   └─> Fetch last 5 10-K / 10-Q MD&A sections from SEC EDGAR
   └─> Chunk text into manageable segments
   └─> Generate summaries using OpenAI
   └─> Store in STATEMENTS and SUMMARY tables

4. Insider Transaction Hydration (equities only)
   └─> Fetch latest Forms 3/4/5 from SEC EDGAR (up to --insiders per form)
   └─> Normalize filing headers and transaction lines
   └─> Upsert into insider / insider_filing / insider_transaction tables

5. Knowledge Graph Extraction (Optional)
   └─> Process existing press releases
   └─> Extract entities and relationships using OpenAI
   └─> Store in Neo4j knowledge graph
```

### Daily Scraping Flow (`scrape.py`)

Each source runs as an independent, lockable step. Before running, a preflight check decides whether there is new data; if the preflight check itself errors it "fails open" and the step runs anyway. Each step acquires a per-ticker/process lock in `PROCESS_RUN_STATE`, then records success (with a cursor) or failure.

```
1. Market Open Check (unless --skip-market-check)
   └─> Check if today is a weekend
   └─> Check if today is a US federal holiday
   └─> Skip if market is closed

2. Latest Stock Data (all instruments)
   └─> Fetch last --days of stock prices
   └─> Compare with latest date in database
   └─> Insert only new records
   └─> Read TICKER.quote_type to gate EDGAR steps below

3. Latest Financial Data (equities only)
   └─> Check for new 10-K/10-Q filings
   └─> Process only new filings
   └─> Update financial tables

4. Latest Press Releases (equities only)
   └─> Check for new 8-K filings (last --8k)
   └─> Check for new 10-K / 10-Q MD&A (last --10k / --10q)
   └─> Process and store new content
   └─> Extract knowledge graph entities

5. Latest Insider Transactions (equities only)
   └─> Check for new Forms 3/4/5 (last --insiders per form)
   └─> Process and upsert new filings and transaction lines
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
# Runtime dependencies
pip install -r requirements.txt

# Test/development dependencies (pytest, pytest-cov, pytest-asyncio)
pip install -r requirements-dev.txt
```

### Single-Ticker Hydration (`hydrate.py`)

`hydrate.py` hydrates one ticker. In `full` mode it loads history for every eligible source; in `incremental` mode it delegates to `SingleStockScraper` (the same engine as `scrape.py`) with the market-calendar check disabled.

```bash
# Full historical hydration for one ticker
python hydrate.py AAPL --start-date 2020-01-01

# Tune EDGAR limits and insider depth
python hydrate.py AAPL \
  --start-date 2020-01-01 \
  --annual 5 --quarterly 20 \
  --8k 40 --10k 5 --10q 5 \
  --insiders 100

# Incremental hydration (delegates to the scraper engine, skips market check)
python hydrate.py AAPL --mode incremental --days 5
```

`hydrate.py` flags:

| Flag | Default | Description |
| --- | --- | --- |
| `ticker` (positional) | — | Stock ticker symbol, e.g. `AAPL` |
| `--start-date` | `2020-01-01` | Historical start date (ISO) for stock prices |
| `--annual` | `5` | Max annual (10-K) filings |
| `--quarterly` | `20` | Max quarterly (10-Q) filings |
| `--8k` | `40` | Max 8-K filings |
| `--10k` | `5` | Max 10-K MD&A sections |
| `--10q` | `5` | Max 10-Q MD&A sections |
| `--insiders` | `100` | Max Form 3/4/5 filings per form |
| `--mode` | `full` | `full` rehydrate or `incremental` |
| `--days` | `5` | Recent-day window for incremental stock updates |

ETF/fund tickers automatically load only prices and fund fundamentals; EDGAR steps are skipped.

**Expected Runtime (full mode, per ticker):**
- Stock data: ~1-2 minutes
- Financials: ~2-3 minutes (5 annual + 20 quarterly)
- Press releases: ~4-6 minutes (40 8-Ks + 5 10-Ks)
- Insider transactions: ~1-2 minutes (Forms 3/4/5)

### Daily / Incremental Scraping (`scrape.py`)

```bash
# Run incremental update for one ticker (defaults shown explicitly)
python scrape.py NVDA --days 5 --annual 1 --quarterly 1 --8k 2 --10k 1 --10q 1 --insiders 10

# Force press-release processing even if preflight says up-to-date
python scrape.py NVDA --force-press-releases

# Run even on weekends / holidays
python scrape.py NVDA --skip-market-check
```

`scrape.py` flags:

| Flag | Default | Description |
| --- | --- | --- |
| `ticker` (positional) | — | Stock ticker symbol, e.g. `AAPL` |
| `--days` | `5` | Recent calendar days of price data to fetch |
| `--annual` | `1` | Max annual (10-K) filings to check |
| `--quarterly` | `1` | Max quarterly (10-Q) filings to check |
| `--8k` | `2` | Max 8-K press-release filings to process |
| `--10k` | `1` | Max 10-K MD&A sections to process |
| `--10q` | `1` | Max 10-Q MD&A sections to process |
| `--insiders` | `10` | Max Form 3/4/5 insider filings per form |
| `--skip-market-check` | `false` | Run even on weekends/holidays |
| `--force-press-releases` | `false` | Always run press-release/10-K processor even if preflight says up-to-date |

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
  "insider_limit": 10,
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
SCRAPE_INSIDER_LIMIT=10
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

The module ships with an offline `pytest` suite under [`tests/`](tests/). All external systems (PostgreSQL, EDGAR, OpenAI, yfinance) are mocked, so the tests need no database, network, or API keys.

```bash
# Install test dependencies
pip install -r requirements-dev.txt

# Run the full suite with coverage (config in pytest.ini / .coveragerc)
python -m pytest

# Run a single test file
python -m pytest tests/test_scrape.py

# Run a single test by node id
python -m pytest tests/test_hydrate.py::TestMainRouting::test_full_equity_runs_all_steps

# Quiet run without coverage
python -m pytest -q -p no:cov
```

#### Test layout

| File | Coverage focus |
| --- | --- |
| `tests/conftest.py`, `tests/fakes.py` | Shared fixtures: `sys.path` setup, `FakeCursor`/`FakeConnection`, fake EDGAR filing/company builders |
| `tests/test_scrape.py` | `SingleStockScraper.run()` state machine, skip/lock/run/success/fail, EDGAR-eligibility gating, market calendar, preflight helpers, CLI flags |
| `tests/test_hydrate.py` | `main()` full/incremental/non-equity routing, per-step wrappers, `lambda_handler` 200/500 |
| `tests/test_connector_database.py` | Config resolution, process-name validation, `get_ticker_id`, filing insert date coercion, `execute_sql_statements` branches |
| `tests/test_parser_stock.py` | Price/split/fundamentals parsing and value coercion |
| `tests/test_parser_financial.py` | XBRL fact extraction, fiscal-period logic, candidate merging |
| `tests/test_concept_mapper.py` | XBRL normalization, GAAP mapping, `GAAP_MAP` invariants |
| `tests/test_processor_insiders.py` | Insider coercion helpers and DataFrame transaction-row parsing |
| `tests/test_processor_pressreleases.py` | Text cleaning, markdown conversion, MD&A section resolution |
| `tests/test_processor_nlp.py` | Text cleaning, sentence tokenization, token-aware chunking |

#### Smoke checks (require real config)

```bash
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

### Runtime (`requirements.txt`)

Targets Python 3.11 (matches the Lambda base image `public.ecr.aws/lambda/python:3.11`):

- **boto3** 1.37.4 - AWS SDK (Secrets Manager, SQS)
- **pyarrow** 19.0.1 - Efficient data serialization
- **edgartools** 5.36.0 - SEC EDGAR data access
- **httpx** 0.28.1 - HTTP client with retry logic
- **nltk** 3.9.4 - Natural language processing
- **openai** 2.36.0 - OpenAI API client
- **numpy** 1.26.4 - Numerical operations
- **pandas** 2.2.3 - Data manipulation
- **psycopg2-binary** 2.9.10 - PostgreSQL adapter
- **pydantic** 2.12.5 - Data validation
- **tiktoken** 0.11.0 - Token counting for OpenAI
- **yfinance** 1.3.0 - Yahoo Finance data

### Development / test (`requirements-dev.txt`)

- **pytest** - Test runner
- **pytest-cov** - Coverage reporting
- **pytest-asyncio** - Async test support

## License

Part of the AlphaListar project. See main repository for license details.

## Support

For issues or questions:
1. Check logs for detailed error messages
2. Verify environment variables are set correctly
3. Test database connectivity separately
4. Review AWS Lambda CloudWatch logs

## Changelog

### v1.3
- **ETF / fund support** - Instrument-aware processing via TICKER `quote_type`; non-equities collect prices and fund fundamentals (NAV, expense ratio, yield, returns) and skip EDGAR-only sources through `is_edgar_eligible()`
- **Insider transactions** - SEC Forms 3/4/5 ingestion into a normalized star schema (`insider`, `insider_filing`, `insider_transaction`, `insider_transaction_code`, `insider_position_current` view); new `--insiders` flag on `hydrate.py` and `scrape.py`
- **Per-process run state & locking** - `PROCESS_RUN_STATE` tracks each source's status, lock token, cursor, and last error, with stale-lock takeover and fail-open preflight checks
- **Single-ticker hydration modes** - `hydrate.py` supports `--mode full` and `--mode incremental` (delegates to the scraper engine)
- **Offline unit test suite** - `pytest` tests under `tests/` covering orchestration and pure helpers, with all I/O mocked (`requirements-dev.txt`, `pytest.ini`, `.coveragerc`)
- Updated dependency versions (edgartools 5.36.0, openai 2.36.0, yfinance 1.3.0, etc.)

### v1.2
- Added knowledge graph extraction
- Implemented daily scraping with market calendar
- AWS Lambda deployment support
- IPv4 enforcement for faster connections
- EDGAR wrapper for Lambda compatibility
- Comprehensive error handling and logging
