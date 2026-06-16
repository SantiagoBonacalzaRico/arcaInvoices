output "elastic_ip" {
  description = "Public IP for the app — point the domain's A record here (Phase 5)."
  value       = aws_eip.app.public_ip
}

output "instance_id" {
  description = "EC2 instance id (SSM deploy target)."
  value       = aws_instance.app.id
}

output "ecr_repository_url" {
  description = "ECR repo to push images to (GitHub Actions)."
  value       = aws_ecr_repository.app.repository_url
}

output "rds_endpoint" {
  description = "RDS Postgres endpoint (private; reachable only from the instance)."
  value       = aws_db_instance.this.address
}

output "github_actions_role_arn" {
  description = "Role ARN GitHub Actions assumes via OIDC (set as a repo secret in Phase 6)."
  value       = aws_iam_role.github_actions.arn
}

output "ssm_parameter_prefix" {
  description = "SSM path holding the app's env/secrets."
  value       = local.ssm_prefix
}

output "admin_password_hint" {
  description = "How to retrieve the generated first-login admin password."
  value       = "aws ssm get-parameter --name ${local.ssm_prefix}/ADMIN_PASSWORD --with-decryption --query Parameter.Value --output text"
}
