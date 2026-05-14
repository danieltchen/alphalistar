data "aws_caller_identity" "current" {}
data "aws_partition" "current" {}

data "aws_secretsmanager_secret" "database" {
  name = var.database_secret_name
}

locals {
  name_dispatcher = "${var.name_prefix}-dispatcher"
  name_worker     = "${var.name_prefix}-worker"
  name_dlq        = "${var.name_prefix}-scrape-dlq"
  name_queue      = "${var.name_prefix}-scrape-jobs"
  name_ecr_worker = "${var.name_prefix}-scrape-worker"

  dispatcher_env = merge(
    {
      SCRAPE_QUEUE_URL = aws_sqs_queue.scrape.url
      AWS_SECRET_NAME  = var.database_secret_name
    },
    var.dispatcher_environment_extra
  )

  worker_env = merge(
    {},
    var.worker_environment_extra
  )

  worker_package_image = var.worker_package_type == "Image"
  worker_image_uri     = local.worker_package_image ? "${aws_ecr_repository.worker[0].repository_url}:${var.worker_image_tag}" : null
}

check "worker_needs_zip_path" {
  assert {
    condition     = var.worker_package_type != "Zip" || (var.worker_lambda_zip_path != null && var.worker_lambda_zip_path != "")
    error_message = "worker_lambda_zip_path must be set when worker_package_type is Zip."
  }
}

check "worker_image_tag_nonempty" {
  assert {
    condition     = !local.worker_package_image || length(trimspace(var.worker_image_tag)) > 0
    error_message = "worker_image_tag must be non-empty when worker_package_type is Image."
  }
}

# ---------------------------------------------------------------------------
# SQS: job queue + dead-letter queue
# ---------------------------------------------------------------------------

resource "aws_sqs_queue" "dlq" {
  name                      = local.name_dlq
  message_retention_seconds = 1209600 # 14 days
  tags                      = var.tags
}

resource "aws_sqs_queue" "scrape" {
  name                       = local.name_queue
  visibility_timeout_seconds = var.sqs_visibility_timeout_seconds
  message_retention_seconds  = 345600 # 4 days
  receive_wait_time_seconds  = 0

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.dlq.arn
    maxReceiveCount     = var.sqs_max_receive_count
  })

  tags = var.tags
}

# ---------------------------------------------------------------------------
# ECR: worker container image (only when worker_package_type is Image)
# ---------------------------------------------------------------------------

resource "aws_ecr_repository" "worker" {
  count = local.worker_package_image ? 1 : 0
  name  = local.name_ecr_worker

  image_tag_mutability = "MUTABLE"
  force_delete         = false

  image_scanning_configuration {
    scan_on_push = true
  }

  tags = var.tags
}

resource "aws_ecr_lifecycle_policy" "worker" {
  count      = local.worker_package_image ? 1 : 0
  repository = aws_ecr_repository.worker[0].name

  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Retain at most 20 images"
        selection = {
          tagStatus   = "any"
          countType   = "imageCountMoreThan"
          countNumber = 20
        }
        action = {
          type = "expire"
        }
      }
    ]
  })
}

# ---------------------------------------------------------------------------
# CloudWatch log groups
# ---------------------------------------------------------------------------

resource "aws_cloudwatch_log_group" "dispatcher" {
  name              = "/aws/lambda/${local.name_dispatcher}"
  retention_in_days = 14
  tags              = var.tags
}

resource "aws_cloudwatch_log_group" "worker" {
  name              = "/aws/lambda/${local.name_worker}"
  retention_in_days = 14
  tags              = var.tags
}

# ---------------------------------------------------------------------------
# IAM: dispatcher
# ---------------------------------------------------------------------------

resource "aws_iam_role" "dispatcher" {
  name = "${var.name_prefix}-dispatcher-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        Service = "lambda.amazonaws.com"
      }
      Action = "sts:AssumeRole"
    }]
  })
  tags = var.tags
}

resource "aws_iam_role_policy_attachment" "dispatcher_basic" {
  role       = aws_iam_role.dispatcher.name
  policy_arn = "arn:${data.aws_partition.current.partition}:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy" "dispatcher_data" {
  name = "${var.name_prefix}-dispatcher-data"
  role = aws_iam_role.dispatcher.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "sqs:SendMessage"
        ]
        Resource = aws_sqs_queue.scrape.arn
      },
      {
        Effect = "Allow"
        Action = [
          "secretsmanager:GetSecretValue"
        ]
        Resource = data.aws_secretsmanager_secret.database.arn
      }
    ]
  })
}

# ---------------------------------------------------------------------------
# IAM: worker
# ---------------------------------------------------------------------------

