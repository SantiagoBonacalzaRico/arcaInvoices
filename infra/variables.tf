variable "aws_region" {
  description = "AWS region (closest to Argentina = sa-east-1)."
  type        = string
  default     = "sa-east-1"
}

variable "project" {
  description = "Project name; used as a prefix for resource names and the SSM path."
  type        = string
  default     = "arcainvoices"
}

variable "github_repo" {
  description = "owner/repo that GitHub Actions deploys from (OIDC trust)."
  type        = string
  default     = "SantiagoBonacalzaRico/arcaInvoices"
}

variable "github_branch" {
  description = "Branch allowed to assume the deploy role (master -> prod)."
  type        = string
  default     = "master"
}

variable "alert_email" {
  description = "Email for the billing budget alert."
  type        = string
}

variable "instance_type" {
  description = "EC2 instance type. Graviton t4g.micro (arm64): same 1GB RAM as t3.micro, ~30% cheaper in sa-east-1."
  type        = string
  default     = "t4g.micro"
}

variable "db_instance_class" {
  description = "RDS instance class (free tier = db.t4g.micro)."
  type        = string
  default     = "db.t4g.micro"
}

variable "db_engine_version" {
  description = "PostgreSQL major version for RDS."
  type        = string
  default     = "16"
}

variable "db_name" {
  description = "Initial database name."
  type        = string
  default     = "arcainvoices"
}

variable "db_username" {
  description = "RDS master username."
  type        = string
  default     = "arca"
}

variable "admin_email" {
  description = "Seeded owner/admin email for the app (first user)."
  type        = string
}

variable "admin_username" {
  description = "Seeded owner/admin username for the app."
  type        = string
  default     = "admin"
}

variable "monthly_budget_usd" {
  description = "Monthly cost budget: alerts at 80%/100% and auto-stops EC2 at 100%."
  type        = number
  default     = 15
}

variable "app_instance_id" {
  description = <<-EOT
    EC2 instance the budget auto-stop targets. Pinned as a literal so the
    guardrail doesn't couple to the instance resource. Update this whenever the
    instance is replaced (e.g. the 2026-10 Graviton migration).
  EOT
  type        = string
  default     = "i-0d84e2d9d02c55d17"
}

variable "domain" {
  description = "Custom apex domain for the app. www.<domain> is the primary URL."
  type        = string
  default     = "easyinvoices.com.ar"
}
