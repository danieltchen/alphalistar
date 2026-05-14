variable "aws_region" {
  type        = string
  description = "Region for all resources in this module."
  default     = "us-east-1"
}

variable "name_prefix" {
  type        = string
  description = "Prefix for resource names (SQS, Lambdas, rules)."
  default     = "alphalistar-scrape"
}

variable "tags" {
  type        = map(string)
  description = "Tags applied to supported resources."
  default     = {}
}

# --- Lambda deployment artifacts (build locally; see README) ---

variable "dispatcher_lambda_zip_path" {
  type        = string
  description = "Filesystem path to the dispatcher deployment .zip."
}

variable "worker_package_type" {
  type        = string
  description = "Worker deployment: Zip (small package) or Image (ECR container for large dependencies)."
  default     = "Image"

  validation {
    condition     = contains(["Zip", "Image"], var.worker_package_type)
    error_message = "worker_package_type must be Zip or Image."
  }
}

variable "worker_lambda_zip_path" {
  type        = string
  nullable    = true
  default     = null
  description = "Filesystem path to the worker .zip. Required when worker_package_type is Zip; ignored for Image."
}

variable "worker_image_tag" {
  type        = string
  description = "ECR image tag for the worker (e.g. git SHA). Used only when worker_package_type is Image."
  default     = "latest"
}

variable "lambda_runtime" {
  type        = string
  description = "Python runtime for the dispatcher Zip function and for the worker when worker_package_type is Zip. Container worker uses the Dockerfile base image (keep in sync with public.ecr.aws/lambda/python)."
  default     = "python3.11"
}

variable "lambda_architecture" {
  type        = string
  description = "Lambda instruction set architecture (x86_64 or arm64)."
  default     = "x86_64"
}

# --- Dispatcher: DB + fan-out ---

variable "database_secret_name" {
  type        = string
  description = "Secrets Manager secret id/name holding Postgres JSON (same shape as run_scraper/db.py: dbname, host, user, password, port)."
}

variable "dispatcher_environment_extra" {
  type        = map(string)
  description = "Additional environment variables for the dispatcher (merged after reserved keys)."
  default     = {}
}

variable "dispatcher_memory_mb" {
  type        = number
  description = "Dispatcher Lambda memory in MB."
  default     = 256
}

variable "dispatcher_timeout_seconds" {
  type        = number
  description = "Dispatcher timeout (SQS send + DB query for all tickers)."
  default     = 300
}

# --- Worker: scrape ---

variable "worker_environment_extra" {
  type        = map(string)
  description = "Environment variables for the worker. SingleStockScraper uses DatabaseConnector.get_db_config() with no args — set DB_NAME, DB_HOST, DB_USER, DB_PASS, DB_PORT (and OPENAI_API_KEY, etc.) here."
  default     = {}
}

variable "worker_memory_mb" {
  type        = number
  description = "Worker Lambda memory in MB."
  default     = 1024
}

variable "worker_timeout_seconds" {
  type        = number
  description = "Worker timeout per invocation (one or more SQS messages per batch)."
  default     = 900
}

variable "worker_reserved_concurrent_executions" {
  type        = number
  description = "Optional reserved concurrency for the worker (omit stress on DB/APIs). Use -1 for no reservation (default AWS unreserved pool)."
  default     = -1
}

# --- SQS ---

variable "sqs_visibility_timeout_seconds" {
  type        = number
  description = "Main queue visibility timeout. Must be >= worker_timeout_seconds (AWS recommends > function timeout)."
  default     = 960
}

variable "sqs_max_receive_count" {
  type        = number
  description = "After this many failed receives, message goes to the DLQ."
  default     = 5
}

variable "sqs_worker_batch_size" {
  type        = number
  description = "Max messages per worker Lambda invocation (1 is safest for long scrapes)."
  default     = 1
}

variable "sqs_worker_max_concurrency" {
  type        = number
  description = "Maximum concurrent Lambda instances reading from the queue (null = account default / unlimited cap)."
  default     = null
}

# --- Schedule ---

variable "dispatcher_schedule_expression" {
  type        = string
  description = "EventBridge schedule expression (e.g. cron(0 14 * * ? *) for 14:00 UTC daily)."
  default     = "cron(0 14 * * ? *)"
}

variable "dispatcher_schedule_enabled" {
  type        = bool
  description = "If false, the rule exists but will not trigger (useful for initial deploy)."
  default     = true
}
