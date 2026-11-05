# Must match table_definition() in core/verity_core/graph/dynamodb/table.py, which is the
# table's single description. tests/infra/test_opentofu.py fails if the two differ.
#
# Provisioned capacity and the Standard class are the only combination inside the Always Free
# allowance: 15 + 10 = 25 units each way. Auto-scaling, streams, TTL and point-in-time recovery
# stay off.
resource "aws_dynamodb_table" "graph" {
  name           = "verity-graph"
  billing_mode   = "PROVISIONED"
  table_class    = "STANDARD"
  read_capacity  = 15
  write_capacity = 15
  hash_key       = "PK"
  range_key      = "SK"

  attribute {
    name = "PK"
    type = "S"
  }

  attribute {
    name = "SK"
    type = "S"
  }

  attribute {
    name = "GSI1PK"
    type = "S"
  }

  attribute {
    name = "GSI1SK"
    type = "S"
  }

  global_secondary_index {
    name            = "GSI1"
    projection_type = "KEYS_ONLY" # D14
    read_capacity   = 10
    write_capacity  = 10

    key_schema {
      attribute_name = "GSI1PK"
      key_type       = "HASH"
    }

    key_schema {
      attribute_name = "GSI1SK"
      key_type       = "RANGE"
    }
  }
}

output "name" {
  value = aws_dynamodb_table.graph.name
}
