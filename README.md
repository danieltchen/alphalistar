# AlphaListar

AlphaListar is a hybrid Retrieval-Augmented Generation (RAG) system for financial Q&A. It combines structured financial data in PostgreSQL with a Neo4j knowledge graph, orchestrated through LangGraph workflows and served by a FastAPI backend with full execution tracing.

## Repository Layout

| Path | Description |
| --- | --- |
| [`beta/app/`](beta/app/README.md) | FastAPI backend, hybrid orchestrator, text-to-SQL and text-to-Cypher pipelines, tracing framework |
| [`beta/frontend/`](beta/frontend/README.md) | React 18 + TypeScript query UI with trace visualization |
| [`beta/eval/`](beta/eval/README.md) | LLM-as-Judge evaluation framework (factual grounding, hallucination rate, consistency) |
| [`beta/`](beta/) | Production deploy scripts (`01..06_*.sh`), Dockerfiles, nginx config, docker-compose files |
| [`scraper/`](scraper/README.md) | Data ingestion from Yahoo Finance and SEC EDGAR, plus OpenAI-powered KG extraction |
| [`run_scraper/`](run_scraper/README.md) | Lightweight dispatcher + SQS worker package for distributed Lambda scraping |
| [`terraform/run_scraper/`](terraform/run_scraper/README.md) | Terraform module: SQS queues, EventBridge schedule, dispatcher (zip) and worker (ECR image) Lambdas |
| [`postgres/`](postgres/) | Numbered SQL migrations (`000__*.sql` → `012_*.sql`) for tickers, fundamentals, traces, eval, auth |
| `build/` | Local build artifacts (e.g. dispatcher zip staging) |

## Architecture

```
        ┌──────────────────────────────────────────────┐
        │  React Frontend  (beta/frontend)             │
        └───────────────────┬──────────────────────────┘
                            │ REST / polling
        ┌───────────────────▼──────────────────────────┐
        │  FastAPI Backend  (beta/app)                 │
        │  ┌──────────────────────────────────────┐    │
        │  │  HybridFinancialOrchestrator         │    │
        │  │   ├─ TextToSqlOrchestrator           │    │
        │  │   └─ TextToCypherOrchestrator        │    │
        │  └──────────────────────────────────────┘    │
        └───────┬──────────────────────────┬───────────┘
                │                          │
        ┌───────▼─────────┐        ┌───────▼─────────┐
        │  PostgreSQL     │        │  Neo4j Aura     │
        │  (financials,   │        │  (knowledge     │
        │   traces, eval) │        │   graph)        │
        └───────▲─────────┘        └───────▲─────────┘
                │                          │
        ┌───────┴──────────────────────────┴───────────┐
        │  Scraper  (scraper/ + run_scraper/)          │
        │  Yahoo Finance · SEC EDGAR · OpenAI          │
        │  Dispatcher Lambda → SQS → Worker Lambda     │
        └──────────────────────────────────────────────┘
```

Queries are classified as `SQL_ONLY`, `HYBRID` (SQL + Cypher), `GRAPH_ONLY`, or `DIRECT_ANSWER` and routed accordingly. Every step is captured by the trace framework for citation, verification, and debugging.

## Quick Start

### Backend (local)

```bash
cd beta
pip install -r requirements.txt
uvicorn app.alphalistar_api:app --reload --host 0.0.0.0 --port 8000
```

### Frontend (local)

```bash
cd beta/frontend
npm install
npm start            # dev server on :3000, proxies to backend on :8000
```

### Database

Apply the SQL files in [`postgres/`](postgres/) in numeric order against your PostgreSQL instance.

### Scraper (local)

```bash
cd scraper
pip install -r requirements.txt
python scrape.py NVDA --days 5 --8k 2 --10k 1 --10q 1
```

See [`scraper/README.md`](scraper/README.md) for hydration, daily incremental, and Lambda modes.

## Deployment

- **Application stack** (EC2 + CloudFront + nginx + Docker): run the ordered scripts in [`beta/`](beta/) (`01_deploy-ec2.sh` → `06_deploy-cloudfront-complete.sh`).
- **Distributed scraper** (Lambda + SQS + EventBridge): provision with [`terraform/run_scraper`](terraform/run_scraper/README.md). The dispatcher ships as a small zip; the worker ships as a container image to ECR.

## Required Environment Variables

```bash
# PostgreSQL
DB_NAME=...
DB_HOST=...
DB_USER=...
DB_PASS=...
DB_PORT=5432

# Neo4j Aura
NEO4J_URI=neo4j+s://<instance>.databases.neo4j.io
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=...

# OpenAI
OPENAI_API_KEY=...

# AWS (optional, for Secrets Manager and Lambda deploys)
AWS_REGION=us-east-1
AWS_SECRET_NAME=...        # RDS credentials secret
AWS_APP_SECRET_NAME=...    # Application runtime secret
```

## Tech Stack

- **Backend:** FastAPI · LangGraph · OpenAI · psycopg2 · neo4j-driver · Pydantic
- **Frontend:** React 18 · TypeScript · Tailwind · react-markdown · KaTeX
- **Data:** PostgreSQL · Neo4j Aura · Redis
- **Ingestion:** yfinance · edgartools · OpenAI
- **Infra:** AWS Lambda · SQS · EventBridge · ECR · CloudFront · EC2 · Secrets Manager · Terraform

## License

See [`LICENSE`](LICENSE).
