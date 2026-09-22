# RDS removed 2026-09-22: after the AWS Free Tier ended the account was
# suspended for the ~$30/mo bill. To stay within budget the app now runs on
# SQLite (on the EC2 EBS volume); all data was migrated out of the final
# Postgres snapshot. The db subnet group is kept (free, unused) to avoid
# destroy-ordering churn. DB_URL now points at SQLite (see secrets.tf).
resource "aws_db_subnet_group" "this" {
  name       = "${var.project}-db"
  subnet_ids = data.aws_subnets.default.ids
}
