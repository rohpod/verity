# The functions run the zips that scripts/build_lambdas.py writes into .build/. The zips are
# uploaded directly (no S3) and are deterministic, so an unchanged build is not a ChangeEvent.
# `try()` lets `tofu validate` pass in CI, where no zip exists.
#
# No reserved concurrency, X-Ray, VPC, layers, dead-letter queue, versions or aliases: each is
# unneeded here and some are not free.

locals {
  # Set from the Function URL below. mock-openai is a separate resource from its callers so that
  # no resource depends on itself.
  openai_base_url = "${trimsuffix(aws_lambda_function_url.mock_openai.function_url, "/")}/v1"
}

resource "aws_lambda_function" "mock" {
  for_each         = local.mocks
  function_name    = each.key
  description      = each.value.description
  role             = aws_iam_role.function[each.key].arn
  runtime          = "python3.12"
  architectures    = ["arm64"]
  handler          = "app.handler"
  memory_size      = 128
  timeout          = 10
  filename         = "${var.build_dir}/${each.key}.zip"
  source_code_hash = try(filebase64sha256("${var.build_dir}/${each.key}.zip"), "")
  tags             = each.value.tags

  depends_on = [aws_cloudwatch_log_group.function, aws_iam_role_policy.inline]
}

# A caller must hold lambda:InvokeFunctionUrl and lambda:InvokeFunction in its own policy, and
# there is no resource policy, so nothing else can call it. Never an output (ADR 0025).
resource "aws_lambda_function_url" "mock_openai" {
  function_name      = aws_lambda_function.mock["mock-openai"].function_name
  authorization_type = "AWS_IAM"
}

resource "aws_lambda_function" "app" {
  for_each         = local.apps
  function_name    = each.key
  description      = each.value.description
  role             = aws_iam_role.function[each.key].arn
  runtime          = "python3.12"
  architectures    = ["arm64"]
  handler          = "app.handler"
  memory_size      = each.value.memory_size
  timeout          = 10
  filename         = "${var.build_dir}/${each.key}.zip"
  source_code_hash = try(filebase64sha256("${var.build_dir}/${each.key}.zip"), "")
  tags             = each.value.tags

  dynamic "environment" {
    for_each = length(each.value.env) > 0 || each.value.uses_openai ? [1] : []
    content {
      variables = merge(
        each.value.env,
        each.value.uses_openai ? { OPENAI_BASE_URL = local.openai_base_url } : {},
      )
    }
  }

  depends_on = [aws_cloudwatch_log_group.function, aws_iam_role_policy.inline]
}

resource "aws_lambda_function" "crawler" {
  function_name    = "verity-crawler"
  description      = "Reads the account and writes the Verity graph"
  role             = aws_iam_role.function["verity-crawler"].arn
  runtime          = "python3.12"
  architectures    = ["arm64"]
  handler          = "app.handler"
  memory_size      = 256
  timeout          = 300
  filename         = "${var.build_dir}/verity-crawler.zip"
  source_code_hash = try(filebase64sha256("${var.build_dir}/verity-crawler.zip"), "")
  tags             = { "verity:component" = "verity-crawler" }

  environment {
    variables = {
      GRAPH_TABLE  = var.table_name
      TENANT       = "kestrel"
      SIGNALS_FILE = "rules/ai_signals.yaml"
    }
  }

  depends_on = [aws_cloudwatch_log_group.function, aws_iam_role_policy.inline]
}

# A failed crawl is repaired by the next one, so a retry would only add a second writer
# (ADR 0014, ADR 0025 decision 8).
resource "aws_lambda_function_event_invoke_config" "crawler" {
  function_name          = aws_lambda_function.crawler.function_name
  maximum_retry_attempts = 0
}

# Exists only while enable_probe is true, and is destroyed before the first crawl so the crawler
# never sees it (ADR 0025, decision 5). It runs on support-assistant-role to show that role cannot
# write outside its usage partition. Its writes carry a condition that can never be true.
resource "aws_lambda_function" "probe" {
  count            = var.enable_probe ? 1 : 0
  function_name    = "verity-probe"
  description      = "Proves a role cannot write outside its partition"
  role             = aws_iam_role.function["support-assistant"].arn
  runtime          = "python3.12"
  architectures    = ["arm64"]
  handler          = "app.handler"
  memory_size      = 512
  timeout          = 10
  filename         = "${var.build_dir}/verity-probe.zip"
  source_code_hash = try(filebase64sha256("${var.build_dir}/verity-probe.zip"), "")
  tags             = { "verity:component" = "verity-probe" }

  environment {
    variables = {
      GRAPH_TABLE = var.table_name
    }
  }

  depends_on = [aws_iam_role_policy.inline]
}
