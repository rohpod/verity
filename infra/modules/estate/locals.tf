# The estate is specified by content/fixtures/crawl/estate.json, and tests/infra/test_estate.py
# compares this file with it: names, memory, timeouts, env names, tags and role policies
# (ADR 0025, decision 6). Everything here is a literal so that the test can read it. ARNs are
# built from var.account_id and never written out.

locals {
  # The boundary denies exactly the Bedrock and SageMaker entries of verity-never-use
  # (infra/bootstrap/verity-never-use.json). `bedrock:Converse*` matches no action today and stays
  # for safety.
  boundary_deny = [
    "bedrock:Converse*",
    "bedrock:Invoke*",
    "sagemaker:InvokeEndpoint*",
  ]

  # The estate's apps. `uses_openai` adds OPENAI_BASE_URL, which comes from the Function URL.
  # Memory sets the CPU share, and the two apps that load pydantic need more of it (ADR 0026).
  apps = {
    support-assistant = {
      description = "Answers customer support questions"
      memory_size = 512
      tags        = { "ai:system-id" = "sys:support-assistant", project = "kestrel-demo" }
      uses_openai = false
      env = {
        MODEL_ADAPTER      = "mock-bedrock"
        HELP_ARTICLES_FILE = "articles.json"
        USAGE_TABLE        = "verity-graph"
        LOG_LEVEL          = "INFO"
      }
    }
    talent-screening = {
      description = "Scores job applicants with a small local model"
      memory_size = 128
      tags        = {}
      uses_openai = false
      env = {
        COEFFICIENTS_FILE = "coefficients.json"
        LOG_LEVEL         = "INFO"
      }
    }
    contract-insights = {
      description = "Summarises customer contracts for sales and legal"
      memory_size = 512
      tags        = { "ai:system-id" = "sys:contract-insights", project = "kestrel-demo" }
      uses_openai = true
      env = {
        USAGE_TABLE = "verity-graph"
        LOG_LEVEL   = "INFO"
      }
    }
    shadow-summariser = {
      description = "Summarises documents for one team"
      memory_size = 128
      tags        = {}
      uses_openai = true
      env         = {}
    }
    invoice-renderer = {
      description = "Renders invoices from a template"
      memory_size = 128
      tags        = {}
      uses_openai = false
      env = {
        INVOICE_TEMPLATE = "template.txt"
      }
    }
  }

  # The simulated providers. Nothing real is called.
  mocks = {
    mock-openai = {
      description = "Simulated OpenAI-shaped endpoint. Nothing real is called"
      tags        = { "verity:component" = "mock-openai" }
    }
    mock-bedrock = {
      description = "Simulated Bedrock Converse-shaped function. Nothing real is called"
      tags        = { "verity:component" = "mock-bedrock" }
    }
  }

  # Every function that has a role of its own. verity-probe has none: it runs on
  # support-assistant-role.
  role_names = toset(concat(keys(local.apps), keys(local.mocks), ["verity-crawler"]))

  # Inline policies by function, then by policy name. The names and shapes are the fixture's.
  policies = {
    support-assistant = {
      logs = [{
        Effect   = "Allow"
        Action   = ["logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = "arn:aws:logs:eu-north-1:${var.account_id}:log-group:/aws/lambda/support-assistant:*"
      }]
      model-and-data = [
        {
          # The seeded finding of ADR 0022. IAM's simulator shows the boundary denies this call.
          Effect   = "Allow"
          Action   = ["bedrock:InvokeModel"]
          Resource = "arn:aws:bedrock:eu-north-1::foundation-model/*"
        },
        {
          Effect    = "Allow"
          Action    = ["dynamodb:PutItem"]
          Resource  = "arn:aws:dynamodb:eu-north-1:${var.account_id}:table/verity-graph"
          Condition = { "ForAllValues:StringEquals" = { "dynamodb:LeadingKeys" = ["T#kestrel#U#sys:support-assistant"] } }
        },
        {
          Effect   = "Allow"
          Action   = ["lambda:InvokeFunction"]
          Resource = "arn:aws:lambda:eu-north-1:${var.account_id}:function:mock-bedrock"
        },
      ]
    }
    talent-screening = {
      logs = [{
        Effect   = "Allow"
        Action   = ["logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = "arn:aws:logs:eu-north-1:${var.account_id}:log-group:/aws/lambda/talent-screening:*"
      }]
    }
    contract-insights = {
      logs = [{
        Effect   = "Allow"
        Action   = ["logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = "arn:aws:logs:eu-north-1:${var.account_id}:log-group:/aws/lambda/contract-insights:*"
      }]
      model-and-data = [
        {
          Effect    = "Allow"
          Action    = ["dynamodb:PutItem"]
          Resource  = "arn:aws:dynamodb:eu-north-1:${var.account_id}:table/verity-graph"
          Condition = { "ForAllValues:StringEquals" = { "dynamodb:LeadingKeys" = ["T#kestrel#U#sys:contract-insights"] } }
        },
        {
          Effect   = "Allow"
          Action   = ["lambda:InvokeFunctionUrl", "lambda:InvokeFunction"]
          Resource = "arn:aws:lambda:eu-north-1:${var.account_id}:function:mock-openai"
        },
      ]
    }
    shadow-summariser = {
      logs = [{
        Effect   = "Allow"
        Action   = ["logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = "arn:aws:logs:eu-north-1:${var.account_id}:log-group:/aws/lambda/shadow-summariser:*"
      }]
      model-and-data = [{
        Effect   = "Allow"
        Action   = ["lambda:InvokeFunctionUrl", "lambda:InvokeFunction"]
        Resource = "arn:aws:lambda:eu-north-1:${var.account_id}:function:mock-openai"
      }]
    }
    invoice-renderer = {
      logs = [{
        Effect   = "Allow"
        Action   = ["logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = "arn:aws:logs:eu-north-1:${var.account_id}:log-group:/aws/lambda/invoice-renderer:*"
      }]
    }
    mock-openai = {
      logs = [{
        Effect   = "Allow"
        Action   = ["logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = "arn:aws:logs:eu-north-1:${var.account_id}:log-group:/aws/lambda/mock-openai:*"
      }]
    }
    mock-bedrock = {
      logs = [{
        Effect   = "Allow"
        Action   = ["logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = "arn:aws:logs:eu-north-1:${var.account_id}:log-group:/aws/lambda/mock-bedrock:*"
      }]
    }

    # The crawler's role (architecture section D). It lists and reads; it never calls
    # lambda:GetFunction, which would allow code download, and it has no logs:CreateLogGroup.
    verity-crawler = {
      logs = [{
        Effect   = "Allow"
        Action   = ["logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = "arn:aws:logs:eu-north-1:${var.account_id}:log-group:/aws/lambda/verity-crawler:*"
      }]
      discovery = [
        {
          Effect = "Allow"
          Action = [
            "cloudtrail:LookupEvents",
            "dynamodb:ListTables",
            "iam:GetPolicy",
            "iam:GetPolicyVersion",
            "iam:GetRolePolicy",
            "iam:ListAttachedRolePolicies",
            "iam:ListRolePolicies",
            "iam:ListRoles",
            "lambda:ListFunctions",
            "tag:GetResources",
          ]
          Resource = "*"
        },
        {
          Effect   = "Allow"
          Action   = ["ssm:GetParametersByPath"]
          Resource = "arn:aws:ssm:eu-north-1:${var.account_id}:parameter/verity/manifests*"
        },
      ]
      # What DynamoDBRepository calls: GetItem, BatchGetItem, Query on GSI1, Scan, and
      # TransactWriteItems, which IAM authorises as PutItem. tests/infra/test_estate.py derives
      # this list from the repository's source and from a recorded crawl.
      graph = [{
        Effect = "Allow"
        Action = [
          "dynamodb:BatchGetItem",
          "dynamodb:GetItem",
          "dynamodb:PutItem",
          "dynamodb:Query",
          "dynamodb:Scan",
        ]
        Resource = [
          "arn:aws:dynamodb:eu-north-1:${var.account_id}:table/verity-graph",
          "arn:aws:dynamodb:eu-north-1:${var.account_id}:table/verity-graph/index/GSI1",
        ]
      }]
    }
  }

  inline_policies = merge([
    for function, named in local.policies : {
      for name, statements in named : "${function}/${name}" => {
        function   = function
        statements = statements
      }
    }
  ]...)
}
