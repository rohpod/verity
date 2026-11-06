# Daily at 03:00 UTC. It starts DISABLED and is enabled only after a manual crawl and a second one
# have passed (ADR 0025, decision 8). Scheduler retries are off: a failed crawl is repaired by the
# next one.
resource "aws_scheduler_schedule" "crawl" {
  name                         = "verity-crawl-daily"
  state                        = var.schedule_state
  schedule_expression          = "cron(0 3 * * ? *)"
  schedule_expression_timezone = "UTC"

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = aws_lambda_function.crawler.arn
    role_arn = aws_iam_role.scheduler.arn

    retry_policy {
      maximum_retry_attempts = 0
    }
  }
}

resource "aws_iam_role" "scheduler" {
  name                 = "verity-crawl-scheduler-role"
  permissions_boundary = aws_iam_policy.boundary.arn

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "scheduler.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "scheduler" {
  name = "invoke-crawler"
  role = aws_iam_role.scheduler.name

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["lambda:InvokeFunction"]
      Resource = aws_lambda_function.crawler.arn
    }]
  })
}
