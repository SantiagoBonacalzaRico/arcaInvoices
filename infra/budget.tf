# Email alert when monthly spend approaches the budget — early warning if
# anything starts costing money outside the free tier.
resource "aws_budgets_budget" "monthly" {
  name         = "${var.project}-monthly"
  budget_type  = "COST"
  limit_amount = tostring(var.monthly_budget_usd)
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 80
    threshold_type             = "PERCENTAGE"
    notification_type          = "ACTUAL"
    subscriber_email_addresses = [var.alert_email]
  }

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 100
    threshold_type             = "PERCENTAGE"
    notification_type          = "ACTUAL"
    subscriber_email_addresses = [var.alert_email]
  }
}

# ── Auto-stop guardrail ───────────────────────────────────────────────────────
# When ACTUAL monthly spend crosses 100% of the budget, AWS Budgets stops the
# EC2 instance (the only compute cost driver once RDS is dropped). A hard
# "no surprise bills" circuit breaker — the service goes offline until you
# restart it. Note: Budgets evaluate on a schedule and cost data lags a few
# hours, so a small amount can slip through before the stop fires.

# Role that AWS Budgets assumes to perform the stop action.
data "aws_iam_policy_document" "budgets_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["budgets.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "budget_action" {
  name               = "${var.project}-budget-action"
  assume_role_policy = data.aws_iam_policy_document.budgets_assume.json
}

resource "aws_iam_role_policy" "budget_action" {
  name = "${var.project}-budget-stop-ec2"
  role = aws_iam_role.budget_action.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "ec2:StopInstances",
        "ec2:DescribeInstanceStatus",
        "ssm:StartAutomationExecution",
        "ssm:GetAutomationExecution",
      ]
      Resource = "*"
    }]
  })
}

resource "aws_budgets_budget_action" "stop_ec2" {
  budget_name       = aws_budgets_budget.monthly.name
  action_type       = "RUN_SSM_DOCUMENTS"
  approval_model    = "AUTOMATIC"
  notification_type = "ACTUAL"

  action_threshold {
    action_threshold_type  = "PERCENTAGE"
    action_threshold_value = 100
  }

  definition {
    ssm_action_definition {
      action_sub_type = "STOP_EC2_INSTANCES"
      region          = var.aws_region
      instance_ids    = [var.app_instance_id]
    }
  }

  execution_role_arn = aws_iam_role.budget_action.arn

  subscriber {
    address           = var.alert_email
    subscription_type = "EMAIL"
  }
}
