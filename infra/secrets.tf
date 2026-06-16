locals {
  ssm_prefix = "/${var.project}/prod"
}

# ── Generated secrets ─────────────────────────────────────────────────────────
# special=false keeps the values URL-safe (used inside the DB_URL).

resource "random_password" "db" {
  length  = 24
  special = false
}

resource "random_password" "secret_key" {
  length  = 48
  special = false
}

resource "random_password" "jwt_secret" {
  length  = 48
  special = false
}

resource "random_password" "admin" {
  length  = 16
  special = false
}

# ── Managed parameters (Terraform owns the value) ─────────────────────────────

resource "aws_ssm_parameter" "db_url" {
  name  = "${local.ssm_prefix}/DB_URL"
  type  = "SecureString"
  value = "postgresql+psycopg2://${var.db_username}:${random_password.db.result}@${aws_db_instance.this.address}:5432/${var.db_name}"
}

resource "aws_ssm_parameter" "secret_key" {
  name  = "${local.ssm_prefix}/SECRET_KEY"
  type  = "SecureString"
  value = random_password.secret_key.result
}

resource "aws_ssm_parameter" "jwt_secret" {
  name  = "${local.ssm_prefix}/JWT_SECRET"
  type  = "SecureString"
  value = random_password.jwt_secret.result
}

resource "aws_ssm_parameter" "admin_email" {
  name  = "${local.ssm_prefix}/ADMIN_EMAIL"
  type  = "String"
  value = var.admin_email
}

resource "aws_ssm_parameter" "admin_username" {
  name  = "${local.ssm_prefix}/ADMIN_USERNAME"
  type  = "String"
  value = var.admin_username
}

resource "aws_ssm_parameter" "admin_password" {
  name  = "${local.ssm_prefix}/ADMIN_PASSWORD"
  type  = "SecureString"
  value = random_password.admin.result
}

resource "aws_ssm_parameter" "cookie_secure" {
  name  = "${local.ssm_prefix}/COOKIE_SECURE"
  type  = "String"
  value = "true"
}

# ── Placeholder parameters (you fill these in later, out-of-band) ─────────────
# Terraform creates them once, then ignores value changes so updating them via
# `aws ssm put-parameter --overwrite` (or the console) won't be reverted.
# APP_BASE_URL / OAUTH_REDIRECT_BASE / CORS_ORIGINS get their real values in
# Phase 5 once the domain exists.

resource "aws_ssm_parameter" "placeholders" {
  for_each = {
    APP_BASE_URL         = "https://CHANGE_ME"
    OAUTH_REDIRECT_BASE  = "https://CHANGE_ME"
    CORS_ORIGINS         = "[\"https://CHANGE_ME\"]"
    GOOGLE_CLIENT_ID     = "REPLACE_ME"
    SYSTEM_SMTP_HOST     = "smtp.gmail.com"
    SYSTEM_SMTP_PORT     = "587"
    SYSTEM_SMTP_USER     = "REPLACE_ME"
    SYSTEM_SMTP_FROM     = "REPLACE_ME"
  }

  name  = "${local.ssm_prefix}/${each.key}"
  type  = "String"
  value = each.value

  lifecycle {
    ignore_changes = [value]
  }
}

resource "aws_ssm_parameter" "secret_placeholders" {
  for_each = toset([
    "GOOGLE_CLIENT_SECRET",
    "SYSTEM_SMTP_PASSWORD",
  ])

  name  = "${local.ssm_prefix}/${each.key}"
  type  = "SecureString"
  value = "REPLACE_ME"

  lifecycle {
    ignore_changes = [value]
  }
}
