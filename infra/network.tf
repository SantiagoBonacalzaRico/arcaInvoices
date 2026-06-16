data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

# Use the account's default VPC + its subnets (free; no NAT gateways).
data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
}

# Latest Amazon Linux 2023 AMI (x86_64) via the public SSM parameter.
data "aws_ssm_parameter" "al2023_ami" {
  name = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64"
}

# ── Security groups ───────────────────────────────────────────────────────────

# Web tier: HTTP/HTTPS open to the world. No SSH — administration is via
# SSM Session Manager (no inbound port, no key pair to leak).
resource "aws_security_group" "web" {
  name        = "${var.project}-web"
  description = "arcaInvoices web: 80/443 in, all out. No SSH (use SSM)."
  vpc_id      = data.aws_vpc.default.id

  ingress {
    description = "HTTP"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "HTTPS"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    description = "All outbound"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "${var.project}-web" }
}

# Database tier: Postgres reachable ONLY from the web security group.
resource "aws_security_group" "db" {
  name        = "${var.project}-db"
  description = "arcaInvoices db: 5432 from web SG only."
  vpc_id      = data.aws_vpc.default.id

  ingress {
    description     = "PostgreSQL from web tier"
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.web.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "${var.project}-db" }
}
