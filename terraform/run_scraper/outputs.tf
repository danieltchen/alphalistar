output "scrape_queue_url" {
  description = "SQS queue URL the dispatcher writes to and the worker reads from."
  value       = aws_sqs_queue.scrape.url
}

output "scrape_queue_arn" {
  description = "SQS queue ARN."
  value       = aws_sqs_queue.scrape.arn
}

output "dead_letter_queue_url" {
  description = "DLQ URL for failed messages after max receives."
  value       = aws_sqs_queue.dlq.url
}

output "dispatcher_lambda_arn" {
  description = "Dispatcher Lambda ARN (EventBridge target)."
  value       = aws_lambda_function.dispatcher.arn
}

output "dispatcher_lambda_name" {
  value = aws_lambda_function.dispatcher.function_name
}

output "worker_lambda_arn" {
  description = "Worker Lambda ARN (SQS event source mapping)."
  value       = aws_lambda_function.worker.arn
}

output "worker_lambda_name" {
  value = aws_lambda_function.worker.function_name
}

output "worker_ecr_repository_url" {
  description = "ECR registry URL for the worker image (Image mode only)."
  value       = try(aws_ecr_repository.worker[0].repository_url, null)
}

output "worker_ecr_repository_arn" {
  description = "ECR repository ARN (Image mode only)."
  value       = try(aws_ecr_repository.worker[0].arn, null)
}

output "worker_image_uri" {
  description = "Image URI configured on the worker Lambda (Image mode only)."
  value       = local.worker_image_uri
}

output "dispatcher_schedule_rule_arn" {
  description = "EventBridge rule ARN for the dispatcher schedule."
  value       = aws_cloudwatch_event_rule.dispatcher_schedule.arn
}