resource "aws_iam_role" "worker" {
  name = "${var.name_prefix}-worker-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        Service = "lambda.amazonaws.com"
      }
      Action = "sts:AssumeRole"
    }]
  })
  tags = var.tags
}

resource "aws_iam_role_policy_attachment" "worker_basic" {
  role       = aws_iam_role.worker.name
  policy_arn = "arn:${data.aws_partition.current.partition}:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy" "worker_data" {
  name = "${var.name_prefix}-worker-data"
  role = aws_iam_role.worker.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = concat(
      [
        {
          Effect = "Allow"
          Action = [
            "sqs:ReceiveMessage",
            "sqs:DeleteMessage",
            "sqs:GetQueueAttributes",
            "sqs:GetQueueUrl",
            "sqs:ChangeMessageVisibility"
          ]
          Resource = aws_sqs_queue.scrape.arn
        }
      ],
      local.worker_package_image ? [
        {
          Effect = "Allow"
          Action = [
            "ecr:GetDownloadUrlForLayer",
            "ecr:BatchGetImage",
            "ecr:BatchCheckLayerAvailability"
          ]
          Resource = aws_ecr_repository.worker[0].arn
        },
        {
          Effect   = "Allow"
          Action   = ["ecr:GetAuthorizationToken"]
          Resource = "*"
        }
      ] : []
    )
  })
}

# ---------------------------------------------------------------------------
# Lambda functions
# ---------------------------------------------------------------------------

resource "aws_lambda_function" "dispatcher" {
  function_name = local.name_dispatcher
  role          = aws_iam_role.dispatcher.arn
  handler       = "run_scraper.dispatcher.lambda_handler"
  runtime       = var.lambda_runtime
  architectures = [var.lambda_architecture]

  filename         = var.dispatcher_lambda_zip_path
  source_code_hash = filebase64sha256(var.dispatcher_lambda_zip_path)

  memory_size = var.dispatcher_memory_mb
  timeout     = var.dispatcher_timeout_seconds

  environment {
    variables = local.dispatcher_env
  }

  depends_on = [
    aws_cloudwatch_log_group.dispatcher,
    aws_iam_role_policy.dispatcher_data
  ]

  tags = var.tags
}

resource "aws_lambda_function" "worker" {
  function_name = local.name_worker
  role          = aws_iam_role.worker.arn
  architectures = [var.lambda_architecture]

  package_type = local.worker_package_image ? "Image" : "Zip"
  image_uri    = local.worker_image_uri

  filename         = local.worker_package_image ? null : var.worker_lambda_zip_path
  source_code_hash = local.worker_package_image ? null : filebase64sha256(var.worker_lambda_zip_path)
  handler          = local.worker_package_image ? null : "run_scraper.worker.lambda_handler"
  runtime          = local.worker_package_image ? null : var.lambda_runtime

  memory_size = var.worker_memory_mb
  timeout     = var.worker_timeout_seconds

  reserved_concurrent_executions = var.worker_reserved_concurrent_executions >= 0 ? var.worker_reserved_concurrent_executions : null

  environment {
    variables = local.worker_env
  }

  depends_on = [
    aws_cloudwatch_log_group.worker,
    aws_iam_role_policy.worker_data,
  ]

  tags = var.tags
}

# ---------------------------------------------------------------------------
# SQS -> worker Lambda
# ---------------------------------------------------------------------------

resource "aws_lambda_event_source_mapping" "worker_sqs" {
  event_source_arn = aws_sqs_queue.scrape.arn
  function_name    = aws_lambda_function.worker.arn
  batch_size       = var.sqs_worker_batch_size
  enabled          = true

  function_response_types = ["ReportBatchItemFailures"]

  dynamic "scaling_config" {
    for_each = var.sqs_worker_max_concurrency != null ? [1] : []
    content {
      maximum_concurrency = var.sqs_worker_max_concurrency
    }
  }
}

# ---------------------------------------------------------------------------
# EventBridge schedule -> dispatcher Lambda
# ---------------------------------------------------------------------------

resource "aws_cloudwatch_event_rule" "dispatcher_schedule" {
  name                = "${var.name_prefix}-dispatcher-schedule"
  description         = "Triggers scrape dispatcher to enqueue per-ticker SQS messages."
  schedule_expression = var.dispatcher_schedule_expression
  state               = var.dispatcher_schedule_enabled ? "ENABLED" : "DISABLED"
  tags                = var.tags
}

resource "aws_cloudwatch_event_target" "dispatcher" {
  rule      = aws_cloudwatch_event_rule.dispatcher_schedule.name
  target_id = "DispatcherLambda"
  arn       = aws_lambda_function.dispatcher.arn
}

resource "aws_lambda_permission" "dispatcher_eventbridge" {
  statement_id  = "AllowExecutionFromEventBridge"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.dispatcher.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.dispatcher_schedule.arn
}
