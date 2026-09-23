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
  description = "EC2 instance type (free tier in sa-east-1 = t3.micro)."
  type        = string
  default     = "t3.micro"
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
    EC2 instance the budget auto-stop targets. Pinned as a literal (not
    aws_instance.app.id) so the guardrail can be applied without coupling to the
    instance resource, which currently has pending AMI-replacement drift.
  EOT
  type        = string
  default     = "i-0d6efa55a2280a51d"
}

variable "domain" {
  description = "Custom apex domain for the app. www.<domain> is the primary URL."
  type        = string
  default     = "easyinvoices.com.ar"
}
