# infra/ — AWS infrastructure (Terraform)

Provisions the production environment for arcaInvoices on AWS, free-tier sized.

## What it creates
- **ECR** repo for the app image (keeps last 10 images).
- **Security groups**: web (80/443 from anywhere, no SSH), db (5432 from web only).
- **EC2 `t3.micro`** (Amazon Linux 2023) + **Elastic IP**, Docker pre-installed,
  admin via **SSM Session Manager** (no SSH key).
- **RDS PostgreSQL `db.t4g.micro`** (private, encrypted, 20 GB).
- **SSM Parameter Store** under `/arcainvoices/prod/*` holding env + secrets
  (DB URL, generated SECRET/JWT/admin password, plus placeholders you fill in).
- **GitHub OIDC** provider + deploy role (ECR push + SSM SendCommand).
- **Budget** alert email.

State is **local** (gitignored). Single environment.

## Prerequisites
- AWS CLI configured (`aws sts get-caller-identity` works) — see `../docs/AWS_SETUP.md`.
- `terraform.tfvars` filled in (copy from `terraform.tfvars.example`).

## Usage
```bash
cd infra
terraform init
terraform plan      # review — creates nothing
terraform apply     # provisions everything (review the plan, type yes)
```

## After apply
```bash
terraform output                         # EIP, ECR URL, RDS endpoint, role ARN
# Retrieve the generated first-login admin password:
aws ssm get-parameter --name /arcainvoices/prod/ADMIN_PASSWORD \
  --with-decryption --query Parameter.Value --output text
```

Fill in the placeholder SSM params (Google OAuth, SMTP, and — in Phase 5 —
APP_BASE_URL / OAUTH_REDIRECT_BASE / CORS_ORIGINS for the real domain), e.g.:
```bash
aws ssm put-parameter --name /arcainvoices/prod/SYSTEM_SMTP_USER \
  --type String --overwrite --value "you@gmail.com"
```

## Teardown
```bash
terraform destroy
```
