# Terraform: distributed scraper (dispatcher + SQS + worker)

This module provisions:

- **SQS** job queue and **dead-letter queue** (after `sqs_max_receive_count` failed receives)
- **Dispatcher** Lambda (`run_scraper.dispatcher.lambda_handler`) — **Zip** deployment: reads active tickers from Postgres via **Secrets Manager**, sends one message per ticker
- **Worker** Lambda (`run_scraper.worker.lambda_handler`) — **SQS trigger**, runs `SingleStockScraper` per message with **partial batch failure** reporting  
  - Default **`worker_package_type = "Image"`**: **ECR** container (fits large deps: pyarrow, pandas, NLTK, etc.; Lambda image limit **10 GB**)
  - Optional **`worker_package_type = "Zip"`**: classic zip (must stay under **250 MB** unzipped)
- **EventBridge** schedule invoking the dispatcher

## Prerequisites

- Terraform `>= 1.5`, AWS provider `>= 5.0`
- AWS credentials configured (`aws configure` or environment variables)
- A **Secrets Manager** secret whose JSON matches `run_scraper/db.py` (`dbname`, `host`, `user`, `password`, `port` — align the secret with that file)
- **Dispatcher** zip (always): see [Dispatcher zip](#dispatcher-zip-small-package) below
- **Worker**: either a pushed **container image** in the module-created ECR repository (Image mode) or a **worker zip** (Zip mode)

## Worker: container image (recommended)

Dockerfile: **[`../../run_scraper/Dockerfile.lambda-worker`](../../run_scraper/Dockerfile.lambda-worker)** — build context must be the **repository root** so both `scraper/` and `run_scraper/` are copied into `LAMBDA_TASK_ROOT`. Base image **`public.ecr.aws/lambda/python:3.11`** matches the default dispatcher `lambda_runtime` of `python3.11`; keep Dockerfile and `lambda_runtime` aligned if you change versions.

### Architecture

Build for the Lambda architecture you set in Terraform (`lambda_architecture`, default `x86_64`):

```bash
# From repository root
docker buildx build --platform linux/amd64 \
  -f run_scraper/Dockerfile.lambda-worker \
  -t <account>.dkr.ecr.<region>.amazonaws.com/<repo>:<tag> \
  --push .
```

Use `linux/arm64` only if `lambda_architecture = "arm64"`.

### First-time deploy (Image mode)

`CreateFunction` for a container Lambda **requires the image to already exist** in ECR. Suggested order:

1. **Create the ECR repository** (and lifecycle policy) first, then push the image, then create the rest of the stack — or run a **targeted** apply so ECR exists before the worker Lambda is created:

   ```bash
   cd terraform/run_scraper
   terraform init
   terraform apply -target='aws_ecr_repository.worker[0]' -target='aws_ecr_lifecycle_policy.worker[0]'
   ```

2. **Log in to ECR** and **push** the image. Repository URL is in `terraform output worker_ecr_repository_url` (or construct `...amazonaws.com/<name_prefix>-scrape-worker` in your account/region).

   ```bash
   aws ecr get-login-password --region <region> | docker login --username AWS --password-stdin <account>.dkr.ecr.<region>.amazonaws.com
   docker buildx build --platform linux/amd64 -f run_scraper/Dockerfile.lambda-worker \
     -t $(terraform output -raw worker_ecr_repository_url):<tag> --push .
   ```

3. Set **`worker_image_tag`** in `terraform.tfvars` to the tag you pushed (prefer **immutable** tags such as a **git SHA**, not only `latest` in production).

4. **Full apply**:

   ```bash
   terraform apply
   ```

### Ongoing releases

1. Build and push a new tag (e.g. `$GIT_SHA`).
2. Update `worker_image_tag` in tfvars (or pass `-var 'worker_image_tag=...'`).
3. `terraform apply` — Lambda will pull the new image.

### Variables (Image)

| Variable | Purpose |
|----------|---------|
| `worker_package_type` | `"Image"` (default) or `"Zip"` |
| `worker_image_tag` | Tag segment of `image_uri` (must exist in ECR before worker Lambda can be created on first deploy) |
| `worker_lambda_zip_path` | Omit or leave unset when using Image |

### Outputs (Image)

- `worker_ecr_repository_url` — push target prefix (without tag)
- `worker_image_uri` — full URI Terraform sets on the worker function (Image mode)

## Dispatcher zip (small package)

Paths must match `dispatcher_lambda_zip_path` (default `./dist/dispatcher.zip`). Create `terraform/run_scraper/dist/` first.

**Bash (repository root):**

```bash
mkdir -p terraform/run_scraper/dist build/dispatcher
pip install -r run_scraper/requirements-dispatcher.txt -t build/dispatcher
cp -r run_scraper build/dispatcher/
cd build/dispatcher && zip -r ../../terraform/run_scraper/dist/dispatcher.zip . && cd ../..
```

**PowerShell (repository root):** install into `build/dispatcher`, copy `run_scraper`, then zip (prefer `zip` from Git Bash if `Compress-Archive` misorders imports).

## Worker: Zip (optional, under 250 MB unzipped)

Set `worker_package_type = "Zip"` and **`worker_lambda_zip_path`** to your zip. Build by installing `scraper/requirements.txt` into a clean directory and copying `scraper/` and `run_scraper/` at the top level, then zip. See previous README revision or use the Image Dockerfile as a reference for dependencies only.

## Worker environment (`SingleStockScraper`)

`scraper/scrape.py` calls `DatabaseConnector.get_db_config()` **with no arguments**, which uses **environment variables**: `DB_NAME`, `DB_HOST`, `DB_USER`, `DB_PASS`, `DB_PORT`. Set these via `worker_environment_extra` in `terraform.tfvars` (or inject via your org’s pattern: SSM, `TF_VAR_`, etc.).

Also set keys required by press-release scraping (for example **`OPENAI_API_KEY`**) the same way.

This module does **not** attach Lambdas to a VPC. If functions must reach RDS inside a VPC, configure VPC (subnets, security groups) on the functions in the AWS Console or extend this module.

## Configure and apply

```bash
cd terraform/run_scraper
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars: secret name, dispatcher zip path, worker Image tag or Zip path, worker env, schedule

terraform init
terraform plan
terraform apply
```

## Optional: GitHub Actions outline

Typical pipeline (OIDC to AWS, no long-lived keys):

1. **Job `terraform-plan`** (or split): `terraform init` + `terraform plan` on PRs.
2. **Job `build-push`**: on `main` or release tags — `aws-actions/configure-aws-credentials`, `amazon-ecr-login`, `docker/build-push-action` with `file: run_scraper/Dockerfile.lambda-worker`, `context: .`, `platforms: linux/amd64`, tags `...:${{ github.sha }}`.
3. **Job `terraform-apply`**: pass `-var worker_image_tag=${{ github.sha }}` or update tfvars in the pipeline artifact; `terraform apply -auto-approve` (or manual approval gate).

Keep **`worker_image_tag`** in sync with the tag you push so the next apply updates the Lambda.

## Post-deploy checks

1. **Invoke dispatcher once** (Console “Test” or CLI): empty event `{}` is enough; optional keys match `dispatcher._resolve_config` (`queue_url`, `dry_run`, `max_tickers`, etc.).
2. Confirm messages appear in the **SQS** queue and **worker** logs in CloudWatch.
3. Tune **`worker_timeout_seconds`** and **`sqs_visibility_timeout_seconds`** so visibility timeout **exceeds** the function timeout (defaults follow AWS guidance).

## Optional adjustments

| Variable | Purpose |
|----------|---------|
| `dispatcher_schedule_expression` | EventBridge cron or `rate(...)` |
| `dispatcher_schedule_enabled` | `false` to pause schedule without destroying the rule |
| `sqs_worker_batch_size` | Keep `1` if each ticker scrape is long |
| `worker_reserved_concurrent_executions` | Cap parallelism (non-negative); `-1` = no dedicated cap |
| `sqs_worker_max_concurrency` | Event source mapping scaling cap (provider / account limits apply) |
| `lambda_runtime` | Dispatcher / Zip worker Python runtime (e.g. `python3.11`); keep in sync with `Dockerfile.lambda-worker` base image |

## KMS

If the **SQS queue** or **Secrets Manager** secret uses a **customer-managed KMS key**, add IAM statements (`kms:Decrypt`, etc.) to the dispatcher and/or worker roles (not included by default).
