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
  description = "Monthly cost budget that triggers the alert email."
  type        = number
  default     = 5
}
