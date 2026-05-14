# run_scraper Lambda Package

This folder is a standalone package for the distributed scraper flow:

- `dispatcher.py`: lightweight orchestrator that queries active tickers and enqueues one SQS message per ticker
- `worker.py`: SQS worker entrypoint that runs `SingleStockScraper` per message
- `db.py`: minimal Postgres/Secrets Manager helpers used by the dispatcher

## Handler names

- Dispatcher Lambda handler: `run_scraper.dispatcher.lambda_handler`
- Worker Lambda handler: `run_scraper.worker.lambda_handler`

## Container image (AWS Lambda)

For large dependency sets, build from the **repo root** using [`Dockerfile.lambda-worker`](Dockerfile.lambda-worker) and push to ECR; see [`terraform/run_scraper/README.md`](../terraform/run_scraper/README.md).

## Independence model

`dispatcher.py` has no dependency on `scraper` modules; it only depends on:

- Python stdlib
- `boto3`
- `psycopg2` (`psycopg2-binary`)

`worker.py` imports `scraper.scrape.SingleStockScraper` and should be deployed with the full scraper runtime dependencies.
